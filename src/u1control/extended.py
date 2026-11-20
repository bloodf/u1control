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

import sys

_CS_GROUPS = {
    "web": "Web",
    "camera": "Kamera",
    "remote_access": "Vzdálený přístup",
    "snapmaker_components": "Komponenty Snapmaker",
    "print_preferences": "Předvolby tisku",
    "tweaks": "Vyladění (Tweaks)",
    "troubleshooting": "Řešení problémů",
    "monitoring_debugging": "Monitoring a ladění",
}

_CS_ITEMS = {
    "web-frontend": ("Webové rozhraní", "Volba mezi Fluidd a Mainsail jako webovým rozhraním."),
    "firmware-config": ("Konfigurace firmwaru", "Povolit nebo zakázat toto webové konfigurační rozhraní."),
    "remote-screen": ("Vzdálená obrazovka", "Streamovat dotykovou obrazovku tiskárny do prohlížeče."),
    "camera-internal": ("Interní kamera", "Výběr ovladače pro vestavěnou MIPI kameru."),
    "camera-internal-resolution": ("Rozlišení interní kamery", "Rozlišení a snímková frekvence vestavěné MIPI kamery. Rozlišení je vždy 1080p; snížit lze pouze snímkovou frekvenci."),
    "camera-usb": ("USB kamera", "Povolit streamování z připojené USB kamery."),
    "camera-rtsp": ("RTSP stream (pouze paxx12)", "Povolit výstup RTSP streamu pro interní kameru (pouze ovladač paxx12)."),
    "ssh": ("SSH přístup", "Povolit vzdálený přístup do příkazové řádky tiskárny přes SSH."),
    "authorization": ("Webové ověřování (experimentální)", "Chránit přístup do Fluidd a Konfigurace firmwaru heslem přes ověřování Moonrakeru."),
    "vpn": ("VPN poskytovatel (experimentální)", "Připojit tiskárnu k VPN pro bezpečný vzdálený přístup odkudkoliv."),
    "cloud": ("Cloudový přístup (experimentální)", "Povolit alternativní cloudový přístup mimo vaši síť."),
    "rfid": ("Detekce filamentu", "Nastavení způsobu detekce filamentu."),
    "firmware-upgrade-channel": ("Aktualizace firmwaru", "Povolit nebo zakázat aktualizace paxx12 firmwaru. Vyžaduje použití Snapmaker Cloudu."),
    "afc": ("AFC Lite přes Fluidd/Mainsail", "Vícekanálová správa filamentů s makry CHANGE_TOOL a LANE_UNLOAD."),
    "spoolman": ("Integrace Spoolman", "Sledování spotřeby filamentu a metadat pomocí správy cívek Spoolman."),
    "chamber_heater": ("Vyhřívání komory PandaBreath / DragonBreath", "Integrace ohřívače komory a filtru vzduchu BIQU Panda Breath nebo otevřeného firmwaru DragonBreath na stejné desce."),
    "filament_feeders": ("Podavače filamentu", "Výběr sestavy podavačů filamentu. Sestavy s delší dráhou k tiskové hlavě (např. BIQU PopStation mini) vyžadují delší délku zavedení než standardních 950 mm."),
    "gui": ("Rozhraní dotykové obrazovky (experimentální)", "Výběr rozhraní zobrazovaného na vestavěné dotykové obrazovce tiskárny."),
    "bed_leveling_force": ("Vynutit kalibraci sítě podložky", "Vynutí kalibraci sítě podložky (bed mesh) před každým tiskem."),
    "object_processing": ("Zpracování objektů pro adaptivní síť", "Povolí zpracování objektů v Moonrakeru pro adaptivní síť. Doporučuje se raději zapnout Exclude Object přímo ve sliceru."),
    "timelapse_force": ("Vynutit časosběr", "Vynutí časosběr bez ohledu na nastavení v aplikaci Snapmaker. Slicer musí volat TIMELAPSE_START, TIMELAPSE_TAKE_FRAME a TIMELAPSE_STOP."),
    "max_speed": ("Maximální rychlost", "Experimentální. Zvyšuje limity pohybu XY a zrychluje výměny nástrojů. Zvyšuje opotřebení tiskárny a může způsobit problémy (např. přeskakování osy Z). Vyvážený režim je doporučený základ; vyžaduje zkalibrovanou tiskárnu."),
    "tmc_autotune": ("TMC AutoTune", "Optimalizuje nastavení driverů TMC2240 pro tišší chod a lepší výkon."),
    "tmc_reduce_current": ("Snížený proud TMC", "Snižuje proud motorů X/Y z 1,2 A na 1,0 A pro tišší chod a nižší zahřívání."),
    "toolhead1": ("Tisková hlava 1", "Dočasné přemostění termistoru, ohřevu nebo MCU pro tiskovou hlavu 1."),
    "toolhead2": ("Tisková hlava 2", "Dočasné přemostění termistoru, ohřevu nebo MCU pro tiskovou hlavu 2."),
    "toolhead3": ("Tisková hlava 3", "Dočasné přemostění termistoru, ohřevu nebo MCU pro tiskovou hlavu 3."),
    "toolhead4": ("Tisková hlava 4", "Dočasné přemostění termistoru, ohřevu nebo MCU pro tiskovou hlavu 4."),
    "klipper-metrics": ("Export metrik Klipperu", "Exportuje metriky Klipperu pro sběr pomocí Promethea."),
}

