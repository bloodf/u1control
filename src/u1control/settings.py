"""One settings store for every capability (page, print setup, scripts). Free of the `orca` module.

Automagic mode: effective() answers with the automagic value of every automation; the stored
expert values are kept but ignored. Expert mode: stored values, defaulting to the automagic ones.
Connection keys (printer address, Spoolman URL, ...) are the same in both modes.
"""

import json
import os
import threading

AUTOMAGIC, EXPERT = "automagic", "expert"
PIPELINE_NAME = "U1 print setup"
PURIFIER_CHOICES = ("auto", "keep-warm", "weak", "strong", "off")

# (key, label, help, automagic value, "bool" | tuple of choices)
AUTOMATIONS = [
    ("mode", "Mode", "Automagic does everything it can by itself; Expert lets you change each step.",
     AUTOMAGIC, (AUTOMAGIC, EXPERT)),
    ("auto_add_pipeline", "Add \"U1 print setup\" to U1 process presets",
     "Adds it to the Slicing Pipeline Plugin setting of your U1 process preset, and gives a U1 printer preset with no "
     "address U1 Control's printer address so OrcaSlicer's Print button works (save the presets to keep them).", True, "bool"),
    ("print_dialog", "Show print setup before sending",
     "After OrcaSlicer's Print, choose the toolheads and options in U1 Control's window. Off: OrcaSlicer's "
     "choice is sent as is, and a material mismatch or a busy U1 is still refused.", True, "bool"),
    ("purifier", "Top cover (purifier) mode", "auto follows Snapmaker's softening-temperature rule.", "auto", PURIFIER_CHOICES),
    ("chamber_wait", "Wait for chamber temperature", "Adds WAIT_CHAMBER_TEMP after bed heat-up when missing.", True, "bool"),
    ("whole_bed_mesh", "Whole-bed bed mesh", "11x11 mesh instead of adaptive (the U1 keeps one mesh).", True, "bool"),
    ("fan_off_probing", "Part fan off while probing", "As Snapmaker Orca.", True, "bool"),
    ("by_object_lift_fix", "Print-by-object tool-change lift fix", "Snapmaker Orca fix #958.", True, "bool"),
    ("real_total_layers", "Real total layer count", "For the touchscreen's layer counter.", True, "bool"),
    ("recolour_metadata", "Recolour file metadata", "Shows the assigned heads' colours in the printer's file list.", True, "bool"),
    ("remember_print_options", "Remember print options", "Reuse the options chosen in the pop-up.", True, "bool"),
    ("rfid_auto_sync", "Apply RFID tags to project filaments", "When a toolhead reads a new tag.", True, "bool"),
    ("spoolman_auto", "Bind a spool when a toolhead changes", "Picks the closest Spoolman spool.", True, "bool"),
    ("spoolman_report_usage", "Report filament use to Spoolman", "Deducts each head's grams when a print finishes.", True, "bool"),
    ("spoolman_write_printer", "Write the bound spool to the toolhead",
     "Sends the spool's vendor, material and colour to the head.", True, "bool"),
    ("bed_level", "Print option: auto bed leveling", "Default for the print setup.", True, "bool"),
    ("flow_calibrate", "Print option: flow calibration", "Default for the print setup.", True, "bool"),
    ("time_lapse_camera", "Print option: time-lapse", "Default for the print setup.", False, "bool"),
]
CONNECTION = {"host": "", "api_key": "", "printer_name": "Snapmaker U1", "spoolman_url": "", "profile_overrides": {}}
EXTRA = {"spooler_hint_dismissed": False, "prefs": {}, "printed_before": False, "stored_pa": False, "ui_language": "auto", "ui_theme": "auto", "camera_fps": 5,
         "network_origins": [],   # scheme://host of printers and Spoolman used: the network grants asked for at load
         "spoolman_refresh_s": 30,
         "overrides_migrated": False,
         "ofd_enabled": False,   # Open Filament Database proposals on the toolhead cards; off: never contacted   # profile_overrides copied into matches.json once (filmatch); then read no more
         "dashboard": {}}   # the Dashboard's layouts (clean_dashboard); {} = the page's default   # the page re-reads Spoolman this often while it shows (0 = off; 10-300)
UI_LANGUAGES = ("auto", "en", "pt-BR", "es", "de", "zh-CN", "pl", "cs")   # "auto": OrcaSlicer's language, then the system's
UI_THEMES = ("auto", "light", "dark")   # "auto": OrcaSlicer's background, then the system's light/dark mode
CAMERA_FPS = (5, 10, 15, 30)   # live camera: most pictures a second U1 Control asks the printer for
REFRESH_RANGE = (10, 300)      # spoolman_refresh_s: 0 (off) or seconds in this range


def valid_refresh(value):
    return type(value) is int and (value == 0 or REFRESH_RANGE[0] <= value <= REFRESH_RANGE[1])


DASHBOARD_MAX_BYTES = 32_000   # the page's dashboard layouts (settings "dashboard"), serialized


