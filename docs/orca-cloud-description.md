# Orca Cloud description

The text of the [U1 Control listing](https://cloud.orcaslicer.com/p/55b8c347d443), in English only: paste the block into the listing's description. It stays well under Orca Cloud's 4000 characters and links to the README for everything else. The images it embeds are served from `main`, so they show once this file's commit is merged. The listing's own images (tile, main, gallery) are in [release.md](release.md#orca-cloud-listing). Keep the plugin list in step with the README's "More plugins by bloodf" table.

```markdown
Run the Snapmaker U1 from OrcaSlicer: toolheads, camera, files.

Full description: https://github.com/bloodf/u1control/blob/main/README.md

## What it does

![The U1 print setup window: four filaments matched to the toolheads T1 to T4](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/u1control-feature-01-setup-en.png){align=center}

**Print setup.** On Print, each filament is matched to a toolhead and the U1 G-code is fixed, as Snapmaker Orca does. A nozzle mismatch (Standard vs High Flow) is a warning you confirm.

![The Dashboard in its default layout: the print, the toolheads, temperatures, controls, camera and printer screen](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/u1control-feature-02-dashboard-en.png){align=center}

**Dashboard.** Print, temperatures, fans, controls, camera, printer screen and console, in a layout you can rearrange. Bed, nozzle, fans and Home also work from OrcaSlicer's Device tab.

![The toolheads T1 to T4 with filament, RFID tag, Spoolman spool and grams left](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/u1control-feature-03-filament-en.png){align=center}

**Toolheads and spools.** Filament, RFID tag, Spoolman spool, the preset each head gets (change it if you like) and pressure advance saved per spool. Open Filament Database presets are opt-in.

![The Files page: folders, print files and the time-lapse list](https://raw.githubusercontent.com/bloodf/u1control/main/assets/orca-cloud/u1control-feature-04-files-en.png){align=center}

**Files.** Print, rename, move and delete files, and save time-lapse videos.

Works with the stock firmware and the U1 Extended Firmware. With [multiACE](https://github.com/decay71/multiACE), U1 Control leaves routing to it and shows the ACE units.

## How to start

1. Subscribe, open the plugin list (macOS: File > Plugins; Windows/Linux: ▾ next to File > Plugins) and tick Activate on U1 Control. Allow the background thread.
2. Select your Snapmaker U1 printer preset and enter its IP address (the Wi-Fi icon next to the printer name). The U1 Control tab appears next to Prepare and Preview.
3. Automagic mode adds U1 print setup to your U1 process preset. Save the preset, slice and press Print.

Needs OrcaSlicer 2.5.0 or newer. Spoolman is optional.

## Privacy

Talks only to your printer and your Spoolman server, on your local network; the Open Filament Database only if you turn it on. No cloud, no telemetry. Deleting, filament moves, calibration and emergency stop ask first.

Independent project, not made or supported by Snapmaker. English, Português, Español, Deutsch, 简体中文, Polski, Čeština.

## More plugins by bloodf

[Organizer](https://cloud.orcaslicer.com/p/5bf381fd42d4) · [Embedder](https://cloud.orcaslicer.com/p/58222d4f9e52) · [Print Calculator](https://cloud.orcaslicer.com/p/521c07cf6de2) · [Spooler](https://cloud.orcaslicer.com/p/50c35dcbd6f3) · [Kobra Control](https://cloud.orcaslicer.com/p/59c786285255)

Source: https://github.com/bloodf/u1control (GPL-3.0-only)
```
