<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/u1control-hero-dark.png">
    <img src="assets/readme/u1control-hero-light.png" alt="u1control: Snapmaker U1 control for OrcaSlicer" width="800">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/bloodf/u1control/actions/workflows/ci.yml"><img src="https://github.com/bloodf/u1control/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/bloodf/u1control/releases/latest"><img src="https://img.shields.io/github/v/release/bloodf/u1control" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/bloodf/u1control" alt="License: GPL-3.0"></a>
  <img src="https://img.shields.io/badge/OrcaSlicer-2.5%2B-informational" alt="OrcaSlicer 2.5+">
</p>

# u1control

u1control is an OrcaSlicer 2.5 plugin for the Snapmaker U1. It adds the U1-specific parts of
Snapmaker Orca to the regular OrcaSlicer, plus a full printer tab: camera, toolheads, RFID, Spoolman,
a file manager and Extended Firmware settings.

It works with the stock Snapmaker firmware and with the
[U1 Extended Firmware](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware), and
picks up the extra features of the Extended Firmware by itself. Everything stays on your local
network, and the plugin needs no extra Python packages.

u1control is an independent project. It is not made or supported by Snapmaker.

<p align="center">
  <img src="assets/features/feature-print-setup.svg" width="72" alt="Print setup">
  <img src="assets/features/feature-live-camera.svg" width="72" alt="Live camera">
  <img src="assets/features/feature-toolheads-rfid.svg" width="72" alt="Toolheads and RFID">
  <img src="assets/features/feature-spoolman.svg" width="72" alt="Spoolman">
  <img src="assets/features/feature-file-manager.svg" width="72" alt="File manager">
  <img src="assets/features/feature-extended-firmware.svg" width="72" alt="Extended Firmware">
  <img src="assets/features/feature-snapmaker-orca-fixes.svg" width="72" alt="Snapmaker Orca fixes">
  <img src="assets/features/feature-automagic.svg" width="72" alt="Automagic">
</p>

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/how-it-works-dark.png">
  <img src="assets/diagrams/how-it-works-light.png" alt="OrcaSlicer sends to u1control, which talks to the U1, Spoolman and Spooler">
</picture>

## Features

### Print setup

When you press **Print** for a U1, u1control decides which toolhead prints each filament before the
file leaves OrcaSlicer, the way Snapmaker Orca does.

<img src="assets/diagrams/toolhead-mapping.png" alt="Each filament colour mapped to a toolhead" width="800">

- Filaments are matched to the four toolheads by material, then material family, then nearest colour.
  Empty heads and material mismatches are flagged before anything is sent.
- The print options go to the printer with the same commands Snapmaker Orca uses: auto bed leveling,
  flow calibration and time-lapse, plus auto-refill, tangle detection, unload when done and light off
  when done when the firmware offers them.
- The top-cover mode follows Snapmaker's rule for the filaments in the print, or the mode you pick.
- Nothing is sent while the U1 is printing, loading, calibrating or updating.

On every U1 slice u1control also fixes the G-code. Each fix can be turned off in Expert mode.

| Fix | Why |
|---|---|
| Top-cover line set to the chosen mode | custom start G-codes lose it, and the profile's own line ignores the pop-up |
| Chamber wait after the bed heats up | some start G-codes leave it out |
| Whole-bed 11×11 mesh instead of adaptive | the U1 keeps one saved mesh, so a small patch would be reused by later prints |
| Part fan off while homing Z and probing | as Snapmaker Orca does |
| Absolute tool-change lift in print-by-object | Snapmaker Orca fix #958; the stock 2.5 profile can lift too little or too much |
| Real total layer count | the touchscreen's layer counter is right |
| File colours match the assigned toolheads | the printer's file list shows the real colours |

### U1 Control tab

- **Dashboard:** everything about the printer on one page.
  - Camera, status and progress, pause, resume, cancel and emergency stop, temperatures with each
    head's filament, speed, chamber light and top cover.
  - The four toolheads: filament and colour, RFID tag details (Snapmaker tags, and with the Extended
    Firmware OpenRFID, OpenSpool, NTAG and external readers), edit, load, unload and read the tag again.
  - Spoolman: one spool per toolhead, picked from a list that shows each spool's colour, brand,
    material and grams left. Pick a spool and its filament is written to the head. Change the filament
    on the printer and the closest spool is linked. Each head's filament use is recorded when the print
    finishes.
  - With the Extended Firmware: the printer's touchscreen (Remote Screen), live, and tappable.
  - Resume or discard a print interrupted by a power cut, and see the printer's error list.
- **Files:** browse, print and delete G-code files; browse, save and delete time-lapses. Create
  folders, and move files and folders with **Move** or by dragging a row onto a folder.
