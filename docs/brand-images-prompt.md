# Image set prompt (second pass)

Use this in the **same ChatGPT conversation** that produced the brand assets, so it reuses the
symbol, palette, fonts and icon set. Ask for one image per message. For anything with text or
precise geometry (diagrams, tables, step guides), ask for **SVG code** first and render it; use the
image generator only for compositions that contain no text.

Real screenshots of OrcaSlicer are taken by us later. Every image below that shows the product
leaves an empty, labelled frame for that screenshot instead of drawing fake UI.

Where each image goes:

| # | Image | File | Used in |
|---|---|---|---|
| 1 | README hero (dark / light) | `assets/readme/hero-dark.png`, `hero-light.png` | README top (`<picture>` dark/light) |
| 2 | Feature strip icons | `assets/readme/feature-*.svg` | README "Features" |
| 3 | How it works diagram | `assets/readme/how-it-works.svg` | README, Orca Cloud description |
| 4 | Firmware support matrix | `assets/readme/firmware-matrix.svg` | README, Orca Cloud description |
| 5 | Automagic vs Expert | `assets/readme/modes.svg` | README, Orca Cloud description |
| 6 | Works with Spooler | `assets/readme/spooler.svg` | README, Spooler README |
| 7 | Toolhead mapping explainer | `assets/readme/mapping.svg` | README "U1 print setup" |
| 8 | Install steps (4 cards) | `assets/readme/install-1..4.svg` | README "Install", Orca Cloud description |
| 9 | Screenshot frames | `assets/orca-cloud/frame-*.svg` | Orca Cloud store images (screenshot inside) |
| 10 | Orca Cloud main image | `assets/orca-cloud/main.png` | Plugin hub card |
| 11 | Release banner template | `assets/release/banner.svg` | GitHub release notes |
| 12 | Social posts | `assets/social/*.png` | Announcements |
| 13 | Empty states / notices | `src/u1control/ui/` (inline SVG) | Inside the plugin UI |

---

