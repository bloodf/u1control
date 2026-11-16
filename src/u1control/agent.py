"""The U1 as an OrcaSlicer printer agent ("Use printer agents", printer preset Printer Agent = u1control).
Pure functions and the print job, free of the `orca` module; plugin.py holds the agent class itself.

OrcaSlicer's Print dialog and Device tab speak Bambu JSON. This module turns a u1.summarize() view into the
`push_status` message OrcaSlicer's DeviceManager parses, the Device tab's commands into Moonraker calls, and a
Print from the dialog (PrintParams) into the same toolhead map and print options the U1 print setup sends.

Sources (OrcaSlicer v2.5.0): src/slic3r/Utils/MoonrakerPrinterAgent.cpp (MRA) and SnapmakerPrinterAgent.cpp (SPA),
src/slic3r/GUI/DeviceManager.cpp (DM) and SelectMachine.cpp (SM). Firmware: Snapmaker u1-klipper 2.1.0 source.

UNTESTED ON A PRINTER (built from source reading and fakes only, marked "untested" where used):
  - the dialog's tray ids arriving as 0..3 for this one-unit, four-tray push (SM get_ams_mapping_result);
  - support_flow_calibration / support_timelapse making the dialog show Flow calibration and Time-lapse (DM:3246, 3336);
  - SET_PRINT_PREFERENCES TIME_LAPSE_CAMERA / FLOW_CALIBRATE taking effect when the job starts this way.
SDCARD_PRINT_FILE_WITH_PARAMETERS (u1-klipper 2.1.0 virtual_sdcard.py:359) is not used: no read-only way to tell
whether older firmware has it, and the commands below work on every U1 firmware u1control supports.
"""

import json
import os
import re
import zipfile

import gcode
import u1
from moonraker import UploadCancelled as Cancelled  # noqa: F401  (raised by run_job and send_job)

UNSUPPORTED = -7010            # IPrinterAgent: "command not supported"
HAS_SDCARD_NORMAL = 1          # DevStorage.h SdcardState
CHAMBER_LIGHT = "chamber_light"
LIGHT_ON, LIGHT_OFF = "SET_LED LED=cavity_led WHITE=1 SYNC=0", "SET_LED LED=cavity_led WHITE=0 SYNC=0"

# Material -> OrcaFilamentLibrary family (MRA map_filament_type_to_generic_id). The id comes from the loaded
# system preset "Generic <family> @System", never hard-coded.
FILAMENT_FAMILIES = {
    "PLA": "PLA", "PLA-CF": "PLA-CF", "PLA SILK": "PLA Silk", "PLA HIGH SPEED": "PLA High Speed",
    "PLA MATTE": "PLA Matte", "ABS": "ABS", "ASA": "ASA", "PETG": "PETG", "PET": "PETG", "PCTG": "PCTG",
    "PA": "PA", "PA-CF": "PA-CF", "PPA-CF": "PPA-CF", "PPA-GF": "PPA-GF", "PC": "PC", "PVA": "PVA",
    "HIPS": "HIPS", "BVOH": "BVOH", "TPU": "TPU",
}
_SUB_TYPES = {"CF": "-CF", "GF": "-GF", "SNAPSPEED": " HIGH SPEED", "HS": " HIGH SPEED", "SILK": " SILK",
              "WOOD": " WOOD", "MATTE": " MATTE", "MARBLE": " MARBLE"}

# print_stats.state -> gcode_state (DM set_print_state); cancelled and error are FAILED, as MRA.
GCODE_STATE = {"standby": "IDLE", "printing": "RUNNING", "paused": "PAUSE", "complete": "FINISH",
               "cancelled": "FAILED", "error": "FAILED"}
PRINT_STAGE = {"printing": 1, "paused": 2, "complete": 3, "error": 4}   # MRA mc_print_stage


class JobError(RuntimeError):
    """A job refused or failed; the message is safe to show the user."""


# ---------------------------------------------------------------- status push

def tray_type(ftype, sub_type=""):
    """SPA combine_filament_type: 'PLA' + 'Matte' -> 'PLA MATTE'; brand sub-types ('Basic') add nothing."""
    base, sub = str(ftype or "").strip().upper(), str(sub_type or "").strip().upper()
    if not base:
        return "PLA"
    return base + _SUB_TYPES.get(sub, "")


