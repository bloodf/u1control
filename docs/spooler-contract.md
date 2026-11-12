# Spooler contract

[Spooler](https://github.com/bloodf/spooler) (0.10.0 or newer) and u1control can run side by side.
Spooler is optional. This is what each side does so the two never fight. The stock list in the U1 Control
Dashboard uses Spooler's presence and stock-list API, which first shipped in Spooler 0.21.0; the joint tests of
u1control 0.4.0 run against the Spooler release `v0.21.0`. With an older Spooler the two still share profiles and
bindings, but the Dashboard shows no Spooler stock.

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
profile for each linked spool. It reads only `"version": 1` with `filaments` as an object of objects
whose values are preset names; any other version or shape is ignored (logged) as if the file were
missing. Without the file, or without a linked spool, it falls back to the
nearest colour among Spooler's profiles, then to its own matcher.

## Keep Slots Synced

While Spooler's "Keep Slots Synced" runs, Spooler refreshes
`<OrcaSlicer data folder>/spooler/keep_slots.json` about every 5 seconds:

```json
{"active": true, "printer": "Snapmaker U1", "ts": 1794300000}
```

While the marker is active (`"active": true`), younger than 30 seconds (`ts` a number) and names the
selected printer, u1control skips its automatic project sync. Running it by hand still works and uses
Spooler's profiles. A fresh marker without a `printer` label also pauses the automatic sync, for any
printer: u1control can't tell which printer it is for, and two automations writing the same project
slots would fight. A marker of another shape counts as inactive.

## Filament use

Only u1control records U1 filament use in Spoolman, per toolhead. Spooler never records use for
Moonraker printers. On the Extended Firmware, SpoolLink and Moonraker record use and u1control records
nothing; the same when the printer's own Moonraker Spoolman link is on.

What u1control books, and when:

- Only prints sent through the U1 print setup step, with the grams Orca estimated per filament. Prints
  started elsewhere (touchscreen, Files tab, another slicer) are not booked.
- A job is that printer (its address) plus that file path. The same name in another folder, or on
  another printer, is a different job.
- It is booked once its printer reports that file `printing` (or `paused`) and then `complete`, whether
  the U1 Control tab is open or not. The spools are the ones linked to the toolheads when the job was
  sent; when that wasn't known (the tab showed another printer), the links in Spoolman when it finished.
- Cancelled or failed prints are not booked (partial use is unknown). A print seen finishing but never
  seen printing is not booked either; it is listed as unconfirmed and the tab says so.
- One Spoolman call per toolhead. Spoolman's "use" adds weight, so a call that fails may or may not
  have been applied: it is listed as unconfirmed, the tab names the spool and grams to check, and it is
  never repeated by itself. Toolheads not tried yet are tried again a minute later.
- Pending jobs are kept in `usage_ledger.json` in u1control's storage folder, replaced whole after
  every change (no API key in it), so they survive closing OrcaSlicer. Each toolhead's use is saved as
  "sending" before its Spoolman call; one still "sending" when the file is read again (OrcaSlicer closed
  or crashed during the call) may have been applied, so it is listed as unconfirmed and never sent again.
  A job seen printing before the restart is only booked if u1control sees it printing again; seen
  finished, cancelled or replaced by another file, it is listed as unconfirmed (or, cancelled, dropped)
  because u1control can't tell that print from a later one. A job not finished within 3 days is dropped
  with a notice. An unreadable ledger file is set aside (`usage_ledger.json.bad-<time>`), never
  overwritten. Nothing reconciles with Spoolman on its own: "use" adds weight and has no request id, so
  exactly-once is not possible; unconfirmed entries name the spool and grams to check.
- Each unconfirmed entry has an `id`, the time it was listed (`at`; unknown for entries from older files),
  printer, file, toolhead, spool and grams. `cmd usage` returns them with the ledger's notices (file set
  aside, unreadable entries skipped, can't be saved). After checking the spool in Spoolman yourself,
  `cmd usage_ack {id}` moves the entry to `acknowledged` in the same file with `acknowledged_at`. That is
  a local note only: it sends nothing to Spoolman and is not a confirmation from Spoolman. There is no
  "book it now" action, because u1control can't prove the earlier call wasn't applied.

## Detecting Spooler

Installed is not running. OrcaSlicer's plugin API has no call that lists loaded plugins or passes
messages between them, and no way to hide a tab (checked against OrcaSlicer's `PythonPluginBridge.cpp`,
`host/PluginHost.cpp`, `host/PluginPages.cpp` and its Pages and Registry docs). Its data folder is
shared and writable by every plugin, so the two plugins use presence files there.

- **Installed** (for the one-time suggestion only): the local preset bundle `spooler` exists, a filament
  preset comes from it, or `<OrcaSlicer data folder>/spooler/spooler_settings.json` exists.
- **Running**: `<OrcaSlicer data folder>/spooler/presence.json` says `"state": "active"`, was refreshed
  within 20 seconds (Spooler refreshes it every 5) and carries this OrcaSlicer's process id. A file left
  behind by an uninstalled, disabled, crashed or other OrcaSlicer never counts. U1 Control writes its own
  `<OrcaSlicer data folder>/u1control/presence.json` the same way. Each plugin says `"stopped"` when
  it unloads.

```json
{"schema": "orca-plugin-presence", "version": 1, "plugin": "spooler", "plugin_version": "0.20.1",
 "session": "9f2c41d07a6b3e85", "pid": 4242, "started": 1794300000, "ts": 1794300125.4, "state": "active",
 "provides": {"stock": 1}, "spoolman": {"source": "spoolman", "origin": "http://raspberrypi:7912"}}
```

`session` is new on every load, so a reloaded plugin is a different run. Any other `schema`, `version`
or `provides.stock` counts as incompatible and is said so in the tab. The Spoolman address is written
without user name or password.

## Stock from Spooler in the U1 Control tab

While Spooler runs in this OrcaSlicer, the Dashboard of the U1 Control tab gets a **Stock from
Spooler** card next to the camera, print status and toolheads: search, material filter, "same material
as the toolhead", remaining grams (low stock from Spooler's setting, "use first" from Spooler), and a
button per spool to link it to the chosen toolhead. Without Spooler the card isn't shown.

- U1 Control's presence says when its tab shows that card (`"wants": {"stock_until": <unix s>,
  "stock_request": <n>}`). Only then does Spooler write `<OrcaSlicer data folder>/spooler/stock.json`,
  from its own Spoolman reads and at most every 30 s (or when Refresh raises `stock_request`). Spooler
  writes nothing to Spoolman or a printer for it.
- `stock.json`: `{"schema": "spooler-stock", "version": 1, "session", "seq", "ts", "request",
  "origin": {"url", "gen", "source"}, "low_stock_grams", "spools": [{"id", "filament_id", "name", "vendor",
  "material", "colour", "colours", "remaining", "initial", "location", "low", "use_first", "u1_bound"}],
  "error"?}`. Archived spools are left out. A list from an earlier Spooler run or another spool source is
  not shown; a list older than 2 minutes is shown as out of date.
- Linking runs U1 Control's own bind command, on its own queue, for the printer the tab shows (requests
  for a printer no longer selected are refused). Before anything is written it checks that Spooler still
  runs with the list the tab showed (same `session` and source generation), that both plugins use the same
  Spoolman address (when U1 Control reaches Spoolman through the printer it can't know that address; then
  only the next check applies), and that U1 Control's own Spoolman read finds that spool with the same
  filament. Then the usual checks: the printer is idle, and an RFID / official head asks first and only
  then sends FORCE=1.
- Spooler's own tab stays, with its card actions and settings. OrcaSlicer adds a tab for every enabled
  Pages capability and offers no call to hide one; to keep a single tab, turn off Spooler's "Spooler" page
  in OrcaSlicer's Plugins dialog. OrcaSlicer still loads Spooler's other capabilities and calls their
  `on_load`, so presence, presets, Keep Slots Synced and the stock list keep working; Spooler's settings
  and card actions are then out of reach until the page is turned back on.
- Filament use is unchanged: U1 Control (stock firmware) or the printer (Extended Firmware / Moonraker
  link) records it, never Spooler. The card says which.

## Future readers (print calculator)

`profiles.json`, `keep_slots.json` and `spooler_settings.json` keep their format. A reader that wants
Spooler's stock can read `stock.json` under the rules above (presence active, same `session`, not older
than it can accept); nothing else is promised. No reader for it exists outside u1control today.

## Tests

`tests/test_spooler_joint.py` loads both built plugins against one fake U1 and one fake Spoolman and
checks every point above, discovery included (both load orders, unload, reload, linking from the stock
list, one booking per toolhead). `tests/test_unified.py` covers presence, the stock list and the print
ledger across restarts on their own. It needs a Spooler checkout: set `SPOOLER_SRC`, or keep `spooler` next to
this repository.
