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
| `POST /server/files/directory`, `POST /server/files/move` | new folder; move a file or folder (same root only) |
| `GET /server/spoolman/status`, `POST /server/spoolman/proxy` | the printer's own Spoolman link |
| `GET /server/gcode_store?count=` | console: the printer's replies logged since a command (u1-moonraker `data_store`) |
| `/firmware-config/api/status`, `/settings`, `/settings/<id>/<value>`, `/action/<id>` | Extended Firmware settings: groups of settings, each option with its label and, when the firmware sets them, a confirmation text, required inputs or `hidden`. Only a log ending in `SUCCESS` counts as applied; a log that ends without `SUCCESS` or `ERROR` is shown as unknown and is not retried |

## Not supported

- Toolhead XYZ offset calibration needs someone at the printer to clean the nozzles, so it stays on
  the touchscreen.
- Snapmaker's MQTT / cloud protocol isn't used.