def clean_dashboard(value):
    """The page's dashboard layouts as stored: {"v": 1, "active": n, "layouts": [{"name", "items": [{"id", "x", "y",
    "w", "h", "cfg"}]}]}. The shape and the size only: the page itself drops widgets it does not know and brings sizes
    within each widget's limits. None when the value is not a dashboard (the stored one is kept)."""
    if not isinstance(value, dict) or value.get("v") != 1:
        return None
    layouts = value.get("layouts")
    if not isinstance(layouts, list) or not 1 <= len(layouts) <= 12:
        return None
    out = []
    for layout in layouts:
        if not isinstance(layout, dict) or not isinstance(layout.get("name"), str) or not isinstance(layout.get("items"), list) \
                or len(layout["items"]) > 40:
            return None
        items = []
        for it in layout["items"]:
            if not isinstance(it, dict) or not isinstance(it.get("id"), str) or not 0 < len(it["id"]) <= 40 \
                    or not all(type(it.get(k)) is int and 0 <= it[k] <= 200 for k in ("x", "y", "w", "h")):
                return None
            item = {k: it[k] for k in ("id", "x", "y", "w", "h")}
            cfg = it.get("cfg")
            if cfg is not None:
                if not isinstance(cfg, dict) or not all(isinstance(k, str) and type(v) in (str, int, float, bool) for k, v in cfg.items()):
                    return None
                item["cfg"] = dict(cfg)
            items.append(item)
        out.append({"name": layout["name"][:40], "items": items})
    active = value.get("active")
    clean = {"v": 1, "active": active if type(active) is int and 0 <= active < len(out) else 0, "layouts": out}
    return clean if len(json.dumps(clean)) <= DASHBOARD_MAX_BYTES else None


def automagic_values():
    return {k: v for k, _, _, v, _ in AUTOMATIONS if k != "mode"}


def _valid(kind, value):
    return isinstance(value, bool) if kind == "bool" else value in kind


class Store:
    """JSON file at `path`, or load() -> text / save(text) callables when no path is available."""

    def __init__(self, path=None, load=None, save=None):
        self.path, self._load, self._save = path, load, save
        self.lock = threading.RLock()
        self.data = self._read()

    def _read(self):
        try:
            if self.path:
                with open(self.path, encoding="utf-8") as f:
                    text = f.read()
            elif self._load:
                text = self._load()
            else:
                return {}
            data = json.loads(text)
        except (OSError, ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data):
        text = json.dumps(data, indent=1, sort_keys=True)
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        elif self._save:
            self._save(text)
        self.data = data

    def effective(self):
        with self.lock:
            d = self.data
            mode = d.get("mode") if d.get("mode") in (AUTOMAGIC, EXPERT) else AUTOMAGIC
            out = {**CONNECTION, **EXTRA, "mode": mode}
            for k in out:
                if k in d and k != "mode" and type(d[k]) is type(out[k]):
                    out[k] = d[k]
            for key, _, _, default, kind in AUTOMATIONS:
                if key != "mode":
                    stored = d.get(key, default)
                    out[key] = stored if mode == EXPERT and _valid(kind, stored) else default
            if mode == EXPERT and d.get("print_dialog") == "never":   # the choice before it became on/off
                out["print_dialog"] = False
            if out["ui_theme"] not in UI_THEMES:
                out["ui_theme"] = EXTRA["ui_theme"]
            if out["camera_fps"] not in CAMERA_FPS:
                out["camera_fps"] = EXTRA["camera_fps"]
            if not valid_refresh(out["spoolman_refresh_s"]):
                out["spoolman_refresh_s"] = EXTRA["spoolman_refresh_s"]
            return {k: dict(v) if isinstance(v, dict) else v for k, v in out.items()}

    def raw(self):
        with self.lock:
            return dict(self.data)

    def update(self, changes):
        """Validate and persist {key: value}; unknown or invalid keys are ignored. Returns effective()."""
        with self.lock:
            data = dict(self.data)
            kinds = {k: kind for k, _, _, _, kind in AUTOMATIONS}
            for key, value in (changes or {}).items():
                if key in kinds:
                    if _valid(kinds[key], value):
                        data[key] = value
                elif key == "ui_language":
                    if value in UI_LANGUAGES:
                        data[key] = value
                elif key == "ui_theme":
                    if value in UI_THEMES:
                        data[key] = value
                elif key == "camera_fps":
                    if type(value) is int and value in CAMERA_FPS:
                        data[key] = value
                elif key == "spoolman_refresh_s":
                    if valid_refresh(value):
                        data[key] = value
                elif key == "dashboard":
                    clean = clean_dashboard(value)
                    if clean is not None:
                        data[key] = clean
                elif key in CONNECTION or key in EXTRA:
                    default = {**CONNECTION, **EXTRA}[key]
                    if type(value) is type(default):
                        data[key] = printer_label(value) if key == "printer_name" else value
            if data != self.data:
                self._write(data)
            return self.effective()


# ---------------------------------------------------------------------- Orca ConfigOptionStrings

def printer_label(name):
    """Spoolman location prefix. Spooler binds a "<name> T<n>" location only when the name is its own
    printer label/model or ends in "U1", so keep that suffix: "Bob" -> "Bob U1"."""
    name = " ".join(str(name or "").split())[:56] or CONNECTION["printer_name"]
    return name if name.upper().endswith("U1") else name + " U1"


def serialize_strings(values):
    """Orca's ";"-separated string list: an entry with a space, ";", quote or backslash is quoted."""
    out = []
    for v in values:
        v = str(v)
        if (len(values) == 1 and not v) or any(c in v for c in ' ;\t\\"\r\n'):
            v = '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n") + '"'
        out.append(v)
    return ";".join(out)


def parse_strings(value):
    """Inverse of serialize_strings; also accepts a list (what the host may hand back)."""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    text, out, cur, quoted, i = str(value or ""), [], [], False, 0
    if not text.strip():
        return []
    while i < len(text):
        c = text[i]
        if quoted and c == "\\" and i + 1 < len(text):
            i += 1
            cur.append({"n": "\n", "r": "\r"}.get(text[i], text[i]))
        elif c == '"':
            quoted = not quoted
        elif c == ";" and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def with_pipeline(value, name=PIPELINE_NAME):
    """New slicing_pipeline_plugin value with `name` added, or None when it is already there."""
    entries = parse_strings(value)
    if name in entries:
        return None
    return serialize_strings([e for e in entries if e] + [name])
