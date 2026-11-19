# Architecture

u1control ships as a standard pure-Python wheel, `u1control_any.whl`, which OrcaSlicer loads as a
plugin. The sources live in `src/u1control/`, and `scripts/build.py` packs them.

## Modules

| Module | Job | Uses `orca`? |
|---|---|---|
| `moonraker.py` | HTTP client for Moonraker (port 80, then 7125) and a small websocket client for the calls Moonraker only offers over websocket | no |
| `u1.py` | U1 knowledge: toolheads, print options, filament mapping, RFID tags, top-cover rule, command builders | no |
| `gcode.py` | Reads exported G-code and applies the U1 fixes | no |
| `agent.py` | The printer agent's pure part: the Bambu-style status push and Device tab commands, and Print / Send from OrcaSlicer's dialog (map, fixes, upload, options, start) | no |
| `extended.py` | Client for the Extended Firmware's Firmware Config API | no |
| `spoolman.py` | Spoolman client and spool matching | no |
| `settings.py` | The shared settings store and the Automagic / Expert rules | no |
| `spooler_bridge.py` | Finds Spooler and reads its `profiles.json` and `keep_slots.json` | no |
| `peers.py` | Presence files in Orca's data folder: says U1 Control runs, finds a running Spooler and reads its stock list | no |
| `usage.py` | Prints u1control sent, by printer and file, until their filament use is booked in Spoolman; kept in `usage_ledger.json` | no |
| `stockview.py` | Spooler's stock in the tab and linking one of its spools to a toolhead through u1control's own bind | no |
| `files.py` | File manager commands, the time-lapse list (videos paired with their cover pictures) and downloads that never overwrite a local file | no |
| `requirements.py` | What the plugin needs and can't install (printer agents preference, Extended Firmware, Spoolman): ok / missing / unknown from what the plugin already knows, no I/O | no |
| `service.py` | Runs printer work for the U1 Control tab: command worker, status monitor, camera, Spoolman follow, job tracker | no |
| `plugin.py` | OrcaSlicer glue: the capabilities (including the `U1Agent` printer agent), settings wiring, preset changes | yes |
| `ui/app.html` | The U1 Control tab and the print setup pop-up: one compiled Vue 3 + PrimeVue page (built from the top-level `ui/` project; mode chosen by the boot JSON `plugin.page_html` fills in) | — |

Only `plugin.py` imports `orca`, so everything else is tested without OrcaSlicer.

The wheel is the package `u1control`: `plugin.py` becomes `u1control/__init__.py`, each module keeps
its name (`u1control.service`, and so on), and `u1control/_assets.py` holds the compiled page,
zlib-compressed and base64-encoded in short lines (`APP_HTML_Z64`, as Spooler ships its page; Orca Cloud's upload
review timed out on the page as readable text), and the PNG tab icon. Nothing is embedded as source text or executed at load time, and the
modules never use plain names like `settings` or `service` that could clash with other plugins.
The sources keep `import u1` style so they run and test in place; the build rewrites those imports
to relative form (`from . import u1`) in the wheel copies. The build refuses any SVG that contains a
script or an event attribute, and writes the zip with fixed timestamps so the same sources give the
same bytes. It also writes `dist/SHA256SUMS`.

## Capabilities

| Name | OrcaSlicer type | Where it shows |
|---|---|---|
| U1 Control | Pages | a tab next to Prepare / Preview / Device |
| U1 print setup | Slicing Pipeline | Process > Others > Slicing Pipeline Plugin; runs at G-code post-processing |
| Check U1 connection | Script | Plugins > Run |
| Sync U1 toolheads to project filaments | Script | Plugins > Run |
| Apply Snapmaker Orca U1 process tuning | Script | Plugins > Run |

## Threads

OrcaSlicer runs the print setup on its slicing thread, page messages on its UI thread and scripts on
its script worker. u1control never sends printer traffic from those threads. All network work runs on
threads the plugin starts:

- **Command worker:** one thread runs page commands in order.
- **Thumbnail worker:** one thread fetches file thumbnails and time-lapse covers, at most 8 waiting; the
  page asks only for rows on screen, 2 at a time per list, and drops the rest when you change folder or
  printer. Commands never wait for it. A cover is a JPEG of at most 1 MB; a bigger one is not fetched whole.
- **Urgent commands:** emergency stop, pause and cancel each get their own short-lived thread, so they
  never wait behind a long job like a bed mesh. Downloads and Save picture also get their own thread.
