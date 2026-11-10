"""paxx12 U1 Extended Firmware: Firmware Config REST API at http://<ip>/firmware-config/api/.

Needs Advanced Mode on the printer and [web] firmware_config: true. Setting changes stream a
text/plain log that ends in 'SUCCESS: ...' or 'ERROR: ...'.
"""

import json
import re
import urllib.parse

from moonraker import PrinterError

API = "/firmware-config/api"
SETTING_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
ACTIONS = ("restart-klipper", "restart-moonraker", "reboot-system", "show-status")


class Extended:
    def __init__(self, moonraker):
        self.mr = moonraker

    def _get(self, path, timeout=None):
        data, headers = self.mr.raw("GET", API + path, timeout=timeout)
        if "json" not in (headers.get("Content-Type") or ""):
            # stock nginx falls through to the web UI's index.html with 200
            raise PrinterError("Firmware Config API not available")
        return json.loads(data.decode("utf-8"))

    def status(self):
        """Version info, or None when this isn't extended firmware / Advanced Mode is off."""
        try:
            return self._get("/status", timeout=3)
        except (PrinterError, OSError, ValueError):
            return None

    def settings(self):
        """[{id, label?, current, options:[...]...}] exactly as the API returns them."""
        result = self._get("/settings")
        return result.get("settings", result) if isinstance(result, dict) else result

    def set(self, setting_id, value, inputs=None):
        if not SETTING_ID_RE.match(setting_id or "") or not VALUE_RE.match(str(value)):
            raise PrinterError("invalid setting %r=%r" % (setting_id, value))
        body = json.dumps(inputs).encode("utf-8") if inputs else None
        data, _ = self.mr.raw("POST", "%s/settings/%s/%s" % (API, setting_id, urllib.parse.quote(str(value))),
                              body, {"Content-Type": "application/json"} if body else None, timeout=180)
        return _outcome(data)

    def action(self, action_id):
        if action_id not in ACTIONS:
            raise PrinterError("unsupported action %r" % action_id)
        data, _ = self.mr.raw("POST", "%s/action/%s" % (API, action_id), timeout=120)
        return _outcome(data)


def _outcome(data):
    log = data.decode("utf-8", "replace")
    tail = [l for l in log.strip().splitlines() if l.strip()][-1:] or [""]
    if tail[0].startswith("ERROR"):
        raise PrinterError(tail[0])
    return {"ok": True, "log": log[-4000:]}
