"""Exported G-code reading and U1 post-processing.

Every transform is idempotent (safe to run twice on the same file) and leaves a
'; u1control:' marker so the result is auditable.
"""

import base64
import contextlib
import os
import re

import u1

MARK = "; u1control:"
SETTING_RE = re.compile(r"^;\s*([A-Za-z0-9_\[\]() ]+?)\s*=\s*(.*?)\s*$")
TOOL_RE = re.compile(r"^\s*T(\d+)\s*(;.*)?$")
THUMB_RE = re.compile(r"^;\s*thumbnail(?:_PNG)? begin (\d+)x(\d+) (\d+)")
PRINT_START_RE = re.compile(r"^\s*PRINT_START\b", re.I)
PURIFIER_RE = re.compile(r"^\s*SET_PURIFIER_MODE\b", re.I)
CHAMBER_WAIT_RE = re.compile(r"^\s*WAIT_CHAMBER_TEMP\b", re.I)
BED_WAIT_RE = re.compile(r"^\s*M190\b", re.I)
MESH_RE = re.compile(r"^\s*BED_MESH_CALIBRATE\b(.*)$", re.I)
PROBING_RE = re.compile(r"^\s*(G28\b[^;]*\bZ|DETECT_BED_PLATE\b|BED_MESH_CALIBRATE\b)", re.I)
WHOLE_MESH = "BED_MESH_CALIBRATE PROBE_COUNT=11,11"   # Snapmaker Orca's U1 line
CHAMBER_WAIT = "WAIT_CHAMBER_TEMP TIMEOUT=180"


def read(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text[:65536] else "\n"
    return text.split(newline), newline


def write(path, lines, newline):
    """Write beside the file, then swap it in: a failure halfway never leaves a cut-off G-code behind."""
    tmp = path + ".u1control.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(newline.join(lines))
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def settings(lines):
    """Orca's '; key = value' config block (at the end of the file) as a dict."""
    out = {}
    for line in reversed(lines[-6000:]):
        m = SETTING_RE.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2))
    for line in lines[:400]:  # header block: estimated time, filament totals
        m = SETTING_RE.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2))
    return out


def split_list(value, numeric=False):
    """';'-separated list. Numeric fields (weights, softening) may use ',' instead; names never do."""
    if value is None:
        return []
    value = value.strip().strip('"')
    sep = "," if numeric and ";" not in value else ";"
    return [v.strip().strip('"') for v in value.split(sep)] if value else []


def is_u1(cfg):
    text = " ".join(cfg.get(k, "") for k in ("printer_model", "printer_settings_id", "inherits"))
    return bool(re.search(r"snapmaker\s*u1|\bu1\b", text, re.I))


def used_tools(lines):
    """Filament indices the print uses, in first-use order."""
    seen = []
    for line in lines:
        m = line[:1] in "T \t" and TOOL_RE.match(line)   # the prefix test skips the millions of moves cheaply
        if m:
            t = int(m.group(1))
            if t not in seen and t < u1.MAX_FILAMENTS:
                seen.append(t)
    return seen


def filaments(lines, cfg):
    """[{index, type, colour, softening, weight}] for the filaments the print uses."""
    types = split_list(cfg.get("filament_type"))
    colours = split_list(cfg.get("filament_colour"))
    soft = split_list(cfg.get("temperature_vitrification"), numeric=True)
    weights = split_list(cfg.get("filament used [g]") or cfg.get("filament_used_g"), numeric=True)
    names = split_list(cfg.get("filament_settings_id"))
    used = used_tools(lines) or list(range(min(len(types), u1.TOOLHEADS) or 1))
    out = []
    for i in used:
        out.append({
            "index": i,
            "type": u1._at(types, i, "PLA"),
            "colour": u1.norm_colour(u1._at(colours, i)),
            "softening": _num(u1._at(soft, i)),
            "weight": _num(u1._at(weights, i)),
            "name": u1._at(names, i, ""),
        })
    return out


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def thumbnail(lines):
    """Largest embedded PNG preview, base64 (None if absent)."""
    best, best_area, cur, area = None, 0, None, 0
    for line in lines[:8000]:
        m = THUMB_RE.match(line)
        if m:
            cur, area = [], int(m.group(1)) * int(m.group(2))
            continue
        if cur is not None:
            if re.match(r"^;\s*thumbnail(?:_PNG)? end", line):
                if area > best_area:
                    best, best_area = "".join(cur), area
                cur = None
            else:
                cur.append(line.lstrip("; ").strip())
    if best:
        try:
            base64.b64decode(best, validate=True)
        except ValueError:
            return None
    return best


def summary(lines, cfg):
    return {
        "time": cfg.get("estimated printing time (normal mode)") or cfg.get("total estimated time", ""),
        "weight": cfg.get("total filament weight [g]") or cfg.get("total filament used [g]", ""),
        "layers": cfg.get("total layer number") or cfg.get("total_layer_count", ""),
        "printer": cfg.get("printer_settings_id", ""),
        "process": cfg.get("print_settings_id", ""),
        "plate": cfg.get("curr_bed_type", ""),
    }


