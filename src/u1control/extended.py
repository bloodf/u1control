"""paxx12 U1 Extended Firmware: Firmware Config REST API at http://<ip>/firmware-config/api/.

Needs Advanced Mode on the printer and [web] firmware_config: true. Setting changes stream a
text/plain log that ends in 'SUCCESS: ...' or 'ERROR: ...'.

GET /settings answers {group: {"label", "items": [{"id", "label", "description", "help_url", "current",
"hidden", "options": {value: {"label", "confirm"?, "hidden"?, "inputs"?: [{"name", "label",
"placeholder", "regex"}]}}}]}} (firmware-config.py, release v2.0.0-paxx12-24, handle_get_settings).
"""

import json
import re
import urllib.parse

from moonraker import PrinterError
from i18n import tr

API = "/firmware-config/api"
SETTING_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}\Z")
VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}\Z")
INPUT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}\Z")
INPUT_MAX = 512
ACTIONS = ("restart-klipper", "restart-moonraker", "reboot-system")
PRINT_ENDING_ACTIONS = ("restart-klipper", "reboot-system")
# Settings whose change leaves Klipper running, so they can change during a print. From the option commands in
# firmware-config/functions/*.yaml (paxx12 Extended Firmware, main of 2026-11-07): these restart only nginx, Moonraker,
# SSH, the USB camera, the remote screen, VPN, cloud or metrics services, or the Firmware Config service itself.
# Every other setting restarts Klipper or reboots, and so does any setting a newer release adds: those wait.
PRINT_SAFE = ("web-frontend", "firmware-config", "remote-screen", "ssh", "camera-usb", "camera-usb-resolution",
              "camera-rtsp", "vpn", "cloud", "object_processing", "spoolman_tag_store", "klipper-metrics")


class Extended:
    def __init__(self, moonraker):
        self.mr = moonraker

    def _get(self, path, timeout=None):
        data, headers = self.mr.raw("GET", API + path, timeout=timeout)
        if "json" not in (headers.get("Content-Type") or ""):
            # stock nginx falls through to the web UI's index.html with 200
            raise PrinterError(tr("Firmware Config API not available"))
        return json.loads(data.decode("utf-8"))

    def status(self):
        """Version info, or None when this isn't extended firmware / Advanced Mode is off."""
        return self.probe()[0]

    def probe(self):
        """(status, conclusive). status: the API's version info, or None. conclusive: the printer really answered
        (JSON, or the web UI's page / a 4xx that says there is no API here). A timeout, a refused connection, a 5xx
        or a broken answer is not conclusive: the API may just be starting, so ask again later."""
        try:
            data, headers = self.mr.raw("GET", API + "/status", timeout=3)
        except PrinterError as e:
            return None, e.status is not None and e.status < 500
        except OSError:
            return None, False
        if "json" not in (headers.get("Content-Type") or ""):
            return None, True   # stock nginx falls through to the web UI's index.html with 200
        try:
            status = json.loads(data.decode("utf-8"))
        except ValueError:
            return None, False
        return (status, True) if isinstance(status, dict) else (None, False)

    def settings(self):
        """The firmware's settings as groups, see normalize_settings."""
        return normalize_settings(self._get("/settings"))

    def set(self, setting_id, value, inputs=None):
        if not SETTING_ID_RE.match(setting_id or "") or not VALUE_RE.match(str(value)):
            raise PrinterError(tr("invalid setting %r=%r") % (setting_id, value))
        if inputs is not None and (not isinstance(inputs, dict) or any(
                not INPUT_NAME_RE.match(str(k)) or not isinstance(v, str) or len(v) > INPUT_MAX
                for k, v in inputs.items())):
            raise PrinterError(tr("invalid inputs for %s") % setting_id)
        body = json.dumps(inputs).encode("utf-8") if inputs else None
        data, _ = self.mr.raw("POST", "%s/settings/%s/%s" % (API, setting_id, urllib.parse.quote(str(value))),
                              body, {"Content-Type": "application/json"} if body else None, timeout=180)
        return _outcome(data)

    def action(self, action_id):
        if action_id not in ACTIONS:
            raise PrinterError(tr("unsupported action %r") % action_id)
        data, _ = self.mr.raw("POST", "%s/action/%s" % (API, action_id), timeout=120)
        return _outcome(data)


def _outcome(data):
    """{"ok": True} only when the log ends in SUCCESS; an ERROR (or "Error:") ending raises. A log that
    stops without either is {"ok": None}: the change may or may not have happened, and it is not retried."""
    log = data.decode("utf-8", "replace")
    tail = ([l.strip() for l in log.splitlines() if l.strip()][-1:] or [""])[0]
    if tail.upper().startswith("ERROR"):
        raise PrinterError(tail)
    if tail.startswith("SUCCESS"):
        return {"ok": True, "log": log[-4000:]}
    return {"ok": None, "log": log[-4000:],
            "error": tr("the printer didn't report how this ended; reload the settings to see what applied")}


def _text(value):
    return value if isinstance(value, str) else ""


def _inputs(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("inputs")
    out = []
    for i in raw:
        if not isinstance(i, dict) or not INPUT_NAME_RE.match(_text(i.get("name"))):
            raise ValueError("input")
        out.append({"name": i["name"], "label": _text(i.get("label")) or i["name"],
                    "placeholder": _text(i.get("placeholder")), "regex": _text(i.get("regex"))})
    return out


def _option(value, raw):
    if not isinstance(raw, dict) or not VALUE_RE.match(str(value)):
        raise ValueError("option %r" % value)
    confirm = raw.get("confirm")
    return {"value": str(value), "label": tr(_text(raw.get("label"))) or str(value),
            "confirm": confirm if isinstance(confirm, str) else ("" if not confirm else tr("Apply this change?")),
            "hidden": raw.get("hidden") is True, "inputs": _inputs(raw.get("inputs"))}


def _item(raw):
    if not isinstance(raw, dict) or not SETTING_ID_RE.match(_text(raw.get("id"))) or not isinstance(raw.get("options"), dict):
        raise ValueError("setting")
    current = raw.get("current")
    return {"id": raw["id"], "label": tr(_text(raw.get("label"))) or raw["id"], "description": tr(_text(raw.get("description"))),
            "help_url": _text(raw.get("help_url")), "current": "" if current is None else str(current),
            "hidden": raw.get("hidden") is True, "print_safe": raw["id"] in PRINT_SAFE,
            "options": [_option(k, v) for k, v in raw["options"].items()]}


def normalize_settings(data):
    """[{"id", "label", "items": [{"id", "label", "description", "help_url", "current", "hidden", "print_safe",
    "options": [{"value", "label", "confirm", "hidden", "inputs": [...]}]}]}] from the API answer.
    print_safe: the setting can change during a print (PRINT_SAFE).
    Raises PrinterError when the answer has another shape."""
    try:
        if not isinstance(data, dict):
            raise ValueError("top level")
        groups = []
        for gid, group in data.items():
            if not isinstance(group, dict) or not isinstance(group.get("items"), list):
                raise ValueError("group %r" % gid)
            groups.append({"id": str(gid), "label": tr(_text(group.get("label"))) or str(gid),
                           "items": [_item(i) for i in group["items"]]})
        return groups
    except ValueError as e:
        raise PrinterError(tr("Firmware Config sent settings u1control can't read (%s)") % e) from e
