"""Release metadata: version, the changelog section Orca Cloud receives, and the CI and publish workflow contract."""

import json
import re
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_notes  # noqa: E402

PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISH = (WORKFLOWS / "publish-orcacloud.yml").read_text("utf-8")
CI = (WORKFLOWS / "ci.yml").read_text("utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text("utf-8")
SPOOLER_RELEASE = "v0.21.0"


class ReleaseMetadata(unittest.TestCase):
    def test_version_is_numeric_and_has_a_dated_section(self):
        version = PROJECT["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertRegex(CHANGELOG, r"(?m)^## \[%s\] - \d{4}-\d{2}-\d{2}$" % re.escape(version))
        self.assertTrue(release_notes.section(CHANGELOG, version))

    def test_ui_package_versions_follow_the_plugin(self):
        pkg = json.loads((ROOT / "ui" / "package.json").read_text("utf-8"))
        lock = json.loads((ROOT / "ui" / "package-lock.json").read_text("utf-8"))
        self.assertEqual(pkg["version"], PROJECT["version"])
        self.assertEqual((lock["version"], lock["packages"][""]["version"]), (PROJECT["version"],) * 2)

    def test_orca_cloud_copy_fits_the_changelog_field(self):
        full = release_notes.section(CHANGELOG, PROJECT["version"])
        footer = "\n\n... Full notes: https://github.com/bloodf/u1control/releases/tag/v%s" % PROJECT["version"]
        short = release_notes.fit(full, 3900, footer)
        self.assertLessEqual(len(short.encode("utf-8")), 3900)
        self.assertLessEqual(len(short), 4000)
        self.assertEqual(release_notes.fit(full, 0, footer), full)

    def test_section_rules(self):
        self.assertIsNone(release_notes.section(CHANGELOG, "99.0.0"))
        text = "## [2.0.0] - 2026-02-01\n- new\n\n## [1.0.0] - 2026-01-01\n- old\n"
        self.assertEqual(release_notes.section(text, "2.0.0"), "- new")


class Workflows(unittest.TestCase):
    def test_publish_runs_on_published_release_only(self):
        self.assertRegex(PUBLISH, r"(?m)^on:\n  release:\n    types: \[published\]\n")
        self.assertNotRegex(PUBLISH, r"(?m)^  (workflow_dispatch|push):")
        self.assertIn("audience=orcacloud", PUBLISH)
        self.assertIn("add-mask", PUBLISH)
        self.assertIn('"$TAG" != "v$version"', PUBLISH)
        self.assertIn("--release-tag", PUBLISH)

    def test_publish_runs_the_page_tests_like_ci(self):
        for step in ("actions/setup-node@", "browser-actions/setup-chrome@", "npm ci --ignore-scripts && npm run build",
                     "git diff --exit-code -- src/u1control/ui/app.html ui/build.json",
                     "python -m unittest discover -s tests", "SPOOLER_SRC:", "CHROME:"):
            self.assertIn(step, CI, step)
            self.assertIn(step, PUBLISH, step)
        for text in (CI, PUBLISH):
            self.assertRegex(text, r'WORKERS: "1"')

    def test_joint_tests_use_the_spooler_release(self):
        self.assertIn("|| '%s'" % SPOOLER_RELEASE, CI)
        self.assertEqual(re.findall(r"(?m)^\s+ref: (v[\d.]+)$", PUBLISH), [SPOOLER_RELEASE])
        self.assertNotIn("ref: main", PUBLISH)

    def test_actions_are_the_ones_ci_uses(self):
        used = lambda text: set(re.findall(r"uses: (\S+)", text))
        self.assertLessEqual(used(PUBLISH), used(CI))


if __name__ == "__main__":
    unittest.main()
