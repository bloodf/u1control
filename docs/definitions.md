# Definitions

The terms used in the code, the UI and the docs.

**Toolhead (head, T1–T4).** One of the U1's four print heads. The code counts from 0 (head 0–3); the
UI counts from 1 (T1–T4).

**Filament (filament index).** A filament slot in the OrcaSlicer project. The U1 accepts up to 32. A
print uses some of them; each one is printed by one toolhead.

**Mapping.** Which toolhead prints each filament, sent as `SET_PRINT_EXTRUDER_MAP`. Several filaments
can share a toolhead.

**Print options.** The printer's per-print settings, sent as `SET_PRINT_PREFERENCES`: auto bed
leveling, flow calibration, time-lapse, auto-refill, tangle detection, unload when done and light off
when done. The first three exist on every firmware. The others are offered only when the printer
reports them.

**Print setup.** The Slicing Pipeline capability, and its pop-up, that sets the mapping and print
options when you send a print.

**Top cover / purifier.** The U1's top cover with its filter fan. Its modes are strong cooling, weak
cooling and keep warm. Snapmaker's rule: if any filament in the print softens at 50 °C or below, use
strong cooling; else if any softens at 70 °C or below, weak cooling; otherwise keep warm.

**Softening temperature.** OrcaSlicer's `temperature_vitrification`. When the profile leaves it at
OrcaSlicer's default of 100, u1control uses a value per material type instead.

**RFID tag.** The chip on a spool, read by the U1 when filament goes into a toolhead's inlet. Stock
firmware reads Snapmaker tags. The Extended Firmware also reads OpenRFID, OpenSpool and NTAG tags and
accepts external readers. All of them report into Klipper's `filament_detect` object.

**Official filament.** A head whose filament came from a Snapmaker RFID tag. Its data is locked on the
printer; overwriting it needs `FORCE=1` and resets that head's flow calibration. u1control never does
that automatically.

**Binding.** Which Spoolman spool is in which toolhead. On the Extended Firmware it is the printer's
`filament_spool_id` (SpoolLink). On stock firmware it is the spool's Spoolman location,
`"<printer name> T<n>"`.

**Printer name.** The prefix of that Spoolman location, `Snapmaker U1` by default. It always ends in
"U1" so that Spooler recognises it.

**SpoolLink.** The Extended Firmware's Spoolman link. It keeps one spool per toolhead and switches
Moonraker's active spool on every tool change.

**Stock firmware / Extended Firmware.** Snapmaker's firmware, and paxx12's community
[U1 Extended Firmware](https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware). u1control
tells them apart by `-paxx12` in the Klipper version or by the Firmware Config API answering.

**Advanced Mode.** A printer setting that the Extended Firmware's config API and config writes need.

**Automagic / Expert.** The two settings modes. In Automagic every automation uses its built-in value.
In Expert you set each one yourself. Connection settings apply in both modes.

**Lease.** The page's "I'm still open" signal. The monitor and camera stop when it lapses.

**Spooler.** A separate OrcaSlicer plugin by the same author. It turns Spoolman filaments into
OrcaSlicer filament profiles. Optional; see [spooler-contract.md](spooler-contract.md).

**Snapmaker Orca.** Snapmaker's fork of OrcaSlicer. Several of u1control's G-code fixes and its
process tuning come from it.
