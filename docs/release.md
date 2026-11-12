# Releasing

A release is a GitHub release for the tag `vX.Y.Z`. Publishing the release runs
`.github/workflows/publish-orcacloud.yml`, which repeats the CI checks on the tagged commit, builds the wheel,
attaches `u1control_any.whl` and `SHA256SUMS` to the GitHub release, and publishes the same wheel to Orca Cloud.

Why a release and not a tag push or `workflow_dispatch`: Orca Cloud only accepts the GitHub OIDC token of a run
triggered by a published release (official guide, <https://cloud.orcaslicer.com/wiki/>, "Publishing a plugin from
GitHub": `on: release: types: [published]`, `id-token: write`, audience `orcacloud`, HTTP 201 is success).

## What the workflow enforces

- The tag is `vX.Y.Z` (numeric) and equals `version` in `pyproject.toml`; `scripts/build.py --release-tag` checks it again.
- Node 24 and Chrome are provisioned (same setup as `ci.yml`); `ui/` is rebuilt with `npm ci --ignore-scripts &&
  npm run build` and the run fails if `src/u1control/ui/app.html` or `ui/build.json` differ from the commit.
- The whole suite runs with `WORKERS=1` against Spooler **`v0.21.0`** (checked out into `spooler/`, passed as
  `SPOOLER_SRC`). That Spooler release is the first with the presence/stock-list API the joint tests need, so it must
  exist as a tag in `bloodf/spooler` before a release here; raising the Spooler version means changing the `ref`
  in `publish-orcacloud.yml`, the default in `ci.yml`, `SPOOLER_RELEASE` in `tests/test_release.py` and the docs.
- `dist/SHA256SUMS` matches the wheel, and the wheel's metadata and `VERSION` equal the version.
- `CHANGELOG.md` has a non-empty `## [X.Y.Z] - date` section. It becomes the GitHub release notes (when empty) and
  the Orca Cloud changelog. Orca Cloud keeps at most 4000 characters, so `scripts/release_notes.py` cuts the copy it
  sends at a line boundary and adds a link to the release page.
- The OIDC token is masked in the log. No secret is stored in the repository.

## Prerequisites (outside the repository)

1. Spooler `v0.21.0` is published (tag in `bloodf/spooler`).
2. On Orca Cloud the u1control plugin is connected to this repository under Edit plugin > GitHub publishing (one
   repository publishes to exactly one plugin). A 401 from the publish step means this is missing.
3. The version is higher than the one the hub lists (0.3.1 when last checked).
4. GitHub Actions is enabled and the release is not a draft.

## Steps

1. On `main`, the commit to release has `pyproject.toml`, `ui/package.json` and `ui/package-lock.json` at the new
   version and a dated changelog section. Run the local gates below and note the commit hash.
2. Tag exactly that commit and push the tag: `git tag vX.Y.Z <commit> && git push origin vX.Y.Z`.
3. Publish the release, which starts the workflow:
   `python3 scripts/release_notes.py X.Y.Z --limit 0 | gh release create vX.Y.Z --verify-tag --title "U1 Control X.Y.Z" --notes-file -`
4. Wait for the "Publish to Orca Cloud" run to finish (a queued run is not a publication). Re-running a run that
   already published is safe; fix the cause and re-run if a step failed.

## Verify afterwards

- The run is green and its last step printed HTTP 201 and "Published vX.Y.Z to Orca Cloud".
- The release lists `u1control_any.whl` and `SHA256SUMS`; the attached `SHA256SUMS` is the authority for what was
  published. Rebuilding the wheel on one machine is byte-identical (the build uses fixed zip timestamps and the
  committed page). The same commit built on another OS should match, since the wheel reads only committed files; a
  difference is something to explain.
- The hub page lists the new version and changelog.

## Local gates

```bash
(cd ui && npm ci --ignore-scripts && npm run build)    # must leave src/u1control/ui/app.html and ui/build.json unchanged
git diff --exit-code -- src/u1control/ui/app.html ui/build.json
export WORKERS=1 SPOOLER_SRC=/path/to/spooler          # a checkout at the v0.21.0 tag (or a working tree that is a superset)
python3 scripts/build.py --release-tag vX.Y.Z          # dist/u1control_any.whl, dist/SHA256SUMS
python3 -m unittest discover -s tests                  # needs node on PATH and Chrome (or CHROME=...)
```

## What the tests cover, and what they do not

Every automated test is mock-only: a fake `orca` module, a fake U1 (Moonraker) and Spoolman server on local ports,
Spooler's real source loaded in the same process, and the built Vue page in headless Chrome under a CSP with a
scripted bridge. Nothing talks to a real OrcaSlicer, printer, camera, cloud account or Spoolman, and no test sends a
printer command outside the fakes. Behaviour inside a real OrcaSlicer 2.5 and on real U1 firmware is unverified
until someone runs it by hand.

OrcaSlicer's plugin API has no call to hide or merge tabs, so U1 Control and Spooler stay two tabs; the only
workaround is turning off Spooler's page in the Plugins dialog (see [spooler-contract.md](spooler-contract.md)).
The Spooler stock shown in U1 Control and the Spooler card therefore live in separate tabs of one window.
