# Changelog

## [Unreleased]

## [0.5.1] - 2026-11-13

- Dark theme: a style meant for the reel and the level bar was applied to the whole page (a faint glow filter and a different background). It now reaches only the reel and the bar.
- Near-black filament on the dark theme, and near-white on the light theme, get a clear edge on the level bar, so a full black spool no longer looks like an empty bar. Same as Spooler 0.22.2.

## [0.5.0] - 2026-11-13

- Toolhead cards show the loaded spool as a reel in its filament colour, drawn fuller or emptier from what is left of the linked Spoolman spool, with the grams, the percentage and a level bar in the filament's colours. An empty toolhead shows a bare reel.
- The stock list shows each spool's reel and a small level bar next to the grams left.
- Spoolman spools carry their full weight (the spool's initial weight, else the filament's) so the fill can be drawn; without it the reel is drawn full and no bar is shown.
- Same reel and bar as Spooler 0.22.0.

## [0.4.2] - 2026-11-12

- Fix the Spooler link (stock, profiles, Keep Slots) and the print ledger silently falling back when used from the tab or a worker thread. OrcaSlicer 2.5 answers `plugin.storage()` only inside plugin callbacks and raises "must be called from a plugin callback" elsewhere; the folder is now read while loading and kept.

## [0.4.1] - 2026-11-12

- Build tools only: shared Orca UI foundation 2.0.3 (Vite 8.3.8, @vitejs/plugin-vue 6.0.11). No change to printer control or the interface. Joint tests still run against Spooler `v0.21.0`.

## [0.4.0] - 2026-11-12

Checked with fakes only: a fake `orca` module, a fake U1 (Moonraker) and Spoolman server, the Spooler source in the same process, and the built page in headless Chrome with a scripted bridge. Nothing here has run inside a real OrcaSlicer or against a real printer, camera or Spoolman.

- The stock list and linking from the Dashboard need Spooler 0.21.0 or newer (its presence and stock-list API; the joint tests run against the `v0.21.0` release). Without Spooler, or with an older one, U1 Control works on its own as before.
- The wheel carries the licences of the bundled Vue, PrimeVue and PrimeUIX (MIT) and U1 Control's own LICENSE under `dist-info/licenses/`.
- Release workflow: the publish run now provisions Node and Chrome, rebuilds the Vue page and fails if the committed `app.html` differs, runs the page tests with `WORKERS=1` against Spooler `v0.21.0`, takes the changelog from this file, and attaches the wheel and `SHA256SUMS` to the GitHub release. `docs/release.md` has the steps.

- Temperature readings fit narrow windows, and the setup window reserves scroll space for its sticky footer so focused controls remain visible.
- Browser tests disable Chrome extensions that could leave child processes holding the runner open. `WORKERS=1` runs scenarios sequentially; CI uses this mode.

- The tab and the U1 print setup window are one Vue 3 + PrimeVue 4 page (shared Orca UI foundation 2.0.2),
  built from `ui/` into `src/u1control/ui/app.html` and still shipped inside the wheel; no CDN, no remote
  font, no eval. English and Brazilian Portuguese, following OrcaSlicer's language unless you choose one in
  Settings. Light and dark follow the host colour while the tab is open.
- Printer commands: one in flight per action (a double click sends once), a visible "waiting" state, and
  after 15–120 s without an answer an "outcome unknown" message that stays until dismissed; nothing is
  retried by itself. Errors stay until dismissed. The emergency stop never waits behind another command
  and stays available for a known printer that is offline; without a selected U1 every printer control is
  off with the reason shown.
- Cancel print and emergency stop name both answers ("Cancel print" / "Keep printing", "Stop now (E-stop)" /
  "Go back"); the E-stop sits apart from Cancel. A blank temperature field never sends 0, values above
  320 °C / 110 °C are refused before sending, and Off during a print asks first.
- Keyboard focus and typed values survive the 2 s status refresh; dialogs return focus to the control
  that opened them.
- Unconfirmed filament use is listed on the Dashboard with its print, toolhead, grams, spool and time, and
  can be marked as checked (a local note only).
- Stock card: "Stock (Spooler)", "Link to T1" buttons, the reason linking is off shown as text, notes by
  severity; the firmware badge reads "Official firmware", never "stock". A short note explains why
  Spooler and U1 Control stay two tabs (OrcaSlicer offers no way to hide a tab).
- Unconfirmed filament use now carries an id, time, printer, file, toolhead, spool and grams, and can be
  marked as checked after you looked in Spoolman. Marking is a local, dated note kept in the ledger
  file; it sends nothing to Spoolman. Unreadable entries in the ledger are reported instead of skipped
  silently.
- The print setup no longer sends with an empty toolhead or another material unless you tick the
  confirmation for those exact warnings; the plugin checks it again and sends nothing otherwise. The
  toolhead list keeps keyboard focus when you choose or when it refreshes.
- The tab can tell "no U1 selected" from "U1 unreachable", and the heater limits it shows come from the
  plugin (320 °C hotend, 110 °C bed).
- CI: the Spooler ref for the joint tests is explicit (run input, `SPOOLER_REF` variable, else the release `v0.21.0`).

- Stock from Spooler on the Dashboard: while Spooler runs in the same OrcaSlicer, its stock list
  (search, material filter, low stock, "use first") shows next to the camera, status and toolheads,
  and a spool links to a toolhead from there through U1 Control's own checks. Each plugin writes a
  presence file in OrcaSlicer's data folder; a file left by a closed, disabled or other OrcaSlicer is
  not taken for a running Spooler. Links from a list of an earlier Spooler run, another Spoolman or a
  printer no longer selected are refused before anything is written.
- Pending filament use is kept on disk (`usage_ledger.json`), so closing OrcaSlicer no longer forgets
  prints in progress. Use being recorded when OrcaSlicer closed, and prints that finished unseen, are
  listed as unconfirmed for you to check, never booked twice or blindly.

- Requests are tied to the printer that was selected: a queued command for one U1 no longer runs on
  another after you switch, and pictures, status and spool data of the old printer are dropped. When the
  selected printer isn't a usable U1, the tab lets go of the old one and clears what it showed,
  including open confirmations.
- Filament use: jobs are tracked per printer and file path (not just the file name), also when the tab
  is closed, and charged to the spools linked when the job was sent. A Spoolman call that fails is
  reported as unconfirmed and never repeated; toolheads not tried yet are tried again.
- Linking a spool writes the toolhead first and Spoolman after; a step that fails says what is left
  and reloads the links. An empty Spoolman inventory clears links; a failed read keeps them.
- Two downloads of the same file, or a file another program creates meanwhile, are never overwritten.
- A broken camera shows its own message and no longer stalls status ("Offline").
- Load, unload, edit, print options and spool writes check the printer is idle (also loading or
  calibrating) right before sending; the print setup checks again after its window closes. Editing
  or linking over an RFID tag asks first and only then sends FORCE=1. Heating asks first.
- Extended Firmware settings read the firmware's real format (groups, labels, confirmations, inputs,
  hidden options). A setting or action is "Applied" only when the firmware reports SUCCESS.
- Thumbnails load for visible rows, two at a time, on their own thread.
- Settings: unsaved Expert values survive switching modes, "Saved" waits for the answer, the API key
  is hidden. Unload when done is set in the print setup pop-up (shown read-only in Settings).
- Dialogs keep keyboard focus, close with Escape and give focus back; more controls have labels.
- Spooler files of another version or shape are ignored instead of breaking the sync.
- Console shows the printer's replies; M112 runs the E-stop.

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
