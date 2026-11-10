# Brand asset prompt

Paste the prompt below into ChatGPT. Ask for one deliverable per message, and always ask for
**SVG code** for vector assets (symbol, wordmark, icons, badges) so they stay sharp; use image
generation only to preview them or for the raster compositions, then rebuild those from the SVGs.

Where each asset goes:

| Asset | File |
|---|---|
| Symbol / app icon | `assets/u1control-icon.svg`, `assets/u1control-icon.png` (Orca Cloud main image) |
| Tab icon | `src/u1control/ui/icon.svg` |
| UI icons, toolhead badges | `src/u1control/ui/` (inlined into the pages) |
| README banners | `assets/u1control-banner.svg`, `assets/u1control-banner-light.svg` |
| GitHub social preview | Repository Settings > Social preview (`assets/u1control-social.png`) |
| Orca Cloud store images | `assets/orca-cloud/*.png` |

---

```text
You are a senior brand and product designer working in a strict, engineering-grade vector style.
Create a complete, original brand identity for "u1control".

THE PRODUCT
u1control is an open-source plugin for OrcaSlicer (a 3D-printing slicer) that controls the
Snapmaker U1, a 3D printer with FOUR independent toolheads (a tool changer: each print can use up
to four filaments/colours, each in its own toolhead T1, T2, T3, T4). Inside the slicer it adds:
a pre-print setup window that maps each filament colour to a toolhead, a printer control tab
(live camera, temperatures, pause/resume), per-toolhead filament with RFID tag reading, Spoolman
spool inventory sync, a printer file manager, and configuration for the community "Extended
Firmware". It has two modes: "Automagic" (everything automatic) and "Expert" (every setting
exposed). Core idea: "four toolheads, one control" - precise, local, no cloud.

It is the sibling of an existing plugin, "Spooler", and must feel like the same family:
Spooler palette = dark #14181F, light #F6F7FB, accents #FF997D (coral), #F4CF78 (amber),
#A99BFF (violet), #78CFD5 (teal). Reuse those four accents as the four TOOLHEAD colours
(T1 coral, T2 amber, T3 violet, T4 teal), plus one u1control primary of your choice that is
distinct from Spooler's (propose 3 options, then use the chosen one consistently; it must pass
WCAG AA as text on #14181F and on #FFFFFF, or define a dark/light variant pair).

AUDIENCE AND PERSONALITY
Prosumer makers and engineers who self-host their tools. Personality: precise, confident,
technical, calm, trustworthy - like a well-made instrument panel. Not playful-cartoon, not
gamer, not corporate-bland.

ART DIRECTION - MUST LOOK HAND-DESIGNED, NOT AI-GENERATED
- Strictly geometric flat vector built on a visible construction grid (8 px base grid,
  icons on a 24 px grid). Every shape made of circles, straight lines and consistent radii.
- One stroke weight per size class, round or square caps used consistently, optical alignment.
- No gradients (except an optional subtle one on the full-colour app tile), no glow, no bevel,
  no 3D renders, no photorealism, no lens flare, no "AI swirl", no noise textures, no fake
  depth, no isometric clutter, no stock-illustration people or robots.
- No invented text anywhere: images contain only the exact words I give you. If unsure, leave
  the space empty. No lorem ipsum, no pseudo-UI with gibberish labels, no fake screenshots.
- Generous whitespace, strict alignment, consistent margins. Think Swiss/industrial design,
  Dieter Rams, aerospace instrument labels.
- Typography: free Google Fonts only, name them. Suggest a precise grotesk or geometric sans for
  the wordmark/headlines (e.g. Inter Tight, Space Grotesk, Manrope) and a monospace for technical
  labels (e.g. JetBrains Mono, IBM Plex Mono). Wordmark in lowercase "u1control"; you may
  differentiate "u1" from "control" by weight or colour, never by changing letters.

SYMBOL CONCEPT DIRECTIONS (show 3 directions as small sketches on one sheet, then refine the one
I pick)
A. Four toolheads: four identical rounded rectangles or circles in a 2x2 or 1x4 arrangement, one
   highlighted/active, suggesting a tool changer and "control".
B. A control dial/knob whose tick marks are four coloured segments (T1-T4).
C. A nozzle tip seen from below with four coloured quadrants, forming a "U" or a target.
The symbol must work in full colour, in one colour, and stay recognisable at 16x16 and 20x20 px.

LEGAL CONSTRAINTS
- Fully original. Do not imitate or reference logos, colours, icons or type of OrcaSlicer,
  Snapmaker, Spoolman, Bambu Lab, Prusa, Klipper or Moonraker. Never draw the Snapmaker logo or
  the U1 printer's industrial design. "U1" appears only inside the word "u1control" or in the
  descriptive line "for Snapmaker U1" where explicitly listed below.

DELIVERABLES (one per reply; exact pixel sizes; transparent background unless stated; for every
vector deliverable provide clean, hand-editable SVG code: no embedded raster, no external fonts
- convert wordmark text to paths, use a viewBox, round coordinates to 0.5 px, group and name
layers, no unnecessary transforms)
1. Brand sheet, 1600x1000, background #14181F: symbol, wordmark, horizontal lockup, stacked
   lockup, clear-space and minimum-size rules, palette swatches with hex + RGB, the four toolhead
   colours labelled exactly "T1", "T2", "T3", "T4", typography samples, and a do/don't row.
2. Symbol / app icon, full colour, 1024x1024 on a rounded-square tile (corner radius ~22%);
   also 512x512 PNG export for the plugin store. SVG viewBox 0 0 256 256.
3. Symbol, single colour, white on transparent and #14181F on transparent, SVG.
4. Slicer tab icon: monochrome line icon, colour exactly #FEFEFE, transparent, on a 24x24 grid,
   1.5 px strokes, round caps/joins, readable at 20 px. SVG with width="24" height="24"
   viewBox="0 0 24 24". Plus 16/20/24 px PNG previews on dark and light backgrounds.
5. Wordmark "u1control" and horizontal lockup (symbol + wordmark), dark and light versions, SVG.
6. UI icon set, 24x24 grid, 1.5 px stroke, currentColor (so CSS can recolour), SVG each:
   dashboard, camera, live-stream, toolhead, filament spool, RFID tag, load filament (arrow into
   toolhead), unload filament, temperature, bed, fan / top-cover purifier, chamber light,
   pause, resume, cancel, emergency stop, files, folder, timelapse video, delete, download,
   firmware chip, console/terminal, settings, automagic (wand or spark made of straight
   geometry - no cartoon), expert (sliders), warning, error, success, link, calibration (target),
   power-loss resume. Deliver as one sprite sheet image for review plus individual SVG code.
7. Toolhead badges: four circular badges reading exactly "T1", "T2", "T3", "T4" in the toolhead
   colours, plus "empty" (outlined, dashed) and "active" (ring) states; 32x32 SVG each, text
   converted to paths, legible at 20 px.
8. README banner, 1600x400, two versions (dark #14181F and light #FFFFFF backgrounds): lockup on
   the left, the line "Snapmaker U1 control for OrcaSlicer" in the secondary font, and an
   abstract four-toolhead motif on the right. No other text.
9. GitHub social preview, 1280x640 (keep content inside a centred 1200x560 safe area): lockup,
   the line "Snapmaker U1 control for OrcaSlicer", and the line "Camera · Toolheads · Spoolman ·
   Files · Extended Firmware". No other text.
10. Plugin store main image, 1600x900 PNG under 2 MB: lockup centred, line "for Snapmaker U1 ·
    OrcaSlicer 2.5+", the four toolhead colours as a simple geometric motif.
11. Four store feature tiles, 1600x900 each, same layout system: a large UI icon from set 6,
    a headline and one sub-line, exactly:
    a. "Print setup" / "Map every colour to the right toolhead before you print."
    b. "Live control" / "Camera, temperatures and controls inside OrcaSlicer."
    c. "Toolheads & Spoolman" / "RFID-aware filament profiles and spool tracking."
    d. "Automagic or Expert" / "Everything automatic, or every setting in your hands."
    Leave the right 55% of each tile as an empty rounded frame (16:10) where I will place a real
    screenshot later - do not draw any UI inside it.
12. Favicon / micro marks: 16, 20, 24 px pixel-hinted versions of the symbol (dark and light),
    PNG + SVG.

QUALITY CHECK BEFORE EACH DELIVERY
State: the grid and stroke values used, the hex codes used, the fonts used, contrast ratios for
text, and confirm no text other than what I specified appears. If an image generator would add
artefacts or stray text, give me only the SVG instead.
```
