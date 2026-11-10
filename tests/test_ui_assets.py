"""Built wheel ships its icons, sanitized, with no unresolved placeholders."""

import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402

UI = ROOT / "src" / "u1control" / "ui"
MAX_BUILT_BYTES = 400_000


class UiAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = build.build(out_dir=Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(cls.artifact) as z:
            cls.text = z.read("u1control/_assets.py").decode("utf-8")

    def page_icons(self, name):
        html = build.page_html(name)
        match = re.search(r"const ICONS = (\{.*?\});\n", html)
        self.assertIsNotNone(match, name)
        return html, json.loads(match.group(1))

    def test_every_referenced_icon_is_inlined(self):
        for page in ("app.html", "setup.html"):
            source = (UI / page).read_text("utf-8")
            html, icons = self.page_icons(page)
            used = set(re.findall(r"\b(?:icon|spot)/[a-z0-9-]+", source))
            self.assertTrue(used or page == "setup.html")
            self.assertEqual(used - set(icons), set(), page)
            self.assertTrue({"toolhead/t%d" % n for n in range(1, 5)} <= set(icons), page)
            self.assertNotIn("__ICONS__", html)
            self.assertIn(repr(html), self.text)   # the wheel carries exactly this page

    def test_app_uses_expected_icons(self):
        names = set(re.findall(r"\bicon/([a-z0-9-]+)", (UI / "app.html").read_text("utf-8")))
        for n in ("dashboard", "toolheads-rfid", "files", "firmware", "terminal", "settings", "pause", "resume",
                  "cancel", "emergency-stop", "chamber-light", "load-filament", "unload-filament", "rfid-tag",
                  "calibration", "delete", "download", "print-setup"):
            self.assertIn(n, names)
        spots = set(re.findall(r"\bspot/([a-z0-9-]+)", (UI / "app.html").read_text("utf-8")))
        self.assertEqual(spots, {"camera-off", "no-files", "not-connected", "printer-busy", "stock-firmware", "spooler-suggestion"})

    def test_no_unresolved_placeholders(self):
        for const in ("APP_HTML", "SETUP_HTML"):
            self.assertIsNone(re.search(r"%s = '[^\n]*__ICONS__" % const, self.text), const)
            self.assertNotIn("__ICONS__", build.page_html(const.split("_")[0].lower() + ".html"))

    def test_inlined_svgs_are_clean(self):
        icons = build.all_icons()
        self.assertGreaterEqual(len(icons), 37 + 4 + 6)
        for key, svg in icons.items():
            self.assertTrue(svg.startswith("<svg"), key)
            self.assertNotRegex(svg, r"(?i)<script|\bon\w+\s*=|<\?xml|<!--", key)

    def test_build_rejects_scripted_svg(self):
        with self.assertRaises(SystemExit):
            build.clean_svg('<svg onload="x()"></svg>', "bad")
        with self.assertRaises(SystemExit):
            build.clean_svg("<svg><script>1</script></svg>", "bad")

    def test_tab_icon_is_monochrome_fefefe(self):
        svg = (UI / "icon.svg").read_text("utf-8")
        colours = {c.upper() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", svg)}
        self.assertEqual(colours, {"#FEFEFE"})
        self.assertEqual(len(re.findall(r'fill="#FEFEFE"', svg)), 5)
        self.assertIn('viewBox="0 0 256 256"', svg)
        self.assertNotIn("currentColor", svg)

    def test_built_size_reasonable(self):
        size = self.artifact.stat().st_size
        print("built size: %d bytes" % size)
        self.assertLess(size, MAX_BUILT_BYTES)


if __name__ == "__main__":
    unittest.main()
