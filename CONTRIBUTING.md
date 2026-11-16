# Contributing

Thanks for helping. Bug reports, printer logs and pull requests are all welcome.

## Reporting a problem

Open an issue with:

- the u1control version (Settings page of the U1 Control tab) and the OrcaSlicer version
- the printer firmware: stock (version from the touchscreen) or Extended Firmware (version)
- what you did, what you expected and what happened
- the plugin log: `<OrcaSlicer data folder>/log/python_*.log`
- for print setup problems, the exported G-code if you can share it

Leave out your printer's API key and anything else private.

## Set up

You need Python 3.12 or newer. The plugin uses only the standard library, so there is nothing to
install.

```sh
git clone https://github.com/bloodf/u1control
git clone https://github.com/bloodf/spooler     # next to it, for the joint tests (release v0.21.0 or newer)
cd u1control
python3 scripts/build.py                        # writes dist/u1control_any.whl
python3 -m unittest discover -s tests
```

The joint tests look for Spooler in `SPOOLER_SRC` or in `../spooler`, and fail if they find neither. They need a
Spooler with the presence/stock-list API (release v0.21.0 or newer); CI checks out `v0.21.0` unless the run input
`spooler_ref` or the repository variable `SPOOLER_REF` says otherwise. Page tests need Node 24 and Chrome or
Chromium (`CHROME=...`); CI runs them with `WORKERS=1` (one scenario at a time). Releases: [docs/release.md](docs/release.md).

To try a build in OrcaSlicer: **File > Plugins > Install local plugin**, pick
`dist/u1control_any.whl`, then **Activate**. Python errors and `print()` output go to
`<OrcaSlicer data folder>/log/python_*.log`.

## Layout

```
src/u1control/      plugin sources (see docs/architecture.md)
src/u1control/ui/   the tab and pop-up pages, icons, toolhead badges, illustrations
scripts/build.py    builds the single-file plugin
tests/              unit tests, a fake `orca` module and a fake U1 + Spoolman server
assets/             README, store and social images, diagrams, fonts with their licences
docs/               reference documentation
```

## Rules for code

- **Standard library only.** No dependencies.
- **Only `plugin.py` imports `orca`.** Keep everything else testable without OrcaSlicer.
- **No printer traffic on OrcaSlicer's threads.** Use the service worker or `run_off_thread`. Preset
  changes (`begin_update` / `commit`) run on a plugin thread, never the UI thread. Don't call
  `orca.host.ui` from the slicing thread except through the existing print setup window.
- **Both firmwares.** Every feature must work on stock firmware, or detect that it can't and say so.
  Extended-only features check `firmware.kind == "extended"`.
- **Commands come from the firmware source.** Check a command or endpoint in
  [u1-klipper](https://github.com/Snapmaker/u1-klipper) /
  [u1-moonraker](https://github.com/Snapmaker/u1-moonraker) before using it, and list it in
  `docs/firmware.md`.
- **G-code fixes are optional and idempotent.** Each one has a setting, leaves a `; u1control:`
  marker, and gives the same result when run twice.
- **Never overwrite an RFID spool by yourself.** `FORCE=1` only after the user confirms.
- **Anything that moves the printer, heats it or deletes files asks first** in the UI.
- **Settings** go in `settings.AUTOMATIONS` with an Automagic value. Then regenerate
  `docs/settings.md` and update the table in `docs/definitions.md` if you add a term.
- **Spooler.** Changes that touch toolhead linking, filament profiles or usage must keep
  `docs/spooler-contract.md` and `tests/test_spooler_joint.py` true.
- Keep functions small and files focused. Comment only what isn't obvious from the code.

## Tests

Every change needs a test that fails without it. The page is a Vue 3 + PrimeVue project in `ui/`: change it there,
then `cd ui && npm ci && npm run build` (writes `src/u1control/ui/app.html` and `ui/build.json`; commit both).
`tests/test_ui_page.py` runs the built page in headless Chrome under a CSP with a scripted bridge
(`ui/tests/page/run.mjs`): it needs Node.js 22.6+ (`node` on PATH or `NODE`) and Chrome or Chromium (or `CHROME`). `tests/fakes.py` has `FakePrinter` (Moonraker and
Spoolman on a local port) and `install_orca` (a fake `orca` module). Run the whole suite before you
open a pull request.

## Commits and pull requests

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(print-setup): ...`, `fix(spoolman): ...`, `docs: ...`, `test: ...`.
- One topic per pull request. Describe what changed, how you tested it, and whether you tried it on a
  real U1 (stock or Extended Firmware).
- Add a line under the next version in `CHANGELOG.md`.

## Releases

Maintainers only:

1. Bump `version` in `pyproject.toml` and add a `## [x.y.z] - date` section to `CHANGELOG.md`.
2. Tag `vx.y.z` and push the tag, then create a GitHub release for it with `dist/u1control_any.whl`.
3. Publishing the release runs `publish-orcacloud.yml`, which uploads the plugin to Orca Cloud.

## Assets

Images live in `assets/` and the UI icons in `src/u1control/ui/`. Keep the SVG and PNG of an image
together and update both. Fonts stay with their licence files.
The README, Orca Cloud and social images are made by `python3 scripts/render_images.py`: do not edit the PNGs.
The script needs Pillow (`pip install pillow`; nothing else here uses it), Node 24+ and Google Chrome. Pass a name
such as `hero` or `feature-03` to redo one image.

- `assets/marketing/source/` holds the native marketing artwork, each with an empty screenshot square. Never
  change these files.
- The script scales each one to its listing size, renders the matching screen of the built page with fake data
  and pastes it inside the square. It also takes the README screenshots.
- `assets/marketing/asset-manifest.json` records every export: source, operation, size, bytes, hash and date.
  The script rewrites it; commit it with the images.

Build the Vue page with `npm --prefix ui run build` first. These are mock previews, not captures from OrcaSlicer.
Set `RENDER_OUT=/tmp/u1control-artwork` to inspect the output without replacing existing artwork.
The renderer blocks network access, validates the page before capturing and saves HTML/JSON evidence if it fails.
It refuses a PNG over Orca Cloud's 2 MB limit. Named `integration`, it inlines Spooler's logo into the
integration SVGs (needs the Spooler repo next to this one).

## License

By contributing you agree that your work is released under the [GPL-3.0-only](LICENSE) license.
