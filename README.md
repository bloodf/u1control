# u1control

Snapmaker U1 control for **OrcaSlicer 2.5+**. It brings the U1-specific parts of Snapmaker Orca
to the regular OrcaSlicer and adds what neither has: a full U1 tab with camera, toolheads,
Spoolman, a file manager and Extended Firmware configuration.

Works with the **stock Snapmaker firmware** and the
[**U1 Extended Firmware**](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware)
(paxx12). It detects which one is running and enables the extra features automatically.
Local network only, no cloud, no extra Python packages.

> Independent project, not made or supported by Snapmaker.

## Features

### U1 print setup (Slicing Pipeline plugin)

Opens when you press **Print → Upload & Print** for a U1, like Snapmaker Orca's pre-print dialog:

- Filament → toolhead mapping with the 4 heads shown in their loaded colour and material.
  Auto mapping (same material, then family, then nearest colour), warnings for empty heads and
  material mismatches. The heads refresh live if you swap a spool on the touchscreen.
- Print options sent the way Snapmaker Orca sends them (`SET_PRINT_EXTRUDER_MAP`,
  `SET_PRINT_USED_EXTRUDERS`, `SET_PRINT_PREFERENCES`): auto bed leveling, flow calibration,
  time-lapse, plus auto-refill, tangle detection, unload/light-off when done when the firmware
  reports them.
- Top-cover (purifier) mode: auto (Snapmaker's softening-temperature rule) or manual.
- Refuses to send while the U1 is printing, loading, calibrating or upgrading.

G-code fixes applied on every U1 slice (each one optional and idempotent):

| Fix | Why |
|---|---|
| Purifier line when the start G-code lacks one | custom start G-codes lose the top-cover control |
| `WAIT_CHAMBER_TEMP` after bed heat-up when missing | as Snapmaker's profile |
| Whole-bed 11×11 mesh instead of adaptive | the U1 saves every mesh as `default`; a small patch is reused by later prints |
| Part fan off while homing Z / plate detect / probing | as Snapmaker Orca |
| Absolute tool-change lift in print-by-object | Snapmaker Orca fix #958 (upstream 2.5 lifts relatively by an absolute target → crashes) |
| Real `TOTAL_LAYER` in `SET_PRINT_STATS_INFO` | the touchscreen's layer counter |
| `filament_colour` metadata recoloured to the assigned heads | the printer's file list shows the real colours |

### U1 Control tab

- **Dashboard:** camera (stock snapshot feed or the Extended Firmware camera + live stream),
  status, progress, pause/resume/cancel/E-stop, temperatures, speed, chamber light, top cover.
  Power-loss recovery (resume/discard) and printer error banners.
- **Toolheads:** loaded filament per head with RFID tag details (Snapmaker, and on Extended
  Firmware OpenRFID / OpenSpool / NTAG / external readers), edit filament
  (`SET_PRINT_FILAMENT_CONFIG`), load / unload, re-read the tag, printer print preferences,
  bed mesh / input shaper / flow calibration.
- **Spoolman:** one spool per toolhead. Pick a spool and its filament is written to the head;
  change the filament on the printer and the closest spool is selected. On Extended Firmware it
  uses SpoolLink (`SET_SPOOL_ID`); on stock firmware the binding lives in the spool's
  location (`U1 T1`…`U1 T4`). Filament use per head is reported when a print finishes.
- **Files:** browse, print and delete G-code; browse, save and delete time-lapses.
- **Firmware:** Extended Firmware settings (web UI, camera, RFID system, Spoolman, SSH, …) through
  its Firmware Config API, plus restart Klipper / Moonraker / reboot.
- **Console:** send G-code.

### Plugins > Run

- **Check U1 connection**
- **Sync U1 toolheads to project filaments**: picks the matching OrcaSlicer filament profile for
  each head (RFID tag first) and sets its colour.
- **Apply Snapmaker Orca U1 process tuning**: Snapmaker Orca's U1 process values that differ
  upstream (asks first; the preset stays unsaved until you save it). Also fixes upstream 2.5's
  `0.18 Standard @Snapmaker U1 (0.6 nozzle)` shipping a 0.25 mm layer height.

## Automagic and Expert modes

**Settings > Mode.** *Automagic* (default) does everything it can by itself and shows a read-only list
of what runs automatically: adds "U1 print setup" to U1 process presets, opens the print pop-up only
when something needs a decision (mapping warnings, ambiguous mapping, first print, unknown printer
options), picks the top-cover mode, applies the G-code fixes, applies RFID tags to project filaments,
binds Spoolman spools, reports filament use and writes the bound spool to its toolhead.
*Expert* shows each of those as a control (pop-up auto / always / never, each G-code fix, Spoolman
steps, print option defaults). Your Expert choices are kept while Automagic is on but ignored.
Connection settings (printer address, API key, printer name, Spoolman URL) apply in both modes.
Settings are stored in the plugin's storage folder (`settings.json`) and shared by every part of the plugin.

## Works with Spooler

[Spooler](https://github.com/bloodf/spooler) turns your Spoolman filaments into OrcaSlicer filament
profiles. If it is installed, u1control uses its profiles when applying heads to project filaments
(the profile of the spool bound to each head, via Spooler's `profiles.json` when present) and leaves
slot syncing to Spooler while its "Keep Slots Synced" runs. If it is not installed, u1control's own
Spoolman tools keep working and the page suggests Spooler once (dismissible).

## Install

1. Download `u1control_any.py` from the [latest release](../../releases/latest) (or subscribe on the
   OrcaSlicer Plugin Hub).
2. OrcaSlicer: **File > Plugins > Install local plugin**, pick the file, tick **Activate**, allow
   the background thread.
3. Select your Snapmaker U1 printer and set its IP (Wi-Fi icon next to the printer name).
4. **Process > Others > Slicing Pipeline Plugin > Add plugin > U1 print setup**, then save the
   process preset (once per U1 process preset).

The **U1 Control** tab appears next to Prepare / Preview / Device.

## Develop

```sh
python3 scripts/build.py                 # -> dist/u1control_any.py
python3 -m unittest discover -s tests    # fake orca module + fake U1/Spoolman HTTP server
```

Sources live in `src/u1control/`; the build embeds the helper modules and the HTML pages into
one file because OrcaSlicer loads one `.py` per plugin.

Publishing: create a GitHub release `vX.Y.Z` matching `pyproject.toml` with a `CHANGELOG.md`
section; `publish-orcacloud.yml` uploads it (connect the repo on Orca Cloud first).

## Credits

Built from the public sources of Snapmaker's
[u1-klipper](https://github.com/Snapmaker/u1-klipper),
[u1-moonraker](https://github.com/Snapmaker/u1-moonraker),
[u1-fluidd](https://github.com/Snapmaker/u1-fluidd),
[Snapmaker/OrcaSlicer](https://github.com/Snapmaker/OrcaSlicer) and the
[U1 Extended Firmware](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware),
and ideas from the SnapSend, U1 Sync & Send, Set & Send and
[orca-snapmaker-u1-camera-plugin](https://github.com/lanwen/orca-snapmaker-u1-camera-plugin)
plugins.

License: GPL-3.0-only.
