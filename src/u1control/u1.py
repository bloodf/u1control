"""Snapmaker U1 domain logic: toolheads, print options, filament mapping, firmware.

Command names and fields come from Snapmaker's open U1 Klipper source
(klippy/extras/print_task_config.py, purifier.py, filament_detect.py).
"""

import re

TOOLHEADS = 4         # PHYSICAL_EXTRUDER_NUM
MAX_FILAMENTS = 32    # LOGICAL_EXTRUDER_NUM
EXTRUDERS = ("extruder", "extruder1", "extruder2", "extruder3")

# (key, SET_PRINT_PREFERENCES param, label, print_task_config field, basic)
# Basic = the three Snapmaker Orca always sends; the others only when the printer reports them.
PREFERENCES = (
    ("bed_level", "BED_LEVEL", "Auto bed leveling", "auto_bed_leveling", True),
    ("flow_calibrate", "FLOW_CALIBRATE", "Flow calibration", "flow_calibrate", True),
    ("time_lapse_camera", "TIME_LAPSE_CAMERA", "Time-lapse", "time_lapse_camera", True),
    ("auto_refill", "AUTO_REPLENISH_FILAMENT", "Auto-refill on run-out", "auto_replenish_filament", False),
    ("refill_any_colour", "REPLENISH_IGNORE_COLOR", "Refill from any colour", "replenish_ignore_color", False),
    ("tangle_detect", "FILAMENT_ENTANGLE_DETECT", "Tangle detection", "filament_entangle_detect", False),
    ("unload_when_done", "END_UNLOAD_FILAMENT", "Unload filament when done", "end_unload_filament", False),
    ("light_off_when_done", "END_LED_TURN_OFF", "Light off when done", "end_led_turn_off", False),
)
PREF_KEYS = tuple(p[0] for p in PREFERENCES)

TASK_FIELDS = ("filament_vendor", "filament_type", "filament_sub_type", "filament_color_rgba",
               "filament_color_multi", "filament_official", "filament_exist", "filament_soft",
               "extruder_map_table", "extruders_used", "reprint_info", "filament_spool_id") + tuple(p[3] for p in PREFERENCES)

STATUS_OBJECTS = {
    "webhooks": None,
    "print_stats": None,
    "display_status": None,
    "virtual_sdcard": ["progress", "file_position", "file_size", "is_active", "pl_env_valid"],
    "machine_state_manager": ["main_state", "action_code"],
    "exception_manager": ["exceptions"],
    "gcode_move": ["speed_factor", "extrude_factor"],
    "toolhead": ["extruder", "homed_axes", "position"],
    "heater_bed": ["temperature", "target"],
    "print_task_config": list(TASK_FIELDS),
    "purifier": None,
    "led cavity_led": ["color_data"],
    "fan": ["speed"],
    "filament_detect": ["info", "state"],   # RFID: Snapmaker, OpenRFID, OpenSpool, external readers
    "filament_feed left": None,   # keyed extruderN: channel_state, filament_detected, ...
    "filament_feed right": None,
    **{name: ["temperature", "target", "state"] for name in EXTRUDERS},
}

# Top-cover purifier commands as Snapmaker's U1 start G-code emits them.
PURIFIER = {
    "keep-warm": "SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45 FAN_SPEED=0.6 DELAY_OFF=600",
    "weak": "SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51 FAN_SPEED=0.6 DELAY_OFF=0",
    "strong": "SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=42 ALARM_TEMP=48 FAN_SPEED=0.6 DELAY_OFF=0",
}
STRONG_COOL_MAX, WEAK_COOL_MAX = 50, 70   # Snapmaker Orca's chamber_cooling_mode thresholds
ORCA_DEFAULT_SOFTENING = 100              # Orca's temperature_vitrification default (often unset)
SOFTENING_BY_TYPE = {                     # from Snapmaker's U1 filament profiles
    "PLA": 45, "PLA+": 45, "PLA-CF": 45, "PLA-GF": 45, "PVA": 45, "BVOH": 45,
    "TPU": 30, "TPE": 30, "PETG": 70, "PETG-CF": 70, "PET": 70, "PCTG": 90,
    "ABS": 100, "ASA": 100, "HIPS": 100, "PC": 120, "PA": 108, "PA-CF": 108, "PAHT-CF": 108,
}


