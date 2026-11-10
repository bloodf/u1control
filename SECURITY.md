# Security

u1control talks only to your printer and, if you set one up, your Spoolman server, on your local
network. It has no cloud service and sends nothing to the internet.

## What it touches

- **Printer:** Moonraker over plain HTTP, the way OrcaSlicer itself does. Use it on a network you trust.
- **API key:** if you enter one, it stays in the plugin's settings file and in memory. It is never sent
  to the page or written to logs.
- **Files:** the plugin edits the G-code OrcaSlicer is exporting, keeps its settings in its own storage
  folder, and saves downloaded time-lapses to `~/Downloads/u1control`, never overwriting a file.
- **Spooler:** it reads Spooler's `profiles.json`, `keep_slots.json` and settings file and never
  writes them.

Deleting files, loading or unloading filament, calibration, emergency stop and Extended Firmware
changes all ask first.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private
[security advisory](https://github.com/bloodf/u1control/security/advisories/new) form and include the
version, what an attacker can do, and how to reproduce it. You'll get an answer within a week.