# --------------------------------------------------------------------- transforms

def _head_end(lines):
    """The index of the first layer line (len(lines) without one): the start G-code is before it."""
    return next((i for i, l in enumerate(lines) if l[:1] != "G" and LAYER_RE.match(l)), len(lines))


def _start_index(lines):
    for i, line in enumerate(lines):
        if PRINT_START_RE.match(line):
            return i
    return None


LAYER_RE = re.compile(r"^\s*;\s*(CHANGE_LAYER|LAYER_CHANGE)\s*$")
WAS_RE = re.compile(r"\(was: (.*)\)$")


def ensure_purifier(lines, mode, fans=None):
    """Make the start G-code's top-cover purifier line match mode ('auto' resolved by caller; 'off' leaves
    the file as sliced). The profile's first SET_PURIFIER_MODE before the first layer (upstream 2.5's U1
    profile has one in its start G-code) is replaced by ours, with a '; u1control: purifier <mode> (was: ...)'
    marker; without one ours goes after PRINT_START. Re-running first restores what the marker recorded.
    fans: {"exhaust_fan"/"inner_fan": percent} sets the mode's fan speed (u1.purifier_command)."""
    marker = MARK + " purifier"
    out, ours_next, was = [], False, None
    for line in (lines if any(l.startswith(marker) for l in lines[:_head_end(lines)]) else ()):
        # undo an earlier run (its marker is in the start G-code) so the result only depends on the file and mode
        if line.startswith(marker):
            m = WAS_RE.search(line)
            ours_next, was = True, m.group(1) if m else None
            continue
        if ours_next:
            ours_next = False
            if PURIFIER_RE.match(line):
                if was:
                    out.append(was)
                continue
        out.append(line)
    out = out or lines
    if mode == "off" or mode not in u1.PURIFIER:
        return out
    cmd = u1.purifier_command(mode, fans)
    limit = next((i for i, l in enumerate(out) if LAYER_RE.match(l)), len(out))
    first = next((i for i in range(limit) if PURIFIER_RE.match(out[i])), None)
    if first is not None:
        return out[:first] + ["%s purifier %s (was: %s)" % (MARK, mode, out[first].strip()), cmd] + out[first + 1:]
    i = _start_index(out)
    if i is None:
        return out
    return out[:i + 1] + [MARK + " purifier " + mode, cmd] + out[i + 1:]


def ensure_chamber_wait(lines):
    if any(CHAMBER_WAIT_RE.match(l) for l in lines):
        return lines
    for i, line in enumerate(lines):
        if BED_WAIT_RE.match(line):
            return lines[:i + 1] + [MARK + " chamber wait", CHAMBER_WAIT] + lines[i + 1:]
    return lines


def whole_bed_mesh(lines):
    """Replace adaptive mesh lines with Snapmaker Orca's whole-bed 11x11 probe, keeping Z_OFFSET.
    The U1 saves every probed mesh as 'default', so a small adaptive patch would be reused by
    the next print that skips leveling."""
    out = lines
    for i in reversed([i for i, l in enumerate(lines) if l[:1] in "Bb \t" and MESH_RE.match(l)]):
        m = MESH_RE.match(lines[i])
        if "mesh_min" in m.group(1).lower():
            z = re.search(r"\bZ_OFFSET=(-?[\d.]+)", m.group(1), re.I)
            out = out if out is not lines else list(lines)
            out[i:i + 1] = [MARK + " whole-bed mesh (was: %s)" % lines[i].strip(),
                            WHOLE_MESH + (" Z_OFFSET=%s" % z.group(1) if z else "")]
    return out


SEQUENCE_RE = re.compile(r"^;\s*print_sequence\s*=?\s*(.*?)\s*$")
MAX_HEIGHT_RE = re.compile(r"^;\s*max_print_height\s*=?\s*([\d.]+)")
TOOL_CHANGE_RE = re.compile(r"^;\s*Change Tool\d+\s*->")
LIFT_RE = re.compile(r"^G1 Z([\d.]+) F600\s*$")


def _print_facts(lines, cfg=None):
    """(print_sequence is 'by object', max_print_height or None) from the '; key = value' comments anywhere in the file.
    A print by layer per cfg (settings(lines): the config block, last in the file) needs no height and no second read
    of a file with millions of lines."""
    if cfg and cfg.get("print_sequence") not in (None, "by object", "by_object"):
        return False, None
    by_object, max_height = False, None
    for line in lines:
        m = SEQUENCE_RE.match(line)
        if m:
            by_object = m.group(1) in ("by object", "by_object")
        m = MAX_HEIGHT_RE.match(line)
        if m:
            max_height = float(m.group(1))
    return by_object, max_height


