# Snapmaker U1 control for OrcaSlicer

![u1control](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/u1control-main.png){align=center}

u1control brings the U1 parts of Snapmaker Orca to the regular OrcaSlicer and adds a full printer
tab: camera, toolheads, RFID, Spoolman, a file manager and Extended Firmware settings. It works with
the stock Snapmaker firmware and with the U1 Extended Firmware. Local network only, no cloud.

## Print setup

![Print setup](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/frame-print-setup.png){align=center}

When you press **Print**, each filament is matched to a toolhead by material and colour, with warnings
for empty heads or other materials. Auto bed leveling, flow calibration, time-lapse and the top cover
are set the way Snapmaker Orca sets them. u1control also fixes the U1 G-code: whole-bed mesh,
print-by-object tool-change lift, real layer count, file colours.

## Live control

![Live control](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/frame-live-control.png){align=center}

Camera, status, temperatures, pause, resume, cancel and emergency stop, chamber light and top cover,
inside OrcaSlicer. Resume a print after a power cut.

## Toolheads and RFID

![Toolheads and RFID](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/frame-toolheads-rfid.png){align=center}

See and edit the filament in each head, load and unload, and run calibration. RFID tags (Snapmaker,
and with the Extended Firmware OpenRFID, OpenSpool and NTAG) pick the right filament profile for your
project.

## Spoolman

![Spoolman](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/frame-spoolman.png){align=center}

One spool per toolhead. Filament use is recorded for each head when the print ends. Works with the
[Spooler](https://github.com/bloodf/spooler) plugin, which turns your spools into OrcaSlicer filament
profiles.

## Files and firmware

![Files and firmware](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/frame-files-firmware.png){align=center}

Browse, print and delete files, save time-lapses, and change Extended Firmware settings.

## Automagic or Expert

Automagic does everything it can by itself and only asks when a decision is needed. Expert turns each
step into a setting.

## Install

1. Subscribe, then open **File > Plugins**, click **Refresh** and tick **Activate**. Allow the
   background thread.
2. Select your Snapmaker U1 printer and enter its IP address (Wi-Fi icon next to the printer).
3. Automagic adds **U1 print setup** to your U1 process preset; save the preset.
4. Open the **U1 Control** tab next to Prepare and Preview.

Requires OrcaSlicer 2.5.0 or newer. Independent project, not made or supported by Snapmaker.

Source, documentation and issues: [github.com/bloodf/u1control](https://github.com/bloodf/u1control)
· License: GPL-3.0-only