_CS_OPTION_LABELS = {
    "Enabled": "Povoleno",
    "Disabled": "Zakázáno",
    "None": "Žádný",
    "Default": "Výchozí",
    "Normal": "Normální",
    "External": "Externí",
    "OpenRFID (force generic vendor)": "OpenRFID (vynutit výrobce Generic)",
    "Stable (recommended)": "Stabilní (doporučeno)",
    "Testing (pre-releases)": "Testovací (předběžná vydání)",
    "Develop (bleeding edge)": "Vývojová (bleeding edge)",
    "Enabled (Force Generic Vendor)": "Povoleno (vynutit výrobce Generic)",
    "Panda Breath (Manual mode)": "Panda Breath (manuální režim)",
    "DragonBreath (Recommended)": "DragonBreath (doporučeno)",
    "Force Full Mesh": "Vynutit plnou síť",
    "Force Adaptive Mesh": "Vynutit adaptivní síť",
    "Balanced": "Vyvážený",
    "Aggressive": "Agresivní",
    "Bypass Thermistor": "Přemostit termistor",
    "Bypass MCU (Disconnected)": "Přemostit MCU (odpojeno)",
}


def _is_cs():
    for name in ("plugin", "u1control.plugin"):
        mod = sys.modules.get(name)
        if mod is not None:
            store = getattr(mod, "_store", None)
            pref = store.effective().get("ui_language", "auto") if store is not None else "auto"
            if pref == "cs":
                return True
            if pref != "auto":
                return False
            host = str(getattr(mod, "_host_lang", "") or "").lower()
            if host.startswith("cs"):
                return True
            if host:
                return False
    return False


from moonraker import PrinterError
from i18n import tr

API = "/firmware-config/api"
SETTING_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
INPUT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
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


def _option(value, raw, cs=False):
    if not isinstance(raw, dict) or not VALUE_RE.match(str(value)):
        raise ValueError("option %r" % value)
    confirm = raw.get("confirm")
    label = _text(raw.get("label")) or str(value)
    if cs:
        label = _CS_OPTION_LABELS.get(label, label)
    return {"value": str(value), "label": label,
            "confirm": confirm if isinstance(confirm, str) else ("" if not confirm else tr("Apply this change?")),
            "hidden": raw.get("hidden") is True, "inputs": _inputs(raw.get("inputs"))}


def _item(raw, cs=False):
    if not isinstance(raw, dict) or not SETTING_ID_RE.match(_text(raw.get("id"))) or not isinstance(raw.get("options"), dict):
        raise ValueError("setting")
    current = raw.get("current")
    label = _text(raw.get("label")) or raw["id"]
    desc = _text(raw.get("description"))
    if cs and raw["id"] in _CS_ITEMS:
        label, desc = _CS_ITEMS[raw["id"]]
    return {"id": raw["id"], "label": label, "description": desc,
            "help_url": _text(raw.get("help_url")), "current": "" if current is None else str(current),
            "hidden": raw.get("hidden") is True, "print_safe": raw["id"] in PRINT_SAFE,
            "options": [_option(k, v, cs) for k, v in raw["options"].items()]}


def normalize_settings(data):
    """[{"id", "label", "items": [{"id", "label", "description", "help_url", "current", "hidden", "print_safe",
    "options": [{"value", "label", "confirm", "hidden", "inputs": [...]}]}]}] from the API answer.
    print_safe: the setting can change during a print (PRINT_SAFE).
    Raises PrinterError when the answer has another shape."""
    try:
        if not isinstance(data, dict):
            raise ValueError("top level")
        cs = _is_cs()
        groups = []
        for gid, group in data.items():
            if not isinstance(group, dict) or not isinstance(group.get("items"), list):
                raise ValueError("group %r" % gid)
            glabel = _text(group.get("label")) or str(gid)
            if cs and str(gid) in _CS_GROUPS:
                glabel = _CS_GROUPS[str(gid)]
            groups.append({"id": str(gid), "label": glabel,
                           "items": [_item(i, cs) for i in group["items"]]})
        return groups
    except ValueError as e:
        raise PrinterError(tr("Firmware Config sent settings u1control can't read (%s)") % e) from e
