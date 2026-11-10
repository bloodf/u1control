"""Interop with the Spooler plugin (github.com/bloodf/spooler), which turns Spoolman filaments into
OrcaSlicer filament presets in the local bundle "spooler". Free of the `orca` module.

preset meta: {"name", "bundle_id", "compatible_printers": [..], "colour": "#RRGGBB", "vendor"}
"""

import json
import os
import re

import u1

BUNDLE_ID = "spooler"
URL = "https://github.com/bloodf/spooler"
NAME_PREFIX = "_local/spooler/"
DATA_SUBDIR = "spooler"                  # <Orca data dir>/spooler/, the data dir being the parent of orca_plugins
SETTINGS_FILE = "spooler_settings.json"
PROFILES_FILE = "profiles.json"          # {"version": 1, "filaments": {"<filament id>": {"<printer label>": "<preset>"}}}
KEEP_SLOTS_FILE = "keep_slots.json"      # {"active": true, "printer": "<label>", "ts": <unix s>}, refreshed ~5 s
KEEP_SLOTS_FRESH = 30.0                  # seconds
COLOUR_CAP = 120.0   # redmean distance beyond which "nearest colour" is no longer the same spool


def detect(bundle_ids, filament_presets_meta, settings_file_exists=False):
    count = sum(1 for m in filament_presets_meta or () if m.get("bundle_id") == BUNDLE_ID)
    installed = BUNDLE_ID in (bundle_ids or ()) or count > 0 or bool(settings_file_exists)
    return {"installed": installed, "presets": count}


def data_dir(storage_path):
    """Spooler's data folder from this plugin's storage path ("" when no orca_plugins folder above it)."""
    cur = os.path.abspath(storage_path or "")
    while os.path.dirname(cur) != cur:
        if os.path.basename(cur) == "orca_plugins":
            return os.path.join(os.path.dirname(cur), DATA_SUBDIR)
        cur = os.path.dirname(cur)
    return ""


def read_json(folder, name):
    """Parsed JSON object from folder/name; None when missing, unreadable or not an object."""
    if not folder:
        return None
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def keep_slots_active(marker, now, printer_labels=()):
    """Spooler's "Keep Slots Synced" is running for this printer: active, refreshed within
    KEEP_SLOTS_FRESH seconds, and its "printer" label matches one of printer_labels (a marker without
    a label, or no labels to compare, counts as a match). Spooler's label is the printer model, or
    "<model> <nozzle>" when two presets share a model."""
    try:
        fresh = bool(marker and marker.get("active")) and abs(now - float(marker.get("ts"))) < KEEP_SLOTS_FRESH
    except (TypeError, ValueError):
        return False
    label = str(marker.get("printer") or "").strip().lower() if fresh else ""
    wanted = [str(p).strip().lower() for p in printer_labels if p]
    return fresh and (not label or not wanted or any(label == w or label.startswith(w + " ") or w.startswith(label + " ")
                                                    for w in wanted))


def profile_lookup(profiles, filament_id, printer_label):
    """Preset name Spooler published for a Spoolman filament on the printer with this label, or None."""
    if not isinstance(profiles, dict) or filament_id is None:
        return None
    entry = (profiles.get("filaments") or {}).get(str(filament_id))
    if not isinstance(entry, dict) or not entry:
        return None
    label = str(printer_label or "").casefold()
    for key, name in entry.items():
        if str(key).casefold() == label:
            return name
    for key, name in entry.items():  # "Snapmaker U1 0.4" style labels when the model is duplicated
        if label and str(key).casefold().startswith(label):
            return name
    return None


def as_list(value):
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [p.strip().strip('"') for p in str(value or "").split(";") if p.strip()]


def spooler_presets(names_meta, printer_names=()):
    """Spooler presets usable with the current printer (any when it, or the preset's list, is unknown)."""
    wanted = {n for n in printer_names if n}
    out = []
    for m in names_meta or ():
        if m.get("bundle_id") != BUNDLE_ID:
            continue
        compatible = as_list(m.get("compatible_printers"))
        if not compatible or not wanted or wanted & set(compatible):
            out.append(m)
    return out


def _norm(text):
    return re.sub(r"[^a-z0-9+]", "", str(text or "").lower())


def _bare(name):
    return name[len(NAME_PREFIX):] if name.startswith(NAME_PREFIX) else name


def preset_for_spool(presets, spool, profiles=None, printer_label=""):
    """Name of the Spooler preset for a bound spool: Spooler's published profiles.json entry, else the
    nearest colour of the same vendor + material."""
    published = profile_lookup(profiles, spool.get("filament_id"), printer_label)
    if published:
        by_bare = {_bare(p["name"]).casefold(): p["name"] for p in presets}
        if _bare(published).casefold() in by_bare:
            return by_bare[_bare(published).casefold()]
    vendor, material = _norm(spool.get("vendor")), _norm(spool.get("material"))
    near = []
    for p in presets:
        bare = _norm(_bare(p["name"]))
        same_vendor = _norm(p.get("vendor")) == vendor if p.get("vendor") else vendor in bare
        if material and material in bare and vendor and same_vendor:
            near.append((u1.colour_distance(spool.get("colour"), p.get("colour")), len(p["name"]), p["name"]))
    near.sort()
    return near[0][2] if near and near[0][0] <= COLOUR_CAP else None
