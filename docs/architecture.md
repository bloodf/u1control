# Architecture

u1control ships as a standard pure-Python wheel, `u1control_any.whl`, which OrcaSlicer loads as a
plugin. The sources live in `src/u1control/`, and `scripts/build.py` packs them.

## Modules

| Module | Job | Uses `orca`? |
|---|---|---|
| `moonraker.py` | HTTP client for Moonraker (port 80, then 7125) and a small websocket client for the calls Moonraker only offers over websocket | no |
| `u1.py` | U1 knowledge: toolheads, print options, filament mapping, RFID tags, top-cover rule, command builders | no |
| `gcode.py` | Reads exported G-code and applies the U1 fixes | no |
| `extended.py` | Client for the Extended Firmware's Firmware Config API | no |
| `spoolman.py` | Spoolman client and spool matching | no |
| `settings.py` | The shared settings store and the Automagic / Expert rules | no |
| `spooler_bridge.py` | Finds Spooler and reads its `profiles.json` and `keep_slots.json` | no |
| `service.py` | Runs printer work for the U1 Control tab: command worker, status monitor, camera, Spoolman follow | no |
| `plugin.py` | OrcaSlicer glue: the capabilities, settings wiring, preset changes | yes |
| `ui/app.html`, `ui/setup.html` | The U1 Control tab and the print setup pop-up | — |

Only `plugin.py` imports `orca`, so everything else is tested without OrcaSlicer.

The wheel is the package `u1control`: `plugin.py` becomes `u1control/__init__.py`, each module keeps
its name (`u1control.service`, and so on), and `u1control/_assets.py` holds the HTML pages and SVG
icons as string constants. Nothing is embedded as source text or executed at load time, and the
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
- **Urgent commands:** emergency stop, pause and cancel each get their own short-lived thread, so they
  never wait behind a long job like a bed mesh. Downloads also get their own thread.
- **Monitor:** polls status every 2 s, follows RFID and Spoolman changes, and fetches camera frames at
  most about 5 per second. It only runs while the page holds a lease, which the page renews every 2 s.
  The lease lapses after 6 s.
- **Preset work:** changes to presets (adding the print setup step, putting filament profiles into
  the project) run on a plugin thread, one at a time, never on the UI thread.

A generation counter tags each printer target. When you switch printers, results that come back for
the old printer are dropped.

## Print setup flow

1. OrcaSlicer exports the G-code and calls the capability at `psGCodePostProcess`.
2. Exporting to a file: u1control applies the G-code fixes and returns.
3. Sending to the printer: u1control reads the printer's state and refuses if it is busy. It then maps
   filaments to toolheads and decides whether the pop-up is needed (see `u1.needs_dialog`).
4. The pop-up is a modal window. It refreshes the toolheads while it is open and gives up after
   15 minutes.
5. u1control writes the fixed G-code, then sends `SET_PRINT_EXTRUDER_MAP`, `SET_PRINT_USED_EXTRUDERS`
   and `SET_PRINT_PREFERENCES`. OrcaSlicer then uploads the file and starts the print.

## Page protocol

The page and the plugin exchange JSON through `orca.postMessage` and `post_message`.

Page to plugin:

| type | fields | effect |
|---|---|---|
| `hello` | `id` | resolve the printer, connect, send `config` |
| `lease` | `camera`, `screen` | keep the monitor running; camera and remote screen on or off |
| `cmd` | `id`, `cmd`, `args` | run `Service.cmd_<cmd>(**args)` |
| `frame_ack` | | the page has shown the last camera frame |
| `save_settings` | `settings` | validate and store settings |
| `sync_project` | `auto` | put filament profiles into the project |

Plugin to page:

| type | fields |
|---|---|
| `reply` | `id`, `result` or `error` |
| `status` | `data` (see `u1.summarize`) |
| `frame` | `image` (JPEG data URL) |
| `screen` | `image` (PNG data URL), sent only when the touchscreen changed |
| `screen_error` | `error` (remote screen off or unreachable; retried every 5 s) |
| `rfid` | `heads` (changed indices), `tags` |
| `config` | settings, Automagic metadata, Spooler state, version |
| `notice` | `text` |
| `offline` | `error` |
| `selection_changed` | |

To add a command, write `cmd_<name>` in `service.py`, call `call("<name>", {...})` from `app.html`,
and add a test that drives it against the fake printer.
