# Settings

All settings live in one file, `settings.json`, in the plugin's storage folder. Every part of the
plugin uses the same file. Change them on the **Settings** page of the U1 Control tab.

## Mode

- **Automagic** (default): every setting below uses its Automagic value.
- **Expert**: you set each one. Your Expert values are kept while Automagic is on.

## Automations

| Setting | Key | Automagic value | Choices | What it does |
|---|---|---|---|---|
| Add "U1 print setup" to U1 process presets | `auto_add_pipeline` | on | on / off | Adds it to the Slicing Pipeline Plugin setting of your U1 process preset (save the preset to keep it). |
| Print setup pop-up | `print_dialog` | auto | auto / always / never | auto: only when something needs a decision (mapping warnings, ambiguous mapping, first print, unknown printer options). never: refuses to send when the mapping has warnings. |
| Top cover (purifier) mode | `purifier` | auto | auto / keep-warm / weak / strong / off | auto follows Snapmaker's softening-temperature rule. |
| Wait for chamber temperature | `chamber_wait` | on | on / off | Adds WAIT_CHAMBER_TEMP after bed heat-up when missing. |
| Whole-bed bed mesh | `whole_bed_mesh` | on | on / off | 11x11 mesh instead of adaptive (the U1 keeps one mesh). |
| Part fan off while probing | `fan_off_probing` | on | on / off | As Snapmaker Orca. |
| Print-by-object tool-change lift fix | `by_object_lift_fix` | on | on / off | Snapmaker Orca fix #958. |
| Real total layer count | `real_total_layers` | on | on / off | For the touchscreen's layer counter. |
| Recolour file metadata | `recolour_metadata` | on | on / off | Shows the assigned heads' colours in the printer's file list. |
| Remember print options | `remember_print_options` | on | on / off | Reuse the options chosen in the pop-up. |
| Apply RFID tags to project filaments | `rfid_auto_sync` | on | on / off | When a toolhead reads a new tag. |
| Bind a spool when a toolhead changes | `spoolman_auto` | on | on / off | Picks the closest Spoolman spool. |
| Report filament use to Spoolman | `spoolman_report_usage` | on | on / off | Deducts each head's grams when a print finishes. |
| Write the bound spool to the toolhead | `spoolman_write_printer` | on | on / off | Sends the spool's vendor, material and colour to the head. |
| Print option: auto bed leveling | `bed_level` | on | on / off | Default for the print setup. |
| Print option: flow calibration | `flow_calibrate` | on | on / off | Default for the print setup. |
| Print option: time-lapse | `time_lapse_camera` | off | on / off | Default for the print setup. |

## Connection (both modes)

| Key | Default | Meaning |
|---|---|---|
| `host` | `""` | Printer address. Blank uses the address of the selected U1 printer preset. |
| `api_key` | `""` | Moonraker API key, only when the printer requires one. Never sent to the page. |
| `printer_name` | `Snapmaker U1` | Prefix of the Spoolman location that links a spool to a toolhead. Always ends in "U1". |
| `spoolman_url` | `""` | Spoolman address. Blank uses the printer's own Spoolman link when it has one. |
| `profile_overrides` | `{}` | Map from a tag to an exact OrcaSlicer filament preset, see below. |

## Profile overrides

`profile_overrides` picks an exact filament preset for a tag, ahead of the automatic choice. Keys are
checked in this order and are not case sensitive; a key only counts when the preset exists.

```json
{
  "UID:04A1B2C3D4E5F6": "My PLA Black @Snapmaker U1",
  "SKU:10001": "Snapmaker PLA SnapSpeed @U1",
  "Polymaker|PLA|Matte": "Polymaker PLA Matte @Snapmaker U1",
  "Polymaker|PETG|": "Polymaker PETG @Snapmaker U1"
}
```

