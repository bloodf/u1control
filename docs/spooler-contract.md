# Spooler contract

[Spooler](https://github.com/bloodf/spooler) (0.10.0 or newer) and u1control can run side by side.
Spooler is optional. This is what each side does so the two never fight.

## Which spool is in which toolhead

1. **Extended Firmware:** the printer's `print_task_config.filament_spool_id[n]`. u1control sets it
   with `SET_SPOOL_ID`; Spooler reads it first.
2. **Stock firmware:** the spool's Spoolman location, `"<printer name> T<n>"` with n = 1–4, for
   example `Snapmaker U1 T1`. u1control writes it; Spooler reads it and never writes a location. The
   printer name always ends in "U1"; Spooler accepts its own printer label, the printer model, or any
   name ending in "U1".
3. If neither applies, Spooler falls back to the RFID tag, then vendor, material and colour. When
   u1control links a spool it also writes the spool's vendor, material, name and colour to the head,
   so that fallback lands on the same spool.

## Filament profiles

Spooler writes `<OrcaSlicer data folder>/spooler/profiles.json`:

```json
{"version": 1, "updated": 1794300000,
 "filaments": {"42": {"Snapmaker U1": "_local/spooler/Polymaker PLA Matte Black @Snapmaker U1"}}}
```

When u1control puts filament profiles into the project, it uses that file to pick the exact Spooler
profile for each linked spool. Without the file, or without a linked spool, it falls back to the
nearest colour among Spooler's profiles, then to its own matcher.

## Keep Slots Synced

While Spooler's "Keep Slots Synced" runs, Spooler refreshes
`<OrcaSlicer data folder>/spooler/keep_slots.json` about every 5 seconds:

```json
{"active": true, "printer": "Snapmaker U1", "ts": 1794300000}
```

While the marker is active, younger than 30 seconds and names the selected printer, u1control skips
its automatic project sync. Running it by hand still works and uses Spooler's profiles.

## Filament use

Only u1control records U1 filament use in Spoolman, per toolhead, when a print finishes. Spooler never
records use for Moonraker printers. On the Extended Firmware, SpoolLink and Moonraker record use and
u1control records nothing.

## Detecting Spooler

u1control treats Spooler as installed when the local preset bundle `spooler` exists, when any filament
preset comes from it, or when `<OrcaSlicer data folder>/spooler/spooler_settings.json` exists. Without
Spooler, the U1 Control tab suggests it once; you can dismiss the suggestion.

## Tests

`tests/test_spooler_joint.py` loads both built plugins against one fake U1 and one fake Spoolman and
checks every point above. It needs a Spooler checkout: set `SPOOLER_SRC`, or keep `spooler` next to
this repository.
