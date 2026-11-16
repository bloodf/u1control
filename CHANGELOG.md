# Changelog

## [Unreleased]

## [0.11.0] - 2026-11-16

- Files: a new **Time-lapses** section lists every video the U1 recorded, newest first, with its cover picture, the print's name, the date and the size. **Refresh** reads the list again. The length of a video is not shown, because the printer doesn't report it.
- **Save** copies a video to `Downloads/u1control` on your computer, never over a file that is already there, and says where it went.
- **Delete** asks first, then removes the video together with its cover and last-frame pictures from the printer. Deleting a time-lapse used to fail ("Path not available for DELETE"): the U1 shares the folder twice, and the "Timelapses & camera" folder of the file list is the read-only one. The new section uses the one that can be written. Deleting from "Timelapses & camera" itself still fails; use the Time-lapses section.
- Saving and deleting work while the U1 prints. In this section, a video can't be deleted while it is being saved, or saved while it is being deleted.
- A video without a cover shows an icon. A printer whose firmware has no time-lapse folder says so instead of showing an error.
- The section is in English and Portuguese, and on a narrow tab the date and size move under the name so Save and Delete stay on screen.
- Checked against a fake U1 only. The folder and file names come from a real U1 (2026-11-16), but listing, covers, Save and Delete of this version have not been run against a printer yet.

## [0.10.1] - 2026-11-16

- Printer agent: connecting to another U1 now switches the printer's id, address, key and status thread in one step. Before, for a moment while switching, the agent could pair the new printer's id with the old connection.

## [0.10.0] - 2026-11-16

