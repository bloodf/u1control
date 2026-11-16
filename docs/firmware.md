# Firmware

u1control talks to the U1 through Moonraker over HTTP: port 80 through the printer's web server, or
port 7125 directly. A few calls only exist over Moonraker's websocket. Everything below comes from
Snapmaker's open [u1-klipper](https://github.com/Snapmaker/u1-klipper) and
[u1-moonraker](https://github.com/Snapmaker/u1-moonraker) sources and from the
[U1 Extended Firmware](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware).

## Telling the firmwares apart

- `GET /printer/info` → `software_version` contains `-paxx12` on the Extended Firmware.
- `GET /firmware-config/api/status` answers with JSON on the Extended Firmware when Advanced Mode is
  on. On stock firmware the web server returns its HTML page instead.

Only a clear answer decides: JSON, the HTML page, or a 4xx. A timeout, a refused connection, a 5xx or a
broken answer leaves the kind as it was (stock on a first connect) and the tab asks again every 30 s, and
once more after the printer was offline, so a printer whose Firmware Config API was still starting, or
that was reflashed, is shown right without selecting it again. An unclear answer never turns an Extended
printer back into stock. Filament use of a print sent earlier is not booked while its printer's firmware
can't be told: SpoolLink books it on the Extended Firmware, so guessing could book it twice.

## Printer objects read

`print_stats`, `virtual_sdcard` (incl. `pl_env_valid` for power-loss recovery), `display_status`,
`print_task_config` (filament per head, mapping, print options, `filament_spool_id` on the Extended
Firmware), `filament_detect` (RFID tags), `filament_feed left|right` (feeder state per head),
`machine_state_manager` (idle, printing, loading, calibrating, ...), `exception_manager`, `purifier`,
`led cavity_led`, `heater_bed`, `extruder`…`extruder3`, `toolhead`, `gcode_move`, `fan`.

## Commands sent

| Purpose | Command |
|---|---|
| Mapping before a print | `SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=<filament> MAP_EXTRUDER=<head>` |
| Heads in use | `SET_PRINT_USED_EXTRUDERS EXTRUDERS=<list>` |
| Print options | `SET_PRINT_PREFERENCES BED_LEVEL= FLOW_CALIBRATE= TIME_LAPSE_CAMERA= ...` |
| Filament in a head | `SET_PRINT_FILAMENT_CONFIG CONFIG_EXTRUDER= VENDOR= FILAMENT_TYPE= FILAMENT_SUBTYPE= FILAMENT_COLOR_RGBA=` (`FORCE=1` only when you confirm overwriting an RFID spool) |
| Spool in a head (Extended Firmware) | `SET_SPOOL_ID CHANNEL=<head> SPOOL_ID=<id>` |
| Load / unload | `AUTO_FEEDING EXTRUDER=<head> LOAD=1` / `UNLOAD=1` |
| Read the tag again | `FILAMENT_DT_UPDATE CHANNEL=<head>` |
| Top cover | `SET_PURIFIER_MODE MODE=...` |
| Chamber light | `SET_LED LED=cavity_led WHITE=0|1 SYNC=0` |
| Calibration | `AUTO_BED_MESH_CALIBRATE`, `SHAPER_CALIBRATE`, `FLOW_CALIBRATE` |
| Power-loss recovery | `SDCARD_PRINT_PL_RESTORE`, `SDCARD_PRINT_PL_CLEAR_ENV` |
| Temperatures, speed | `M104 T<head> S<t>`, `M140 S<t>`, `M220 S<percent>` |

Mapping, used heads and print options are refused by the firmware once a print runs, which is why
they are sent before the upload and not written into the G-code.

## Printer agent (u1control as OrcaSlicer's agent)

| Purpose | Call |
|---|---|
| Status for the Device tab and the print dialog (every 2 s while connected) | `GET /printer/objects/query` with the objects above, `GET /printer/info` once |
| Upload the job | `POST /server/files/upload` (multipart, `root=gcodes`) |
| Toolhead map and print options | the three commands above, in one `POST /printer/gcode/script`, after the upload |
| Start | `POST /printer/print/start` (Moonraker sends `SDCARD_PRINT_FILE`) |
| Device tab | `POST /printer/print/pause`, `/resume`, `/cancel`; `SET_LED LED=cavity_led WHITE=0|1 SYNC=0`; G-code lines as sent |

The print dialog's boxes map to `SET_PRINT_PREFERENCES`: Auto Bed Leveling → `BED_LEVEL`, Flow Dynamics
Calibration → `FLOW_CALIBRATE`, Timelapse → `TIME_LAPSE_CAMERA`. Untested on a printer: that OrcaSlicer
shows the last two for `support_flow_calibration` / `support_timelapse` in the push, that the dialog's slot
ids arrive as toolheads 0-3, and that the two options take effect when set this way.

`SDCARD_PRINT_FILE_WITH_PARAMETERS` (firmware 2.1.0, `virtual_sdcard.py`) would set the map and options in
the start command itself, but there is no read-only way to tell whether older firmware has it, so it is
not used.

## Firmware settings during a print

Changing an Extended Firmware setting runs the option's command on the printer. Most of them restart
Klipper or reboot, which ends a running print, so while the U1 is printing or paused u1control refuses
them (the page disables their Apply button and says why), together with Restart Klipper and Reboot.

These stay available during a print, because their commands only restart nginx, Moonraker, SSH, the USB
camera, the remote screen, VPN, cloud or metrics services, or the Firmware Config service itself:
`web-frontend`, `firmware-config`, `remote-screen`, `ssh`, `camera-usb`, `camera-usb-resolution`,
`camera-rtsp`, `vpn`, `cloud`, `object_processing`, `spoolman_tag_store`, `klipper-metrics`, and the
Restart Moonraker action. Every other setting waits, including any setting a newer firmware release adds.
The list (`extended.PRINT_SAFE`) comes from the option commands in the firmware's
`firmware-config/functions/*.yaml` (main branch of 2026-11-07).

## Endpoints

| Endpoint | Use |
|---|---|
| `GET /printer/objects/query` | status |
| `POST /printer/gcode/script` | the commands above |
| `POST /printer/print/start`, `/pause`, `/resume`, `/cancel` | print control |
| websocket `printer.emergency_stop` | emergency stop (U1 offers it over websocket only); `M112` as fallback |
| websocket `camera.start_monitor` | wakes the stock camera every 50 s |
| `GET /server/files/camera/monitor.jpg` | stock camera frame |
| `GET /webcam/snapshot.jpg` | Extended Firmware camera frame |
| `GET /screen/snapshot` | Extended Firmware Remote Screen: the touchscreen as PNG (Settings > Firmware > Remote Screen must be on) |
| `POST /screen/touch?a=tap&x=&y=` | tap the touchscreen at a framebuffer pixel |
| `GET /server/files/directory`, `/metadata`, `DELETE /server/files/...` | file manager (`gcodes` and `camera` roots) |
| `GET /server/files/roots`, `GET /server/files/list?root=timelapse`, `GET` and `DELETE /server/files/timelapse/...` | time-lapses: the videos (`<print>_<YYYYMMDDHHMMSS>.mp4`), their cover (`..._cover.jpg`) and last frame (`....jpg`). Seen on a U1 on 2026-11-16: `timelapse` and `camera` are the same folder (`/oem/printer_data/camera`), `timelapse` with `rw` and `camera` with `r`, so a `DELETE` under `camera` answers 405 (u1-moonraker `file_manager.py`, `delete_file`). The root is not registered in u1-moonraker's public source; a printer without it gets "This printer shares no time-lapse folder" |
| `POST /server/files/directory`, `POST /server/files/move` | new folder; move or rename a file or folder (same root only; the folder is listed first and a name it already has is refused) |
| `GET /server/spoolman/status`, `POST /server/spoolman/proxy` | the printer's own Spoolman link |
| `GET /server/gcode_store?count=` | console: the printer's replies logged since a command (u1-moonraker `data_store`) |
| `/firmware-config/api/status`, `/settings`, `/settings/<id>/<value>`, `/action/<id>` | Extended Firmware settings: groups of settings, each option with its label and, when the firmware sets them, a confirmation text, required inputs or `hidden`. Only a log ending in `SUCCESS` counts as applied; a log that ends without `SUCCESS` or `ERROR` is shown as unknown and is not retried |

## Not supported

- Toolhead XYZ offset calibration needs someone at the printer to clean the nozzles, so it stays on
  the touchscreen.
- Snapmaker's MQTT / cloud protocol isn't used.