```text
Using the u1control brand system you created in this conversation (same symbol, wordmark,
lockups, palette incl. the four toolhead colours T1 coral #FF997D, T2 amber #F4CF78, T3 violet
#A99BFF, T4 teal #78CFD5, dark #14181F, light #F6F7FB, the primary colour we chose, the fonts and
the 24 px UI icon set), produce the following images. Same rules as before: strictly geometric
flat vector on an 8 px grid, consistent stroke weights, no gradients/glow/3D/noise/AI-art
textures, no stock people or robots, no fake UI, and NO text other than the exact strings I give
(spell them exactly; keep "u1control" lowercase). Never draw the Snapmaker logo or the U1
printer's industrial design; when the printer must appear, use an abstract box with four
toolhead circles. For each deliverable: give SVG code (text converted to paths unless I say
"live text", viewBox set, named groups), a PNG export at the stated size, and a self-check
listing every text string present, the hex codes used and contrast ratios of text.

1. README HERO, 1600x640, two versions (background #14181F and #FFFFFF):
   left: lockup + line "Snapmaker U1 control for OrcaSlicer" + line "Camera · Toolheads ·
   Spoolman · Files · Extended Firmware"; right: an empty rounded frame 16:10 with a thin border
   labelled nothing (a screenshot goes there), with the four toolhead colours as a geometric
   accent motif behind the frame's corner.

2. FEATURE STRIP: eight 96x96 tiles (rounded square, subtle tinted background from the palette,
   icon from the set, no text): print setup, live camera, toolheads + RFID, Spoolman, file
   manager, Extended Firmware, Snapmaker Orca fixes, Automagic. SVG each, consistent.

3. HOW IT WORKS diagram, 1600x900, live text in our UI font, light and dark versions. Boxes and
   arrows only, left to right:
   "OrcaSlicer 2.5" -> "u1control" -> "Snapmaker U1"; under "Snapmaker U1" two labels
   "Stock firmware" and "Extended Firmware"; a branch from "u1control" to "Spoolman" and to
   "Spooler (optional)". Arrow labels exactly: "slice & send", "toolheads & status",
   "spools", "filament profiles". A footer line: "Local network only · no cloud".

4. FIRMWARE SUPPORT MATRIX, 1600x900, live text, light and dark. Table with columns
   "Feature", "Stock firmware", "Extended Firmware" and rows exactly:
   "Print setup & toolhead mapping" ✓ ✓ / "Camera" ✓ ✓ / "Toolheads, load & unload" ✓ ✓ /
   "RFID: Snapmaker tags" ✓ ✓ / "RFID: OpenRFID, OpenSpool, NTAG" – ✓ /
   "Spoolman per toolhead" ✓ ✓ / "Files & time-lapses" ✓ ✓ / "Firmware settings" – ✓ /
   "Power-loss resume" ✓ ✓. Use our check and dash glyphs drawn as shapes, not emoji.

5. AUTOMAGIC VS EXPERT, 1600x900, live text, two columns with the automagic and expert icons.
   Left title "Automagic", line "Everything that can be automatic, is." bullets:
   "Adds U1 print setup to your process presets", "Maps filaments to toolheads",
   "Picks filament profiles from RFID tags", "Links spools in Spoolman",
   "Asks only when something needs you". Right title "Expert", line "Every step is a setting."
   bullets: "Choose when the print window opens", "Turn each G-code fix on or off",
   "Set print options and top-cover mode", "Control Spoolman linking and usage",
   "Override filament profiles per tag".

6. WORKS WITH SPOOLER, 1600x700, live text, light and dark. Two lockup cards side by side,
   "u1control" (our symbol) and "Spooler" (leave its logo as an empty square frame labelled
   nothing — I'll drop Spooler's own logo in), joined by a link glyph. Under them three short
   rows: "Same spool for every toolhead", "Spooler's filament profiles in your project",
   "Filament use booked once". Footer: "Spooler is optional — u1control works on its own."

7. TOOLHEAD MAPPING EXPLAINER, 1600x700, live text. Left: four filament swatches labelled
   "Filament 1" … "Filament 4" (colours: #E6483D, #F2F2F2, #1E1E1E, #2E7BE6). Right: the four
   toolhead badges T1–T4 from the brand kit, each showing a loaded spool colour. Curved
   connectors map 1->T1, 2->T3, 3->T4, 4->T2. One amber warning chip on the 4->T2 line with the
   text "PETG on a PLA toolhead". Caption: "Each colour goes to the right toolhead before you
   print."

8. INSTALL STEPS, four cards 800x500 each, live text, same template: big step number in the
   primary colour, title, one line, and an empty rounded screenshot frame (bottom 60%):
   1 "Install" / "File > Plugins > Install local plugin, then Activate."
   2 "Connect your U1" / "Select the U1 printer and enter its IP address."
   3 "Turn on print setup" / "Automagic adds it to your U1 process presets."
   4 "Print" / "Press Print. u1control handles the rest."

9. SCREENSHOT FRAMES for the plugin store, 1600x900 each, five versions with live-text headline
   + sub-line on the left 40% and an empty rounded 16:10 frame (thin border, soft drop shadow
   allowed ONLY as a 1-level flat offset, no blur) on the right 60%:
   a "Print setup" / "Map every colour to the right toolhead before you print."
   b "Live control" / "Camera, temperatures and controls inside OrcaSlicer."
   c "Toolheads & RFID" / "Tags pick the right filament profile for you."
   d "Spoolman built in" / "One spool per toolhead, usage booked when the print ends."
   e "Files & firmware" / "Browse prints and time-lapses, configure Extended Firmware."
   Each file under 2 MB.

10. ORCA CLOUD MAIN IMAGE, 1600x900 PNG under 2 MB: lockup centred, line "for Snapmaker U1 ·
    OrcaSlicer 2.5+", four toolhead colours as a geometric motif, generous margins (works when
    cropped to a 16:9 card and to a square thumbnail — show both crops).

11. RELEASE BANNER TEMPLATE, 1280x320, live text placeholders exactly "u1control" and "vX.Y.Z"
    (I will replace the version text), symbol left, toolhead motif right.

12. SOCIAL POSTS: (a) 1080x1080 and (b) 1200x675, lockup + line "Snapmaker U1 control for
    OrcaSlicer" + line "Free & open source"; (c) 1080x1350 vertical with the feature strip icons
    from item 2 in a 2x4 grid and the line "Everything your U1 needs inside OrcaSlicer".

13. UI SPOT ILLUSTRATIONS for the plugin (SVG only, 160x120, currentColor + toolhead colours,
    no text): "not connected" (printer box with a broken link), "no files", "camera off",
    "stock firmware" (chip with a small lock), "Spooler suggestion" (two linked cards),
    "printer busy" (toolhead with a clock). Must look right on #14181F and #FFFFFF.

After all items, give me a single table: filename, size, background, text strings, where used.
```
