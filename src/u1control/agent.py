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
import urllib.parse
import zipfile

import gcode
import u1
from i18n import tr
from moonraker import UploadCancelled as Cancelled  # noqa: F401  (raised by run_job and send_job)

UNSUPPORTED = -7010            # IPrinterAgent: "command not supported"
HAS_SDCARD_NORMAL = 1          # DevStorage.h SdcardState
# home_flag bit 16 = is_support_pa_calibration (DM parse_home_flag). DM parses home_flag after support_flow_calibration
# in the same push and lets the bit win (DM:1216 over DM:3277), so without it the dialog's Flow calibration box hides.
HAS_PA_CALIBRATION = 1 << 16
# The Snapmaker U1's model_id in OrcaSlicer's profiles (resources/profiles/Snapmaker/machine/Snapmaker U1.json). It is
# the device's printer_type (DevManager on_machine_alive reads ssdp dev_type), which the Print dialog compares with the
# preset's model_id (DevConfigUtil is_printer_model_compatible); MRA sends the preset's model_id the same way. The
# plugin API doesn't show a preset's model_id, so it is written here.
U1_MODEL_ID = "797581801"
CHAMBER_LIGHT = "chamber_light"
# The stock firmware's camera picture, renewed only for ~60 s after camera.start_monitor (u1control's own camera does the
# same keepalive, service.py CAMERA_KEEPALIVE)
STOCK_CAMERA = "/server/files/camera/monitor.jpg"
MONITOR_EVERY = 50.0    # s between camera.start_monitor requests while the Device tab shows the camera
MONITOR_WATCHED = 10.0  # s since the Device tab last asked for the camera URL that still count as "showing it"
# Device tab speed level (DevDefs.h DevPrintingSpeedLevel: silent, standard, sport, ludicrous) -> M220 percent, as Bambu's
SPEED_PERCENT = {1: 50, 2: 100, 3: 124, 4: 166}
LIGHT_ON, LIGHT_OFF = "SET_LED LED=cavity_led WHITE=1 SYNC=0", "SET_LED LED=cavity_led WHITE=0 SYNC=0"

