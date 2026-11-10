# Changelog

## [0.3.1] - 2026-11-10

- The pages use OrcaSlicer's accent colour (teal by default) instead of yellow.
- README and store images re-rendered: the open spool picker, the Move dialog and the merged
  dashboard. The Orca Cloud description describes the new layout.

## [0.3.0] - 2026-11-10

- One Dashboard: camera, status, temperatures with each head's filament, and the four toolheads with
  their spools. The Toolheads and Firmware tabs are gone.
- Spoolman, the printer's print options, calibration and the Extended Firmware settings moved to
  Settings.
- With the Extended Firmware the Dashboard shows the printer's touchscreen (Remote Screen) and passes
  clicks on it to the printer as taps.
- New spool picker: a list with each spool's colour, brand, material, location and grams left,
  compatible materials first. It no longer closes on its own when the status refreshes, and works
  during a print.
- A temperature you are typing is no longer wiped by the status refresh.
- Files: create folders, and move files and folders into another folder with Move or by dragging a
  row onto a folder (or onto Up). Moves stay inside their own root.

## [0.2.3] - 2026-11-10

- Time-lapse downloads go to `<name>.part` and are renamed when complete. The plugin no longer
  deletes files on your computer; an interrupted download keeps its `.part` file and says where.

## [0.2.2] - 2026-11-10

- Ships as a standard Python wheel (`u1control_any.whl`) with no embedded or dynamically executed
  code, and declares its permissions up front.
- Spoolman locations bind the way Spooler does (#2): archived spools never bind, "<printer name> T<n>"
  beats other names ending in "U1", and when two spools claim one toolhead the one used last wins.

## [0.2.1] - 2026-11-10

- README, install and store images now show real screenshots of the plugin, and the Spooler image
  shows Spooler's logo. `scripts/render_images.py` regenerates them.
- The spool picker no longer overflows the toolhead cards, the firmware badge stays on one line and
  the temperature rows keep their buttons on one line.
- Open-source project setup: issue forms, pull request template, code of conduct, Dependabot and the
  Orca Cloud description text.

## [0.2.0] - 2026-11-10

- New look: brand symbol as the tab icon, icons across the U1 Control tab and the print setup pop-up,
  toolhead badges in the toolhead colours, and illustrations for empty states.
- Documentation: architecture, definitions, settings, firmware and Spooler contract references,
  contributing guide and security policy.
- README with diagrams and install steps.
- Temperature rows show readable toolhead badges.

## [0.1.0] - 2026-11-10

- U1 print setup (Slicing Pipeline plugin): filament to toolhead mapping, print options, top-cover mode,
  refuses to send while the U1 is busy.
- U1 G-code fixes: purifier line, chamber wait, whole-bed mesh, fan off while probing, by-object tool-change lift,
  real total layers, recoloured metadata.
- U1 Control tab: dashboard with camera, toolheads with RFID, files and time-lapses, Extended Firmware settings, console.
- Spoolman: one spool per toolhead, automatic binding, usage reporting, spool written to the toolhead.
- Plugins > Run: check connection, sync toolheads to project filaments, Snapmaker Orca U1 process tuning.
- Automagic and Expert modes with one shared settings store; the print pop-up only opens when a decision is needed.
- Adds "U1 print setup" to U1 process presets automatically.
- Spooler interop: uses Spooler's filament profiles, colour-aware profile choice, defers slot syncing to Spooler,
  suggests Spooler when it is missing.
- Works with Spooler 0.10.0+: shared toolhead/spool binding, Spooler presets via profiles.json, Keep Slots marker,
  single usage booking; joint integration tests run both plugins together.
- Safety: E-stop and pause/cancel bypass the command queue, automatic Spoolman binding never overwrites RFID spools,
  live-stream iframe removed, streaming downloads, prefixed module names.