- **Console:** send G-code.
- **Settings:** Automagic or Expert, Spoolman, the printer's print options, bed mesh, input shaper
  and flow calibration, the Extended Firmware's settings (web UI, camera, RFID system, Spoolman, Remote
  Screen, SSH and more) with restart Klipper, restart Moonraker and reboot, Spooler, and the connection.

### Firmware support

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/firmware-support-dark.png">
  <img src="assets/diagrams/firmware-support-light.png" alt="Features on stock firmware and on Extended Firmware">
</picture>

### Automagic and Expert

<img src="assets/diagrams/automagic-vs-expert.png" alt="Automagic does each step for you; Expert makes each step a setting">

Automagic is the default: everything that can run by itself does, and the print pop-up only opens
when a decision is needed. Expert turns each step into a setting. Your Expert choices are kept while
Automagic is on. See [docs/settings.md](docs/settings.md) for every setting.

### Works with Spooler

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/integration/u1control-works-with-spooler-dark.png">
  <img src="assets/integration/u1control-works-with-spooler-light.png" alt="u1control and Spooler share spools and filament profiles">
</picture>

[Spooler](https://github.com/bloodf/spooler) turns your Spoolman filaments into OrcaSlicer filament
profiles. With Spooler installed, u1control applies Spooler's profile for the spool in each toolhead
and steps aside while Spooler's "Keep Slots Synced" runs. Without it, u1control's own Spoolman tools
do the job. The two plugins agree on which spool is in which toolhead and record filament use only
once. The details are in [docs/spooler-contract.md](docs/spooler-contract.md).

### Plugins > Run

- **Check U1 connection**
- **Sync U1 toolheads to project filaments:** puts the right filament profile for each toolhead into
  the project, using the RFID tag first.
- **Apply Snapmaker Orca U1 process tuning:** asks first, then changes the process preset to Snapmaker
  Orca's U1 values. It also fixes the 0.25 mm layer height in OrcaSlicer 2.5's
  `0.18 Standard @Snapmaker U1 (0.6 nozzle)`. The preset stays unsaved until you save it.

## Install

<p align="center">
  <img src="assets/install/u1control-install-01.png" width="390" alt="Step 1: install">
  <img src="assets/install/u1control-install-02.png" width="390" alt="Step 2: connect your U1">
  <img src="assets/install/u1control-install-03.png" width="390" alt="Step 3: turn on print setup">
  <img src="assets/install/u1control-install-04.png" width="390" alt="Step 4: print">
</p>

1. Subscribe to u1control on the OrcaSlicer Plugin Hub, or download `u1control_any.whl` from the
   [latest release](../../releases/latest) and use **File > Plugins > Install local plugin**.
2. Tick **Activate** and allow the background thread when OrcaSlicer asks.
3. Select your Snapmaker U1 printer and enter its IP address (the Wi-Fi icon next to the printer name).
4. In Automagic mode u1control adds **U1 print setup** to your U1 process preset. Save the preset to
   keep it. In Expert mode, add it yourself under **Process > Others > Slicing Pipeline Plugin**.

The **U1 Control** tab appears next to Prepare, Preview and Device.

Requirements: OrcaSlicer 2.5.0 or newer, and a Snapmaker U1 on the same network.

## Documentation

- [Architecture](docs/architecture.md): modules, threads and the page protocol
- [Definitions](docs/definitions.md): the terms used in the code and the UI
- [Settings](docs/settings.md): every setting and its Automagic value
- [Firmware](docs/firmware.md): the printer commands and endpoints u1control uses
- [Spooler contract](docs/spooler-contract.md): how u1control and Spooler share work
- [Contributing](CONTRIBUTING.md), [Code of conduct](CODE_OF_CONDUCT.md) and [Security](SECURITY.md)

Questions and ideas: [Discussions](https://github.com/bloodf/u1control/discussions). Bugs: [Issues](https://github.com/bloodf/u1control/issues).

## Credits

u1control is built from the public sources of Snapmaker's
[u1-klipper](https://github.com/Snapmaker/u1-klipper),
[u1-moonraker](https://github.com/Snapmaker/u1-moonraker),
[u1-fluidd](https://github.com/Snapmaker/u1-fluidd),
[Snapmaker/OrcaSlicer](https://github.com/Snapmaker/OrcaSlicer) and the
[U1 Extended Firmware](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware).
Ideas came from the SnapSend, U1 Sync & Send, Set & Send and
[orca-snapmaker-u1-camera-plugin](https://github.com/lanwen/orca-snapmaker-u1-camera-plugin) plugins.

Fonts in `assets/fonts` (Outfit, JetBrains Mono) are under the SIL Open Font License.

License: [GPL-3.0-only](LICENSE).