def _at(values, i, default=None):
    return values[i] if isinstance(values, (list, tuple)) and 0 <= i < len(values) else default


def norm_colour(value):
    """'#ff0000', 'FF0000FF', 'ff0000' -> '#FF0000'; anything else -> None."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", str(value or "").strip())
    return "#" + m.group(1).upper() if m else None


def colour_distance(a, b):
    """Weighted RGB distance ('redmean'); unknown colours are far apart."""
    a, b = norm_colour(a), norm_colour(b)
    if not a or not b:
        return 765.0
    r1, g1, b1 = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    r2, g2, b2 = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    rm = (r1 + r2) / 2
    return ((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2) ** 0.5


def material_family(ftype):
    """'PLA-CF' / 'PLA Matte' / 'PLA+' -> 'PLA'."""
    m = re.match(r"[A-Za-z]+", (ftype or "").strip())
    return m.group(0).upper() if m else ""


def describe_toolheads(task):
    heads = []
    for t in range(TOOLHEADS):
        ftype = str(_at(task.get("filament_type"), t, "") or "")
        none = ftype.upper() in ("", "NONE")
        exist = _at(task.get("filament_exist"), t)
        multi = _at(task.get("filament_color_multi"), t) or {}  # {nums, alpha, colors, mode}
        multi = multi.get("colors") if isinstance(multi, dict) else multi
        heads.append({
            "index": t,
            "type": "" if none else ftype,
            "vendor": str(_at(task.get("filament_vendor"), t, "") or "").replace("NONE", ""),
            "sub_type": str(_at(task.get("filament_sub_type"), t, "") or "").replace("NONE", ""),
            "colour": norm_colour(_at(task.get("filament_color_rgba"), t)),
            "colours": [c for c in (norm_colour(x) for x in multi) if c] if isinstance(multi, list) else [],
            "official": bool(_at(task.get("filament_official"), t, False)),
            "present": bool(exist) if exist is not None else not none,
            "loaded": (bool(exist) if exist is not None else True) and not none,
        })
    return heads


def _hex_rgb(value):
    try:
        return "#%06X" % (int(value) & 0xFFFFFF)
    except (TypeError, ValueError):
        return norm_colour(value)


def _none(value):
    text = str(value if value is not None else "").strip()
    return "" if text.upper() in ("", "NONE", "0") else text


def rfid_tags(detect):
    """Parsed tag per toolhead from filament_detect.info (any reader: Snapmaker, OpenRFID,
    OpenSpool, external NFC). None when no tag was read for that head."""
    infos = (detect or {}).get("info") or []
    tags = []
    for t in range(TOOLHEADS):
        info = _at(infos, t) or {}
        ftype = _none(info.get("MAIN_TYPE"))
        uid = info.get("CARD_UID")
        uid = "".join("%02X" % (b & 0xFF) for b in uid) if isinstance(uid, list) else _none(uid)
        uid = "" if uid and not uid.strip("0") else uid  # all-zero = empty reader slot
        if not ftype and not uid:
            tags.append(None)
            continue
        n = max(1, min(int(info.get("COLOR_NUMS") or 1), 5))
        tags.append({
            "vendor": _none(info.get("VENDOR")), "manufacturer": _none(info.get("MANUFACTURER")),
            "type": ftype, "sub_type": _none(info.get("SUB_TYPE")),
            "colour": _hex_rgb(info.get("RGB_1")),
            "colours": [c for c in (_hex_rgb(info.get("RGB_%d" % i)) for i in range(1, n + 1)) if c],
            "hotend_min": info.get("HOTEND_MIN_TEMP") or None, "hotend_max": info.get("HOTEND_MAX_TEMP") or None,
            "bed_temp": info.get("BED_TEMP") or None, "diameter": info.get("DIAMETER") or None,
            "weight": info.get("WEIGHT") or None, "sku": _none(info.get("SKU")), "uid": uid,
            "official": bool(info.get("OFFICIAL")),
        })
    return tags


def rfid_signature(tag):
    """What identifies a read: changes when a different spool/tag is read."""
    return tag and tuple(tag.get(k) for k in ("uid", "type", "vendor", "sub_type", "colour"))


def printer_options(task):
    """Print options the printer reports, as set now: {key: bool}."""
    found = {}
    for key, _, _, field, _ in PREFERENCES:
        if field in task:
            v = task[field]
            found[key] = any(v) if isinstance(v, list) else bool(v)
    return found


def summarize(status):
    """Compact state for the UI from a STATUS_OBJECTS query."""
    stats = status.get("print_stats") or {}
    sd = status.get("virtual_sdcard") or {}
    task = status.get("print_task_config") or {}
    active = (status.get("toolhead") or {}).get("extruder", "extruder")
    led = (status.get("led cavity_led") or {}).get("color_data")
    temps = []
    for i, name in enumerate(EXTRUDERS):
        e = status.get(name) or {}
        temps.append({"temp": e.get("temperature"), "target": e.get("target"), "active": name == active})
    purifier = status.get("purifier") or {}
    return {
        "state": stats.get("state") or (status.get("webhooks") or {}).get("state", "unknown"),
        "message": stats.get("message") or (status.get("webhooks") or {}).get("state_message", ""),
        "filename": stats.get("filename") or "",
        "progress": (status.get("display_status") or {}).get("progress", sd.get("progress")),
        "print_duration": stats.get("print_duration"),
        "total_duration": stats.get("total_duration"),
        "filament_used": stats.get("filament_used"),
        "layer": (stats.get("info") or {}).get("current_layer"),
        "total_layers": (stats.get("info") or {}).get("total_layer"),
        "speed_factor": (status.get("gcode_move") or {}).get("speed_factor"),
        "bed": {"temp": (status.get("heater_bed") or {}).get("temperature"),
                "target": (status.get("heater_bed") or {}).get("target")},
        "extruders": temps,
        "heads": describe_toolheads(task),
        "options": printer_options(task),
        "light": bool(led[0][3]) if led and led[0] and len(led[0]) > 3 else None,
        "purifier": {"fitted": purifier.get("power_detected"), "mode": purifier.get("mode")},
        "fan": (status.get("fan") or {}).get("speed"),
        "feed": feed_states(status),
        "rfid": rfid_tags(status.get("filament_detect")),
        "machine_state": _main_state((status.get("machine_state_manager") or {}).get("main_state")),
        "power_loss": bool(sd.get("pl_env_valid")) and not is_busy(stats.get("state")),
        "reprint": task.get("reprint_info") if sd.get("pl_env_valid") else None,
        "exceptions": (status.get("exception_manager") or {}).get("exceptions") or [],
    }


MAIN_STATES = ("IDLE", "PRINTING", "XYZ_OFFSET_CALIBRATE", "BED_LEVELING", "FLOW_CALIBRATION", "SHAPER_CALIBRATE",
               "UPGRADING", "ABNORMAL", "SCREWS_TILT_ADJUST", "AUTO_LOAD", "AUTO_UNLOAD", "MANUAL_LOAD",
               "PARK_POINT_MANUAL_CALIBRATION", "HOMING_ORIGIN_CALIBRATION")


def _main_state(value):
    """machine_state_manager.main_state arrives as an IntEnum value or its name."""
    if isinstance(value, int) and 0 <= value < len(MAIN_STATES):
        return MAIN_STATES[value]
    return str(value).rsplit(".", 1)[-1].upper() if value not in (None, "") else ""


def machine_busy(view):
    """Printing, or the U1 is in the middle of loading / calibrating / upgrading."""
    return is_busy(view.get("state")) or view.get("machine_state") not in ("", "IDLE")


CALIBRATIONS = {   # name -> command; all require an idle U1 (machine_state_manager gate)
    "bed_mesh": "AUTO_BED_MESH_CALIBRATE",
    "input_shaper": "SHAPER_CALIBRATE",
    "flow": "FLOW_CALIBRATE",
}


def feed_states(status):
    """Per toolhead feeder state ('load_finish', 'wait_insert', 'unload_doing', ...)."""
    merged = {}
    for name in ("filament_feed left", "filament_feed right"):
        merged.update(status.get(name) or {})
    out = []
    for t in range(TOOLHEADS):
        ch = merged.get("extruder%d" % t) or {}
        out.append({"state": ch.get("channel_state", ""), "detected": ch.get("filament_detected"),
                    "error": ch.get("channel_error", "")})
    return out


def load_command(head):
    """Screen-equivalent auto load for a toolhead (filament must be inserted in its inlet)."""
    return "AUTO_FEEDING EXTRUDER=%d LOAD=1" % int(head)


def unload_command(head):
    return "AUTO_FEEDING EXTRUDER=%d UNLOAD=1" % int(head)


def is_busy(state):
    return state in ("printing", "paused")


# --------------------------------------------------------------------- firmware

def detect_firmware(printer_info, ext_status=None):
    """{'kind': 'extended'|'stock', 'version': str}. Extended writes '-paxx12' into /etc/FULLVERSION,
    which Klipper reports as software_version; a Firmware Config API answer confirms it."""
    version = str((printer_info or {}).get("software_version") or "")
    extended = "paxx12" in version.lower() or isinstance(ext_status, dict)
    if isinstance(ext_status, dict) and ext_status.get("Version"):
        version = version or str(ext_status["Version"])
    return {"kind": "extended" if extended else "stock", "version": version}


# --------------------------------------------------------------------- mapping

def match_cost(f, h):
    """Lower is a better filament -> toolhead fit: exact type, then family, then colour."""
    s = colour_distance(f.get("colour"), h.get("colour"))
    if (f.get("type") or "").upper() != (h.get("type") or "").upper():
        s += 1e6 if material_family(f.get("type")) == material_family(h.get("type")) else 1e7
    return s


def auto_map(filaments, heads):
    """{filament index: toolhead}. Exact type, then family, then nearest colour; globally best
    pairs first so an early filament can't steal a later one's exact match. Shares heads when
    there are more filaments than loaded heads."""
    loaded = [h["index"] for h in heads if h["loaded"]]
    if not loaded:
        return {f["index"]: f["index"] % TOOLHEADS for f in filaments}

    score = match_cost
    mapping, taken = {}, set()
    pairs = sorted((score(f, heads[t]), f["index"], t) for f in filaments for t in loaded)
    for _, fi, t in pairs:
        if fi not in mapping and t not in taken:
            mapping[fi] = t
            taken.add(t)
    for f in filaments:
        if f["index"] not in mapping:
            mapping[f["index"]] = min(loaded, key=lambda t: (score(f, heads[t]), t))
    return mapping


def mapping_warnings(filaments, heads, mapping):
    """Human-readable problems with a mapping (empty head, other material)."""
    out = []
    by_index = {f["index"]: f for f in filaments}
    for fi, t in sorted(mapping.items()):
        f, h = by_index.get(fi), heads[t] if 0 <= t < len(heads) else None
        if f is None or h is None:
            continue
        if not h["loaded"]:
            out.append("Filament %d → T%d: toolhead is empty" % (fi + 1, t + 1))
        elif material_family(f.get("type")) != material_family(h["type"]):
            out.append("Filament %d (%s) → T%d loaded with %s" % (fi + 1, f.get("type"), t + 1, h["type"]))
    return out


def needs_dialog(filaments, heads, mapping, prefs_known, first_print):
    """True when the print setup pop-up should open in "auto" mode: something needs a decision."""
    if first_print or not prefs_known or mapping_warnings(filaments, heads, mapping):
        return True
    loaded = [h["index"] for h in heads if h["loaded"]]
    by_index = {f["index"]: f for f in filaments}
    used = [t for fi, t in mapping.items() if fi in by_index]
    if len(used) != len(set(used)):
        return True  # two filaments share a head
    best = []
    for f in filaments:
        if loaded:
            best.append(min(loaded, key=lambda t: (match_cost(f, heads[t]), t)))
            if (f.get("type") or "").upper() != (heads[mapping.get(f["index"], best[-1])].get("type") or "").upper():
                return True  # no exact type match
    return len(best) != len(set(best))  # two filaments best-match the same head


def preprint_script(mapping, prefs):
    """Commands Snapmaker Orca sends before a print starts (refused by firmware mid-print)."""
    lines = ["SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=%d MAP_EXTRUDER=%d" % (f, t) for f, t in sorted(mapping.items())]
    used = sorted(set(mapping.values()))
    lines.append("SET_PRINT_USED_EXTRUDERS EXTRUDERS=" + ",".join(map(str, used)))
    params = []
    for key, param, _, _, _ in PREFERENCES:
        value = prefs.get(key)
        if value is None:
            continue  # not offered: printer keeps its own setting
        if key == "unload_when_done":
            params.append("%s=[%s]" % (param, ",".join("1" if value and t in used else "0" for t in range(TOOLHEADS))))
        else:
            params.append("%s=%d" % (param, 1 if value else 0))
    if params:
        lines.append("SET_PRINT_PREFERENCES " + " ".join(params))
    return "\n".join(lines)


def _gcode_word(value):
    """Klipper param values can't hold spaces/semicolons; keep it readable."""
    return re.sub(r"[\s;=\"']+", "_", str(value or "").strip())[:32] or "Generic"