- u1control is now also a printer agent, so OrcaSlicer's own Print dialog and Device tab work with the U1. To switch: in OrcaSlicer's **Preferences** turn on **Use printer agents instead of print hosts**, then in your U1 printer preset set **Printer Agent** to `u1control` and the host to the U1's IP, and save the preset. The print-host way (U1 print setup) keeps working as before.
- Print dialog: the four toolheads are the four slots, each with its filament and colour. The slot you pick for each filament is the toolhead that prints it; a filament you leave unpicked gets the toolhead u1control matches by material and colour.
- Print dialog: **Auto Bed Leveling**, **Flow Dynamics Calibration** and **Timelapse** start ticked in OrcaSlicer's dialog, so U1 Control's own print options decide what is used: each runs only when its box is ticked and it is on in U1 Control (by default bed leveling and flow calibration are on and time-lapse is off). Unticking a box turns that option off. OrcaSlicer remembers the box; tick it again to go back to U1 Control's setting. Auto-refill, refill from any colour, tangle detection, unload when done and light off when done come from U1 Control's settings (the options you last chose), or stay as the printer has them.
- Print from the dialog applies the same G-code fixes as U1 print setup, uploads the file, sends the toolhead map and options, then starts the print. A busy U1 (printing, loading, calibrating, updating), an empty toolhead or another material in a picked slot stops it before anything is sent, and the reason shows in OrcaSlicer's dialog. Filament use is booked in Spoolman as for prints sent through U1 print setup.
- The printer state and the picked toolheads are checked again after the upload; if the U1 became busy or a toolhead changed, the file stays on the U1 and the print isn't started. Cancelling in OrcaSlicer up to the moment the print starts starts nothing.
- **Send** uploads the fixed G-code without starting it, and refuses the name of the file the U1 is printing. A .gcode.3mf job is sent as its plate's G-code.
- Device tab: pause, resume and stop are sent at once. G-code lines and the light switch run one at a time, in the order you give them; a G-code line may take up to 10 minutes (homing, heating), as in the Console. Commands still waiting when OrcaSlicer disconnects from the U1 are dropped, never sent later.
- The printer preset's port and HTTPS setting are used as OrcaSlicer gives them. Work files left by a print interrupted when OrcaSlicer closed are removed the next time the plugin loads.
- Device tab: status, temperatures, progress, layers, the four toolheads and the chamber light, with pause, resume, stop, the light switch and the G-code lines OrcaSlicer sends.
- Settings > Print setup and the README say how to switch to the agent (English and Portuguese).
- OrcaSlicer asks once, when the plugin loads, to let u1control read the sliced job from its temp folder; the agent needs this to send a print. On Windows that folder is your whole `%TEMP%` (read only), because OrcaSlicer writes the job there directly.
- Untested on a real printer (built from Snapmaker's firmware 2.1.0 source and OrcaSlicer 2.5.0 source, checked against a fake U1 only):
  - that OrcaSlicer's dialog shows **Flow Dynamics Calibration** and **Timelapse** for this agent (`support_flow_calibration`, `support_timelapse` in the status push);
  - that the dialog's slot numbers arrive as toolheads 1 to 4 for this one-unit, four-slot push (`ams_mapping`);
  - that flow calibration (`FLOW_CALIBRATE`) and time-lapse (`TIME_LAPSE_CAMERA`) set by `SET_PRINT_PREFERENCES` right before the print starts take effect;
  - that OrcaSlicer's dialog shows the reason u1control gives when it stops a print;
  - the Device tab's light switch and G-code lines.
  Bed leveling, the toolhead map and the extended options use the same commands as U1 print setup.
- Not used: firmware 2.1.0's `SDCARD_PRINT_FILE_WITH_PARAMETERS`, which can't be detected safely on older firmware. Resonance compensation is not offered: OrcaSlicer never sends it, and the firmware's per-print setting has no effect that could be confirmed.

## [0.9.1] - 2026-11-15

- Screen readers: "U1 unreachable" and "doesn't answer" are announced at once again, as before 0.9.0; connecting, busy and the other reasons stay polite.
- Screen readers: the late-status notice is announced once. Its age, which changes every second, is shown but no longer read out again and again; the state in the top bar still says it.
- Tests: the stock Link buttons are off and point at the page's reason while the printer is offline or connecting.

## [0.9.0] - 2026-11-15

- New look, shared with the other Orca plugins: a cobalt bar at the top with the printer's name, address, firmware and connection state, the four tabs (Dashboard, Files, Console, Settings) and **Emergency stop**, which stays in the bar on every tab and still asks first. Panels have coloured headers and icons, the text uses the Manrope font, and light and dark follow OrcaSlicer.
- Dashboard: the print is the panel at the top left, with a drawing of the U1, the file, the percentage, the layer and elapsed, left and finish times. Pause, Resume and Cancel print sit under it; Cancel is red, at the far end and still asks.
- Toolheads: each toolhead is a card with its filament colour across the top, the spool drawn with what is left of the linked Spoolman spool, and its own nozzle temperature with Set and Off (these used to be in the status card). Load, Unload, Edit and Read RFID are at the bottom of each card. Bed, speed, top cover and chamber light are in a Bed and chamber panel.
- Why controls are off (no printer, offline, connecting, busy) is said once under the bar, on every tab, instead of next to each control.
- No printer chosen yet: the Dashboard shows the U1 with Open Settings and Try again, and the stock list stays below.
- Unconfirmed filament use is one warning line with **Review**; the list and "I checked it in Spoolman" open from there.
- The camera is one line while it is off; the frame rate choice is unchanged. Stock, Files, Console, the firmware card and Settings use the same panels; Settings has an index of its sections and one Save bar at the bottom.
- Every confirmation, every control that waits for the print to end and every message is unchanged. The page is smaller: the spool pictures are now drawn instead of embedded.
- The wheel also carries the licences of the Lucide icons (ISC) and the Manrope font (SIL OFL 1.1).

## [0.8.0] - 2026-11-15

- Stock (Spooler) on the Dashboard: in OrcaSlicer's web view each spool picture in the list grew to 40 × 160 px, squeezed out of shape, so a row was about 170 px tall, only two spools fitted and the last picture ran into the note under the list. The picture is now a fixed 40 px square (undistorted), rows keep their text height and the list scrolls inside its area.
- Stock (Spooler): "U1 Control reaches Spoolman through the printer…" is a plain line instead of a bordered box that looked like a text field.
- Toolheads: when the printer is busy, "The printer is busy (printing, loading or calibrating)" is shown once above the four toolheads instead of under each one. Edit, Load and Unload stay off and point to it for screen readers.
- Camera: choose the live view's frame rate on the camera card (5, 10, 15 or 30 fps; 5 stays the default). It is the most U1 Control asks for: the printer decides how often its camera picture changes (the official firmware renews it at its own pace) and each picture passes through OrcaSlicer one at a time, so the rate you see can be lower. When the picture hasn't changed, it is not sent to the page again and U1 Control asks less often, down to once a second, then speeds up again (never past the chosen rate) once the picture changes. At most the chosen rate of requests reaches the printer, and about one a second while the picture stands still. See docs/settings.md.
- Settings: a new Print setup card says whether the selected process preset runs U1 print setup (the toolhead choice), when its pop-up opens in Automagic, how to be asked every time (Expert, Print setup pop-up: always), and which ways of sending skip it (Export G-code, Print on the Files page, OrcaSlicer's "Use printer agents instead of print hosts"). When the step is missing it says how to add it, and only promises the automatic add while "Add U1 print setup to U1 process presets" is on. The README says the same.

## [0.7.0] - 2026-11-14

- Files: rename a file or folder (**Rename** on each row). A name the folder already has, a name with `/ \ : * ? " < > |` or control characters, a hidden name, and a print file losing its `.gcode` / `.gco` / `.g` extension are refused.
- Files: filter the list by name, and see each print file's filament in a new Filament column.
- Camera: **Save picture** saves the camera picture on screen to `~/Downloads/u1control` as `<printer> <date time>.jpg`, never replacing a file. It sends nothing to the printer.
- Moving a file into a folder that already has one with the same name is refused. Moonraker's move replaced the file there.
- The firmware (official or Extended) is checked again while the printer's answer was unclear, and after the printer was offline. An Extended printer whose Firmware Config API was slow on the first connect no longer stays in official-firmware mode until it is selected again. An unclear answer never switches an Extended printer back.
- Filament use of a print sent earlier waits while its printer's firmware can't be told, instead of guessing and possibly booking what SpoolLink also books.
- While a print runs or is paused, firmware settings that restart Klipper or reboot the printer are refused and their Apply buttons are off, as are Restart Klipper and Reboot. Settings that leave Klipper alone (Remote Screen, SSH, USB camera, web UI, VPN and a few more; see docs/firmware.md) still apply.
- The Files tab starts at the top folder of a newly selected printer instead of the previous printer's folder.
- A file list or Move dialog with a malformed entry from the printer no longer fails as a whole; the entry is skipped.
- The print setup no longer reads a `true` in the pop-up's answer as toolhead T2.

- A broken answer from the printer (not HTTP at all, or cut off) no longer stops the tab's monitor for good. It was not caught on the Remote Screen path, so status, camera and RFID follow stopped until OrcaSlicer restarted. It is now a normal printer error, and the Remote Screen keeps its own error and retry whatever goes wrong.
- Emergency stop falls back to `M112` also when the printer's websocket answers with an error given as plain text.
- An RFID tag with malformed fields (a colour count that is not a number, an odd UID) no longer fails every status poll and shows the printer offline; the bad field is ignored.
- A Spoolman address that answers with something other than JSON (a proxy's login page, another service) is reported as a Spoolman error. It used to fail the status poll during automatic spool follow and show the printer offline.
- Saving a printer file keeps it inside `~/Downloads/u1control` whatever the file is called on the printer: `\`, `:` and other characters Windows reads as folders or drives become `_`.
- Restart Klipper and Reboot (Settings > Firmware) are refused while a print runs or is paused, since both end it. Restart Moonraker still works, and a printer stuck in another state can still be restarted.
- Plugins > Run > Check U1 connection detects the Extended Firmware the same way the tab does, not from the version text alone.

## [0.6.0] - 2026-11-13

- The page now runs on PrimeVue 5.0.5 and @primeuix/themes 3.1.1 (shared Orca UI foundation 3.0.2, shared with Spooler, Organizer and the Print Calculator). No visible change is intended: same palette, sizes, fonts, focus rings and reduced-motion behaviour. The dialog close button is a few pixels smaller.
- PrimeVue 5 is under the PrimeUI License (Community tier); its key ships with the page and is checked offline, without any network access.
- Newer web view needed: PrimeVue 5 writes colours with CSS `light-dark()`, so OrcaSlicer's web view must be WebKit 17.5+ on macOS, WebView2 on Windows or WebKitGTK 2.44+ on Linux.

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