- **Monitor:** polls status every 2 s, follows RFID and Spoolman changes, and fetches camera frames at
  most `camera_fps` per second (5 by default; see docs/settings.md), one at a time: the next is fetched
  once the page has shown the last one (or after 2 s). An unchanged picture is not sent again and slows
  the fetching down to once a second until the picture changes (docs/settings.md). It only runs while the page holds a lease, which the page renews every 2 s.
  The lease lapses after 6 s. Status and camera have separate errors and retries: a broken camera shows
  its own message and never delays status, RFID or Spoolman follow. While the firmware answer was unclear
  it checks the firmware again every 30 s (see docs/firmware.md). It keeps the last camera frame for
  Save picture (`snapshot`), which only writes it to a local file.
- **Job tracker:** follows every printer with a print u1control sent (`print_stats` every 5 s unless the
  monitor just looked), whether the page is open or not, and books its filament use when it finishes.
- **Presence:** rewrites `<data folder>/u1control/presence.json` every 5 s from load to unload (see
  docs/spooler-contract.md, "Detecting Spooler").
- **Preset work:** changes to presets (adding the print setup step, putting filament profiles into
  the project) run on a plugin thread, one at a time, never on the UI thread.

A generation counter tags each printer target. Every request carries the generation and client of the
printer that was selected when it arrived (the page also sends the generation it shows). A queued
request whose printer is no longer selected is refused before it does anything, and a running one stops
before its next printer or Spoolman call. Results, status, frames and screen pictures about the old
printer are dropped. When the selection is not a usable U1, the service lets go of the old printer and
the page clears what it showed, including open confirmations. Emergency stop, pause and cancel go to the
printer they were pressed for, on their own thread.

## Print setup flow

1. OrcaSlicer exports the G-code and calls the capability at `psGCodePostProcess`.
2. Exporting to a file: u1control applies the G-code fixes and returns.
3. Sending to the printer: u1control reads the printer's state and refuses if it is busy. It then maps
   filaments to toolheads and decides whether the pop-up is needed (see `u1.needs_dialog`).
4. The pop-up is a modal window. It refreshes the toolheads while it is open and gives up after
   15 minutes.
   When the chosen mapping has warnings (empty toolhead, other material; `u1.warning_ids`), the pop-up
   sends them back as `acknowledged` only after the user ticks the confirmation; the plugin compares them
   with the warnings of the mapping and the toolheads it last showed, and sends nothing when they differ.
5. u1control writes the fixed G-code, then sends `SET_PRINT_EXTRUDER_MAP`, `SET_PRINT_USED_EXTRUDERS`
   and `SET_PRINT_PREFERENCES`. OrcaSlicer then uploads the file and starts the print.

## Page protocol

The page and the plugin exchange JSON through `orca.postMessage` and `post_message`.

Page to plugin:

| type | fields | effect |
|---|---|---|
| `hello` | `id` | resolve the printer, connect, send `config`; with no usable U1 the error reply has `no_target: true` |
| `lease` | `camera`, `screen`, `stock` | keep the monitor running; camera and remote screen on or off; `stock`: the Stock tab or the Dashboard is on screen, so Spooler keeps its list fresh |
| `cmd` | `id`, `cmd`, `args`, `gen` | run `Service.cmd_<cmd>(**args)` for printer generation `gen`; `stock` and `stock_assign` (`head`, `spool_id`, `key`, `force`) are the Stock tab's |
| `frame_ack` | | the page has shown the last camera frame |
| `camera_fps` | `value` | store the camera frame rate (5, 10, 15 or 30) and use it at once |
| `save_settings` | `settings` | validate and store settings |
| `sync_project` | `auto` | put filament profiles into the project |

Plugin to page:

| type | fields |
|---|---|
| `reply` | `id`, `result` or `error` (`connect` also returns `limits`: the hotend/bed °C the plugin clamps to) |
| `status` | `data` (see `u1.summarize`; also `bindings` and `firmware`, which the page follows when the plugin learns more) |
| `frame` | `image` (JPEG data URL) |
| `screen` | `image` (PNG data URL), sent only when the touchscreen changed |
| `screen_error` | `error` (remote screen off or unreachable; retried every 5 s) |
| `rfid` | `heads` (changed indices), `tags` |
| `config` | settings, Automagic metadata, Spooler state, version, `pipeline` (`preset`, `on`: whether the selected U1 process preset runs U1 print setup; null without a U1 preset) |
| `notice` | `text` |
| `offline` | `error` |
| `selection_changed` | |

To add a command, write `cmd_<name>` in `service.py`, call it from the page with `run({cmd: "<name>", ...})` (`ui/src/app/store.ts`), then `npm run build` in `ui/`,
and add a test that drives it against the fake printer.