def generic_preset_name(material):
    family = FILAMENT_FAMILIES.get(" ".join(str(material or "").split()).upper())
    return "Generic %s @System" % family if family else None


def _rgba(colour):
    c = u1.norm_colour(colour)
    return (c[1:] if c else "FFFFFF") + "FF"


def ams_block(heads, filament_id=None):
    """The four toolheads as one four-tray unit (MRA build_ams_payload: id "0", info "0002"), tray id = toolhead.
    filament_id(preset name) -> the filament_id of that system preset, or None."""
    trays, bits = [], 0
    for h in heads[:u1.TOOLHEADS]:
        tray = {"id": str(h["index"]), "tag_uid": "0000000000000000"}
        if h.get("loaded"):
            bits |= 1 << h["index"]
            material = tray_type(h.get("type"), h.get("sub_type"))
            preset = generic_preset_name(material)
            colour = _rgba(h.get("colour"))
            colours = [_rgba(c) for c in h.get("colours") or []] or [colour]
            tray.update(tray_type=material, tray_color=colour, cols=colours, ctype=1, remain=-1,
                        tray_info_idx=(filament_id(preset) if filament_id and preset else None) or "")
        else:
            tray.update(tray_info_idx="", tray_type="", tray_color="00000000", tray_slot_placeholder="1")
        trays.append(tray)
    return {"ams": [{"id": "0", "info": "0002", "tray": trays}], "ams_exist_bits": "1", "tray_exist_bits": "%X" % bits}