def filament_config_command(head, vendor, ftype, sub_type="", colour="#FFFFFF", force=False, soft=None):
    """SET_PRINT_FILAMENT_CONFIG for one toolhead. Official RFID spools need FORCE=1."""
    c = norm_colour(colour) or "#FFFFFF"
    parts = ["SET_PRINT_FILAMENT_CONFIG", "CONFIG_EXTRUDER=%d" % int(head),
             "VENDOR=%s" % _gcode_word(vendor), "FILAMENT_TYPE=%s" % _gcode_word(ftype).upper(),
             "FILAMENT_SUBTYPE=%s" % _gcode_word(sub_type or "Basic"),
             "FILAMENT_COLOR_RGBA=%sFF" % c[1:]]
    if soft is not None:
        parts.append("SOFT=%d" % int(soft))
    if force:
        parts.append("FORCE=1")
    return " ".join(parts)


# --------------------------------------------------------------------- top cover

def softening(ftype, vitrification=None):
    if vitrification not in (None, "", ORCA_DEFAULT_SOFTENING):
        try:
            return float(vitrification)
        except (TypeError, ValueError):
            pass
    t = (ftype or "").upper()
    return SOFTENING_BY_TYPE.get(t, SOFTENING_BY_TYPE.get(material_family(t), ORCA_DEFAULT_SOFTENING))


def purifier_mode(filaments):
    """Snapmaker Orca's chamber_cooling_mode: any used filament softening <= 50 C -> strong,
    else any <= 70 C -> weak, else keep warm. filaments: [{'type', 'softening'?, 'high_temp'?}]"""
    mode = "keep-warm"
    for f in filaments:
        if f.get("high_temp"):
            continue
        s = softening(f.get("type"), f.get("softening"))
        if s <= STRONG_COOL_MAX:
            return "strong"
        if s <= WEAK_COOL_MAX:
            mode = "weak"
    return mode