# Material -> OrcaFilamentLibrary family (MRA map_filament_type_to_generic_id).
FILAMENT_FAMILIES = {
    "PLA": "PLA", "PLA-CF": "PLA-CF", "PLA SILK": "PLA Silk", "PLA HIGH SPEED": "PLA High Speed",
    "PLA MATTE": "PLA Matte", "ABS": "ABS", "ASA": "ASA", "PETG": "PETG", "PET": "PETG", "PCTG": "PCTG",
    "PA": "PA", "PA-CF": "PA-CF", "PPA-CF": "PPA-CF", "PPA-GF": "PPA-GF", "PC": "PC", "PVA": "PVA",
    "HIPS": "HIPS", "BVOH": "BVOH", "TPU": "TPU",
}
# filament_id of each "Generic <family> @System" preset in OrcaSlicer's OrcaFilamentLibrary (resources/profiles/
# OrcaFilamentLibrary/filament, resolved through "inherits", OrcaSlicer main 32f6db87). OrcaSlicer's plugin API
# doesn't show a preset's filament_id, so they are listed here. An id OrcaSlicer doesn't know still works: its sync
# from AMS then takes "Generic <tray_type>" (PresetBundle::sync_ams_list); only an empty one becomes "Generic PLA".
GENERIC_IDS = {
    "ABS": "OFY9muEs", "ASA": "OFLPAxz3", "BVOH": "OFo2UF2C", "CoPE": "OFjt9en1", "EVA": "OFCD8qiU",
    "HIPS": "OFsFon5l", "PA": "OFg8ndtj", "PA-CF": "OFQLcbps", "PC": "OFLakOUI", "PCTG": "OFu1evlr",
    "PE": "OFPklMI1", "PETG": "OFYPdQJh", "PHA": "OF74KeQR", "PLA": "OFDSrzZ8", "PLA High Speed": "OFmpMwxS",
    "PLA Matte": "OFmY0l6t", "PLA Silk": "OFesA6rF", "PLA-CF": "OFWbdGsC", "PP": "OF1UNk9P", "PPA-CF": "OF8tPByX",
    "PPA-GF": "OF8Tlg47", "PVA": "OFDvXujf", "SBS": "OFhQfUQY", "TPU": "OFgbpcy9",
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


def material_family(material):
    """OrcaFilamentLibrary family of a material, or None: the table, else the longest family named in it as a
    whole word."""
    text = " ".join(str(material or "").split()).upper()
    return FILAMENT_FAMILIES.get(text) or next(
        (FILAMENT_FAMILIES[k] for k in sorted(FILAMENT_FAMILIES, key=len, reverse=True)
         if re.search(r"(?<![A-Z0-9])%s(?![A-Z0-9])" % re.escape(k), text)), None)


def generic_filament_id(material):
    """filament_id of the material's "Generic <family> @System" preset, or ""."""
    return GENERIC_IDS.get(material_family(material), "")


def _rgba(colour):
    c = u1.norm_colour(colour)
    return (c[1:] if c else "FFFFFF") + "FF"


def ams_block(heads, preferred=None):
    """The four toolheads as one four-tray unit (MRA build_ams_payload: id "0", info "0002"), tray id = toolhead.
    tray_info_idx is what OrcaSlicer's AMS sync matches presets on (filament_id): preferred(head) first (the
    Spooler preset of the head's Spoolman spool, or ""), else the Generic preset of the head's material."""
    trays, bits = [], 0
    for h in heads[:u1.TOOLHEADS]:
        tray = {"id": str(h["index"]), "tag_uid": "0000000000000000"}
        if h.get("loaded"):
            bits |= 1 << h["index"]
            material = tray_type(h.get("type"), h.get("sub_type"))
            colour = _rgba(h.get("colour"))
            colours = [_rgba(c) for c in h.get("colours") or []] or [colour]
            tray.update(tray_type=material, tray_color=colour, cols=colours, ctype=1, remain=-1,
                        tray_info_idx=(preferred(h) if preferred else "") or generic_filament_id(material))
        else:
            tray.update(tray_info_idx="", tray_type="", tray_color="00000000", tray_slot_placeholder="1")
        trays.append(tray)
    # Nested as DevFilaSystemParser::ParseV1_0 reads it: print.ams.ams, print.ams.tray_exist_bits (MRA build_ams_payload)
    return {"ams": {"ams": [{"id": "0", "info": "0002", "tray": trays}], "ams_exist_bits": "1",
                    "tray_exist_bits": "%X" % bits}}


def _remaining_minutes(view):
    p, spent = view.get("progress"), view.get("print_duration")
    if not isinstance(p, (int, float)) or not isinstance(spent, (int, float)) or p <= 0.0 or p >= 1.0:
        return 0
    return int(spent * (1 - p) / p // 60)


def push_status(view, preferred=None):
    """{"print": {...}} for on_local_message_fn, from u1.summarize(); preferred as ams_block."""
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
        "sdcard": True, "home_flag": HAS_SDCARD_NORMAL << 8 | HAS_PA_CALIBRATION,
        "support_send_to_sd": True,
        "support_bed_leveling": 1,          # SM: Auto Bed Leveling on/off -> task_bed_leveling
        "support_flow_calibration": True,   # SM: Flow Dynamics Calibration -> task_flow_cali (untested)
        "support_timelapse": True,          # SM: Timelapse -> task_record_timelapse (untested)
        "nozzle_temp_range": [0, u1.HOTEND_MAX], "bed_temp_range": [0, u1.BED_MAX],
        "nozzle_temper": active.get("temp") or 0, "nozzle_target_temper": active.get("target") or 0,
        "bed_temper": bed.get("temp") or 0, "bed_target_temper": bed.get("target") or 0,
        "fan_gear": int(max(0.0, min(1.0, fan)) * 255 + 0.5),
        "subtask_name": view.get("filename") or "", "gcode_file": view.get("filename") or "",
        "mc_percent": int(round(max(0.0, min(1.0, progress)) * 100)),
        "mc_remaining_time": _remaining_minutes(view),
        "layer_num": int(view.get("layer") or 0), "total_layer_num": int(view.get("total_layers") or 0),
        "spd_lvl": speed_level(view.get("speed_factor")),
        "lights_report": [{"node": CHAMBER_LIGHT, "mode": "on" if view.get("light") else "off"}],
        **ams_block(view.get("heads") or [], preferred),
    }
    if isinstance(view.get("chamber"), (int, float)):   # DevConfig: the Device tab shows it only when told to
        p.update(chamber_temper=view["chamber"], support_chamber_temp_display=True)
    return {"print": p}


def speed_level(factor):
    """The Device tab speed level nearest a gcode_move speed_factor (1.0 = 100 %); standard when unknown."""
    if not isinstance(factor, (int, float)) or isinstance(factor, bool):
        return 2
    return min(SPEED_PERCENT, key=lambda lvl: (abs(factor * 100 - SPEED_PERCENT[lvl]), lvl != 2))


def camera_source(webcams, base):
    """(CameraStreamMode name, absolute URL) for the Device tab, from a /server/webcams/list result: the first enabled
    webcam's MJPEG or RTSP stream (OrcaSlicer plays those), else its snapshot; with no webcam (the stock firmware lists
    none) the stock camera picture, which needs camera.start_monitor to stay current (monitor_due)."""
    def absolute(url):
        return urllib.parse.urljoin(base.rstrip("/") + "/", url.strip()) if isinstance(url, str) and url.strip() else ""
    cams = webcams.get("webcams") if isinstance(webcams, dict) else None
    for cam in cams if isinstance(cams, list) else []:
        if not isinstance(cam, dict) or not cam.get("enabled", True):
            continue
        stream, service = absolute(cam.get("stream_url")), str(cam.get("service") or "").lower()
        if stream.lower().startswith("rtsp://"):
            return "RTSP", stream
        if stream and (not service or service.startswith("mjpegstreamer")):
            return ("HTTPS" if stream.lower().startswith("https://") else "HTTP"), stream
        if absolute(cam.get("snapshot_url")):
            return "HTTP_SNAPSHOT", absolute(cam.get("snapshot_url"))
    return "HTTP_SNAPSHOT", absolute(STOCK_CAMERA)


def monitor_due(now, watched_at, requested_at):
    """Whether to send camera.start_monitor now: the Device tab showed the stock camera picture in the last
    MONITOR_WATCHED s, and the last request (None: never) is MONITOR_EVERY s old."""
    return watched_at is not None and now - watched_at <= MONITOR_WATCHED and (
        requested_at is None or now - requested_at >= MONITOR_EVERY)


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
    resume, stop, gcode (script; also the speed level, as M220), set_light (on), unsupported, invalid."""
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
    elif section == "print" and name == "print_speed" and str(body.get("param")) in ("1", "2", "3", "4"):
        out = {"kind": "gcode", "script": "M220 S%d" % SPEED_PERCENT[int(body["param"])]}
    elif section == "print" and name == "gcode_line" and isinstance(body.get("param"), str) \
            and body["param"].strip():
        out = {"kind": "gcode", "script": body["param"]}   # MRA: Klipper runs it as given (guarded_line excepted)
    return {**(out or {"kind": "unsupported"}), "seq": seq}


# What the Device tab sends to home, heat and cool (IPrinterAgent.hpp command_go_home, command_set_bed and
# command_set_nozzle, DevFan.cpp command_control_fan): G-code lines, as this agent reports no MQTT control (DM "fun").
GUARDED = {"G28": None, "M104": u1.HOTEND_MAX, "M140": u1.BED_MAX, "M106": 255}   # code -> highest S


def guarded_line(script):
    """[(line, code, {letter: number or None})] for the Device tab home, heater and fan lines in script (any line of
    it, comments dropped); empty when there are none and the script runs as given."""
    out = []
    for line in str(script or "").splitlines():
        words = line.split(";", 1)[0].upper().split()
        if not words or words[0] not in GUARDED:
            continue
        args = {}
        for w in words[1:]:
            try:
                args[w[0]] = float(w[1:]) if len(w) > 1 else None
            except ValueError:
                args[w[0]] = None
        out.append((" ".join(line.split()), words[0], args))
    return out


def line_refusal(script, view):
    """Why the Device tab may not run the guarded_line lines of script now (translated), or None. Only while the U1
    is idle, as the tab's commands; heater targets 0..the U1 limit, fan 0..255, toolhead T0..T3."""
    lines = guarded_line(script)
    if lines and u1.machine_busy(view):
        return tr("the U1 is busy (%s)") % (view.get("machine_state") or view.get("state") or "").lower()
    for text, code, args in lines:
        top, s, t = GUARDED[code], args.get("S"), args.get("T", 0)
        if top is not None and (s is None or not 0 <= s <= top):
            return tr("%s out of range (0 to %d)") % (text, top)
        if code == "M104" and (t is None or t != int(t) or not 0 <= t < u1.TOOLHEADS):
            return tr("bad toolhead")
    return None


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
    """The print options for a job from the dialog. OrcaSlicer's dialog starts every box ticked (SM:3205-3238
    load_option_vals), so a box alone would override U1 Control's settings on every plain print. Each of the three
    is on only when its box is ticked AND U1 Control's own setting (offered) is on: the setting is the default,
    unticking the box turns it off for this print. The extended options come from offered unchanged."""
    boxes = {"bed_level": bed_leveling, "flow_calibrate": flow_cali, "time_lapse_camera": timelapse}
    return {**offered, **{k: bool(v) and bool(offered.get(k)) for k, v in boxes.items()}}


def upload_name(name, source):
    """MRA UploadFile::upload_name: a safe printer file name ending in .gcode."""
    name = os.path.basename(str(name or "")) or os.path.basename(str(source or "")) or "print"
    for ext in (".3mf", ".gcode"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
    name = re.sub(r'[\x00-\x1f\x7f"#;*/\\]', "_", name).lstrip(". ")
    return (name or "print")[:240] + ".gcode"


def sweep_jobs(work_dir):
    """Remove job-*.gcode work files left by an earlier session (OrcaSlicer closed mid-job). Returns the count."""
    try:
        names = os.listdir(work_dir)
    except OSError:
        return 0
    stale = [n for n in names if re.fullmatch(r"job-[0-9a-f]+\.gcode", n)]
    for n in stale:
        _remove(os.path.join(work_dir, n))
    return len(stale)


def plate_gcode(path, plate_index, out):
    """The plate's G-code from a .gcode.3mf (Metadata/plate_<n>.gcode) into the open binary file `out`."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        wanted = "Metadata/plate_%d.gcode" % max(1, int(plate_index or 1))
        if wanted not in names:
            plates = [n for n in names if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
            if len(plates) != 1:
                raise JobError(tr("no G-code for plate %s in %s") % (plate_index, os.path.basename(path)))
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


def prepare_gcode(path, plate_index, options, view, ams_mapping, version, work_dir, prefs=None, choose=None):
    """Read the job, check it against the toolheads and apply u1control's G-code fixes into a temp file.
    Returns (temp path, mapping, filaments, choice). Raises JobError: not a U1 print, or the mapping has warnings.
    view=None (Send, no print starts): fixes only, no toolhead check.
    choose(view, filaments, mapping, prefs, lines, cfg) -> None (no print setup shown) or the print setup's answer
    {"map", "prefs", "purifier", "heads", "commands"} (its warnings already acknowledged and checked; the top-cover
    fan speeds in prefs go into the G-code); raises Cancelled."""
    tmp = _copy_job(path, plate_index, work_dir)
    try:
        lines, newline = gcode.read(tmp)
        cfg = gcode.settings(lines)
        if not gcode.is_u1(cfg):
            raise JobError(tr("this G-code was not sliced for a Snapmaker U1"))
        mapping, filaments, heads, choice = None, gcode.filaments(lines, cfg), None, None
        done = setup_done(lines)
        if view is not None:
            heads = view["heads"]
            mapping = job_mapping(ams_mapping, filaments, heads)
            choice = choose(view, filaments, mapping, prefs, lines, cfg) if choose and not done else None
            if choice:
                mapping, heads = choice["map"], choice.get("heads") or heads
                fans = {k: choice["prefs"][k] for k in u1.COVER_FANS if k in choice["prefs"]}
                options = {**options, **fans, "purifier": choice["purifier"]}
            else:
                problems = u1.mapping_warnings(filaments, heads, mapping)
                if problems:
                    raise JobError(tr("%s. Pick other slots in the print dialog, or load the filament.") % "; ".join(problems))
        if not done:
            lines, _ = gcode.process(lines, cfg, options, mapping, heads, version)
            gcode.write(tmp, lines + ([SETUP_DONE] if choice else []), newline)
        return tmp, mapping, filaments, choice
    except BaseException:
        _remove(tmp)
        raise


HEAD_FACTS = ("loaded", "type", "colour", "vendor", "official")   # as plugin._still_valid
SETUP_DONE = gcode.MARK + " print setup done"   # last line of G-code that went through print setup


def setup_done(lines):
    """True when this G-code already went through U1 print setup (the slicing pipeline or the printer agent):
    a second pass shows no window, sends no second pre-print script and changes nothing in it."""
    return any(line.strip() == SETUP_DONE for line in lines[-50:])


def _busy_reason(view):
    return tr("the U1 is busy (%s); wait for it to finish first") % (view["machine_state"] or view["state"]).lower()


def send_job(client, path, name, plate_index, options, version, work_dir, progress=None, cancelled=None):
    """Send (upload only, no print starts): the G-code fixes, then the upload. Returns the printer file name.
    Refuses a name the U1 is printing now: the upload would replace the running print's file."""
    filename = upload_name(name, path)
    view = u1.summarize(client.query(u1.STATUS_OBJECTS))
    if u1.is_busy(view["state"]) and view["filename"].lstrip("/") == filename:
        raise JobError(tr("the U1 is printing %s now; send it under another name or wait") % filename)
    tmp, _, _, _ = prepare_gcode(path, plate_index, options, None, None, version, work_dir)
    try:
        client.upload(tmp, filename, progress=progress, cancelled=cancelled)
        return filename
    finally:
        _remove(tmp)


def run_job(client, path, name, plate_index, ams_mapping, options, offered_prefs, task, version, work_dir,
            progress=None, cancelled=None, stage=None, choose=None):
    """Print from the dialog: refuse a busy U1, map (and ask, see prepare_gcode's choose) and fix the G-code,
    upload, send the toolhead map and print options (u1.preprint_script), then start the print.
    task: {"bed_leveling", "flow_cali", "timelapse"}. offered_prefs(view) -> the prefs u1control offers for this
    printer. Returns {"filename", "mapping", "filaments", "script"}. Raises JobError, Cancelled or
    moonraker.PrinterError."""
    view = u1.summarize(client.query(u1.STATUS_OBJECTS))
    if u1.machine_busy(view):
        raise JobError(_busy_reason(view))
    prefs = job_prefs(offered_prefs(view), task.get("bed_leveling"), task.get("flow_cali"), task.get("timelapse"))
    tmp, mapping, filaments, choice = prepare_gcode(path, plate_index, options, view, ams_mapping, version, work_dir,
                                                    prefs, choose)
    try:
        if choice:
            prefs, view = choice["prefs"], {**view, "heads": choice.get("heads") or view["heads"]}
            if cancelled and cancelled():
                raise Cancelled()
            now = u1.summarize(client.query(u1.STATUS_OBJECTS))   # the print setup may have stayed open a while
            if u1.machine_busy(now):
                raise JobError(_busy_reason(now))
        script = u1.preprint_script(mapping, prefs, choice.get("commands", False) if choice else False)
        filename = upload_name(name, path)
        if stage:
            stage("upload")
        client.upload(tmp, filename, progress=progress, cancelled=cancelled)
        if cancelled and cancelled():
            raise Cancelled()
        after = u1.summarize(client.query(u1.STATUS_OBJECTS))   # the upload can take a while: check again
        if u1.machine_busy(after):
            raise JobError(tr("%s; the file is on the U1, nothing was started") % _busy_reason(after))
        for t in sorted(set(mapping.values())):
            if any(view["heads"][t].get(k) != after["heads"][t].get(k) for k in HEAD_FACTS):
                raise JobError(tr("T%d changed during the upload; the file is on the U1, nothing was started. "
                               "Print again.") % (t + 1))
        if stage:
            stage("start")
        client.gcode(script)
        if cancelled and cancelled():
            raise Cancelled()
        client.print_start(filename)
        return {"filename": filename, "mapping": mapping, "filaments": filaments, "script": script, "choice": choice}
    finally:
        _remove(tmp)