def by_object_toolchange_lift(lines, cfg=None):
    """Snapmaker Orca fix #958 (head crashes in print-by-object): upstream 2.5's U1 change-filament
    G-code lifts *relatively* by an absolute target. Rewrite those lifts as absolute moves, and use
    max_print_height when the profile fell back to the 1.5 mm hop. Only the G91 / G1 Z.. F600 / G90
    triple that directly follows a tool-change comment block (before the next T command) is touched."""
    by_object, max_height = _print_facts(lines, cfg)
    if not by_object:
        return lines
    out, i, n, in_block = [], 0, len(lines), False
    while i < n:
        line = lines[i]
        text = line.strip()
        if TOOL_CHANGE_RE.match(line):
            in_block = True
        elif TOOL_RE.match(line) or (text and not text.startswith(";") and text != "G91"):
            in_block = False   # next tool change, or any other command: the block is over
        if in_block and text == "G91" and i + 2 < n and lines[i + 2].strip() == "G90" and LIFT_RE.match(lines[i + 1].strip()):
            z = float(LIFT_RE.match(lines[i + 1].strip()).group(1))
            if z <= 1.5:
                if not max_height:   # the 1.5 mm hop with no height to lift to: as absolute Z it would dive into the print
                    out.append(line)
                    i += 1
                    in_block = False
                    continue
                z = max_height
            out += [MARK + " absolute tool-change lift (Snapmaker Orca #958)", "G90", "G1 Z%g F600" % z]
            i += 3
            in_block = False
            continue
        if in_block and text == "G91":
            in_block = False   # a G91 that is not the lift triple
        out.append(line)
        i += 1
    return out


def real_total_layers(lines, cfg=None):
    """Snapmaker Orca writes the real layer count into SET_PRINT_STATS_INFO TOTAL_LAYER=;
    upstream writes a pre-export estimate, so the touchscreen's layer counter can overshoot.
    Print-by-object restarts the layer count per object, so it is left alone there."""
    if _print_facts(lines, cfg)[0]:
        return lines
    count = sum(1 for l in lines if l[:1] != "G" and LAYER_RE.match(l))
    if not count:
        return lines
    rx = re.compile(r"^(\s*SET_PRINT_STATS_INFO\b.*\bTOTAL_LAYER=)(\d+)", re.I)
    return [rx.sub(lambda m: m.group(1) + str(count), l) if "=" in l else l for l in lines]


def fan_off_while_probing(lines):
    """Part fan off before Z homing / plate detect / mesh (as Snapmaker Orca's start G-code)."""
    start = _start_index(lines)
    if start is None:
        return lines
    out = lines
    for i in reversed([i for i, l in enumerate(lines[start + 1:], start + 1)   # the prefix test skips the moves
                       if (l[:1] in "DdBb \t" or l[:3] in ("G28", "g28")) and PROBING_RE.match(l)]):
        if not lines[i - 1].strip().upper().startswith("M107"):
            out = out if out is not lines else list(lines)
            out.insert(i, "M107 " + MARK + " fan off while probing")
    return out


def recolour_metadata(lines, mapping, heads):
    """Rewrite '; filament_colour = ...' so the printer's file list shows the assigned heads' colours."""
    out = list(lines)
    for i in [i for i, l in enumerate(lines) if "filament_colour" in l]:
        m = SETTING_RE.match(lines[i])
        if m and m.group(1) == "filament_colour":
            colours = split_list(m.group(2))
            for fi, t in mapping.items():
                c = heads[t].get("colour") if 0 <= t < len(heads) and heads[t].get("loaded") else None
                if c and fi < len(colours):
                    colours[fi] = c
            out[i] = "; filament_colour = " + ";".join(colours)
    return out


def tag_slicer(lines, version):
    """Header comment identifying the post-processor."""
    if any(l.startswith(MARK + " version") for l in lines[:50]):
        return lines
    return [MARK + " version %s" % version] + lines


def process(lines, cfg, options, mapping=None, heads=None, version="0"):
    """Apply the enabled transforms. options: dict of booleans plus 'purifier' mode and, optionally, the
    top-cover fan speeds ("exhaust_fan", "inner_fan": percent)."""
    used = filaments(lines, cfg)
    mode = options.get("purifier", "auto")
    if mode == "auto":
        mode = u1.purifier_mode(used)
    fans = u1.clean_prefs({k: options.get(k) for k in u1.COVER_FANS})
    lines = ensure_purifier(lines, mode, fans)
    if mode in u1.PURIFIER and u1.purifier_command(mode, fans) not in lines:
        mode = "off"   # nowhere to put it (no PRINT_START): report what actually happened
    if options.get("chamber_wait", True):
        lines = ensure_chamber_wait(lines)
    if options.get("whole_bed_mesh", True):
        lines = whole_bed_mesh(lines)
    if options.get("by_object_lift_fix", True):
        lines = by_object_toolchange_lift(lines, cfg)
    if options.get("real_total_layers", True):
        lines = real_total_layers(lines, cfg)
    if options.get("fan_off_probing", True):
        lines = fan_off_while_probing(lines)
    if mapping and heads and options.get("recolour_metadata", True):
        lines = recolour_metadata(lines, mapping, heads)
    return tag_slicer(lines, version), mode