def _remaining_minutes(view):
    p, spent = view.get("progress"), view.get("print_duration")
    if not isinstance(p, (int, float)) or not isinstance(spent, (int, float)) or p <= 0.0 or p >= 1.0:
        return 0
    return int(spent * (1 - p) / p // 60)


def push_status(view, filament_id=None):
    """{"print": {...}} for on_local_message_fn, from u1.summarize()."""
    state = view.get("state") or "standby"
    gstate = GCODE_STATE.get(state, "RUNNING")
    if gstate == "IDLE" and view.get("machine_state") not in ("", "IDLE", None):
        gstate = "PREPARE"   # loading, calibrating, updating: DM counts PREPARE as printing, so no new job starts
    active = next((e for e in view.get("extruders") or [] if e.get("active")), {})
    bed = view.get("bed") or {}
    progress = view.get("progress") if isinstance(view.get("progress"), (int, float)) else 0
    fan = view.get("fan") if isinstance(view.get("fan"), (int, float)) else 0
    p = {
        "command": "push_status", "msg": 0, "support_mqtt_alive": True, "sequence_id": "0",
        "gcode_state": gstate, "mc_print_stage": PRINT_STAGE.get(state, 0),
        "mc_print_error_code": 0, "print_error": 0,
        # Both storage reports must say present or the dialog refuses LAN printing (MRA:2167-2184)
        "sdcard": True, "home_flag": HAS_SDCARD_NORMAL << 8,
        "support_send_to_sd": True,
        "support_bed_leveling": 1,          # SM: Auto Bed Leveling on/off -> task_bed_leveling
        "support_flow_calibration": True,   # SM: Flow Dynamics Calibration -> task_flow_cali (untested)
        "support_timelapse": True,          # SM: Timelapse -> task_record_timelapse (untested)
        "nozzle_temp_range": [0, 320], "bed_temp_range": [0, 110],
        "nozzle_temper": active.get("temp") or 0, "nozzle_target_temper": active.get("target") or 0,
        "bed_temper": bed.get("temp") or 0, "bed_target_temper": bed.get("target") or 0,
        "fan_gear": int(max(0.0, min(1.0, fan)) * 255 + 0.5),
        "subtask_name": view.get("filename") or "", "gcode_file": view.get("filename") or "",
        "mc_percent": int(round(max(0.0, min(1.0, progress)) * 100)),
        "mc_remaining_time": _remaining_minutes(view),
        "layer_num": int(view.get("layer") or 0), "total_layer_num": int(view.get("total_layers") or 0),
        "lights_report": [{"node": CHAMBER_LIGHT, "mode": "on" if view.get("light") else "off"}],
        **ams_block(view.get("heads") or [], filament_id),
    }
    return {"print": p}


def version_reply(firmware, product="Snapmaker U1"):
    return {"info": {"command": "get_version", "result": "success",
                     "module": [{"name": "ota", "sw_ver": firmware or "", "product_name": product}]}}


def access_code_reply(code):
    return {"system": {"command": "get_access_code", "access_code": code or ""}}


def gcode_reply(seq, param, ok):
    return {"print": {"command": "gcode_line", "sequence_id": seq, "param": param,
                      "result": "success" if ok else "failed"}}


# ---------------------------------------------------------------- Device tab commands

def parse_command(json_str):
    """A Device tab command -> {"kind", ..., "seq"}. Kinds: get_version, get_access_code, pushall, noop, pause,
    resume, stop, gcode (script), set_light (on), unsupported, invalid."""
    try:
        msg = json.loads(json_str)
    except (TypeError, ValueError):
        return {"kind": "invalid"}
    if not isinstance(msg, dict):
        return {"kind": "invalid"}
    for section in ("print", "system", "info", "pushing"):
        body = msg.get(section)
        if isinstance(body, dict) and "command" in body:
            break
    else:
        return {"kind": "unsupported", "seq": ""}
    name, seq = body["command"], str(body.get("sequence_id") or "")
    if not isinstance(name, str):
        return {"kind": "invalid"}
    out = None
    if (section, name) in (("info", "get_version"), ("system", "get_access_code"), ("pushing", "pushall")):
        out = {"kind": name}
    elif section == "pushing" and name in ("start", "stop"):
        out = {"kind": "pushall" if name == "start" else "noop"}
    elif section == "system" and name == "ledctrl" and body.get("led_node") == CHAMBER_LIGHT \
            and body.get("led_mode") in ("on", "off"):
        out = {"kind": "set_light", "on": body["led_mode"] == "on"}
    elif section == "print" and name in ("pause", "resume", "stop"):
        out = {"kind": name}
    elif section == "print" and name == "gcode_line" and isinstance(body.get("param"), str) \
            and body["param"].strip():
        out = {"kind": "gcode", "script": body["param"]}   # MRA: Klipper runs it as given
    return {**(out or {"kind": "unsupported"}), "seq": seq}


# ---------------------------------------------------------------- print job

def parse_list(text):
    if isinstance(text, list):
        return text
    try:
        value = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def job_mapping(ams_mapping, filaments, heads):
    """{filament index: toolhead} from PrintParams.ams_mapping (one tray id per project filament, -1 = none;
    tray id = toolhead here, untested on a printer). Filaments the dialog left unmapped get u1.auto_map's choice."""
    trays = parse_list(ams_mapping)
    auto = u1.auto_map(filaments, heads)
    mapping = {}
    for f in filaments:
        i = f["index"]
        t = trays[i] if i < len(trays) else -1
        ok = isinstance(t, int) and not isinstance(t, bool) and 0 <= t < u1.TOOLHEADS
        mapping[i] = t if ok else auto[i]
    return mapping


def job_prefs(offered, bed_leveling, flow_cali, timelapse):
    """The dialog's three boxes over the prefs u1control offers (the extended ones come from its settings)."""
    return {**offered, "bed_level": bool(bed_leveling), "flow_calibrate": bool(flow_cali),
            "time_lapse_camera": bool(timelapse)}


def upload_name(name, source):
    """MRA UploadFile::upload_name: a safe printer file name ending in .gcode."""
    name = os.path.basename(str(name or "")) or os.path.basename(str(source or "")) or "print"
    for ext in (".3mf", ".gcode"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
    name = re.sub(r'[\x00-\x1f\x7f"#;*/\\]', "_", name).lstrip(". ")
    return (name or "print")[:240] + ".gcode"


def plate_gcode(path, plate_index, out):
    """The plate's G-code from a .gcode.3mf (Metadata/plate_<n>.gcode) into the open binary file `out`."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        wanted = "Metadata/plate_%d.gcode" % max(1, int(plate_index or 1))
        if wanted not in names:
            plates = [n for n in names if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
            if len(plates) != 1:
                raise JobError("no G-code for plate %s in %s" % (plate_index, os.path.basename(path)))
            wanted = plates[0]
        with z.open(wanted) as src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    return
                out.write(chunk)


def _copy_job(path, plate_index, work_dir):
    """The job's G-code (from a .gcode or a .gcode.3mf) in a work file the caller removes. work_dir: the plugin's
    storage folder; OrcaSlicer denies tempfile.* off the main thread, and the storage folder needs no grant."""
    os.makedirs(work_dir, exist_ok=True)
    tmp = os.path.join(work_dir, "job-%s.gcode" % os.urandom(6).hex())
    try:
        with open(tmp, "wb") as out:
            if path.lower().endswith(".3mf"):
                plate_gcode(path, plate_index, out)
            else:
                with open(path, "rb") as src:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
        return tmp
    except BaseException:
        _remove(tmp)
        raise


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def prepare_gcode(path, plate_index, options, view, ams_mapping, version, work_dir):
    """Read the job, check it against the toolheads and apply u1control's G-code fixes into a temp file.
    Returns (temp path, mapping, filaments). Raises JobError: not a U1 print, or the mapping has warnings.
    view=None (Send, no print starts): fixes only, no toolhead check."""
    tmp = _copy_job(path, plate_index, work_dir)
    try:
        lines, newline = gcode.read(tmp)
        cfg = gcode.settings(lines)
        if not gcode.is_u1(cfg):
            raise JobError("this G-code was not sliced for a Snapmaker U1")
        mapping, filaments, heads = None, gcode.filaments(lines, cfg), None
        if view is not None:
            heads = view["heads"]
            mapping = job_mapping(ams_mapping, filaments, heads)
            problems = u1.mapping_warnings(filaments, heads, mapping)
            if problems:
                raise JobError("; ".join(problems) + ". Pick other slots in the print dialog, or load the filament.")
        lines, _ = gcode.process(lines, cfg, options, mapping, heads, version)
        gcode.write(tmp, lines, newline)
        return tmp, mapping, filaments
    except BaseException:
        _remove(tmp)
        raise


def send_job(client, path, name, plate_index, options, version, work_dir, progress=None, cancelled=None):
    """Send (upload only, no print starts): the G-code fixes, then the upload. Returns the printer file name."""
    tmp, _, _ = prepare_gcode(path, plate_index, options, None, None, version, work_dir)
    try:
        filename = upload_name(name, path)
        client.upload(tmp, filename, progress=progress, cancelled=cancelled)
        return filename
    finally:
        _remove(tmp)


def run_job(client, path, name, plate_index, ams_mapping, options, offered_prefs, task, version, work_dir,
            progress=None, cancelled=None, stage=None):
    """Print from the dialog: refuse a busy U1, map and fix the G-code, upload, send the toolhead map and print
    options (u1.preprint_script), then start the print. task: {"bed_leveling", "flow_cali", "timelapse"}.
    offered_prefs(view) -> the prefs u1control offers for this printer. Returns {"filename", "mapping",
    "filaments", "script"}. Raises JobError, Cancelled or moonraker.PrinterError."""
    view = u1.summarize(client.query(u1.STATUS_OBJECTS))
    if u1.machine_busy(view):
        raise JobError("the U1 is busy (%s); wait for it to finish first"
                       % (view["machine_state"] or view["state"]).lower())
    tmp, mapping, filaments = prepare_gcode(path, plate_index, options, view, ams_mapping, version, work_dir)
    try:
        prefs = job_prefs(offered_prefs(view), task.get("bed_leveling"), task.get("flow_cali"), task.get("timelapse"))
        script = u1.preprint_script(mapping, prefs)
        filename = upload_name(name, path)
        if stage:
            stage("upload")
        client.upload(tmp, filename, progress=progress, cancelled=cancelled)
        if cancelled and cancelled():
            raise Cancelled()
        if stage:
            stage("start")
        client.gcode(script)
        client.print_start(filename)
        return {"filename": filename, "mapping": mapping, "filaments": filaments, "script": script}
    finally:
        _remove(tmp)
