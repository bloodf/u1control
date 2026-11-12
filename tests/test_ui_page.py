"""Behaviour of the compiled U1 Control page (Vue 3 + PrimeVue, ui/ -> src/u1control/ui/app.html): its real
production build runs in an owned headless Chrome under a host-like CSP, with a scripted OrcaSlicer bridge
(ui/tests/page/run.mjs). Replaces the former fake-DOM harness; every scenario of it was ported first.
Needs Node.js (`node` on PATH or NODE=...) and Chrome/Chromium (found automatically or CHROME=...)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import build  # noqa: E402
import extended  # noqa: E402
import fakes  # noqa: E402
import u1  # noqa: E402

NODE = os.environ.get("NODE") or shutil.which("node")
RUNNER = os.path.join(ROOT, "ui", "tests", "page", "run.mjs")


UNIT = os.path.join(ROOT, "ui", "tests", "unit")


class PageLogic(unittest.TestCase):
    def test_unit_tests_of_the_page_rules(self):
        """node --test of ui/tests/unit (temperature parsing, setup warnings, tracker timeout/no-retry, locale)."""
        if not NODE:
            self.fail("Node.js is needed: put node on PATH or set NODE")
        files = sorted(os.path.join(UNIT, f) for f in os.listdir(UNIT) if f.endswith(".test.ts"))
        proc = subprocess.run([NODE, "--test", *files], capture_output=True, text=True, timeout=120, cwd=os.path.join(ROOT, "ui"))
        self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])

    def test_setup_warnings_match_the_plugin(self):
        """The page builds the same warning ids the plugin requires as acknowledgement (u1.warning_ids)."""
        if not NODE:
            self.fail("Node.js is needed: put node on PATH or set NODE")
        types = ["PLA", "PLA+", "PETG", "PETG-CF", "PA6-CF", "Silk PLA", "TPU 95A", "", "ABS"]
        cases = []
        for n, ftype in enumerate(types):
            heads = [{"index": i, "loaded": i != 2, "type": types[(n + i) % len(types)] if i != 2 else ""} for i in range(4)]
            filaments = [{"index": 0, "type": ftype}, {"index": 1, "type": types[(n + 3) % len(types)]}]
            for mapping in ({0: 0, 1: 1}, {0: 2, 1: 3}, {0: 1, 1: 2}):
                cases.append({"f": filaments, "h": heads, "m": {str(k): v for k, v in mapping.items()},
                              "want": u1.warning_ids(filaments, heads, mapping)})
        logic = Path(ROOT, "ui", "src", "core", "logic.ts").as_uri()
        script = ("import { setupWarnings } from %s;\nconst cases = %s;\n"
                  "console.log(JSON.stringify(cases.map(c => setupWarnings(c.f, c.h, c.m).map(w => w.id))));") % (json.dumps(logic), json.dumps(cases))
        with tempfile.TemporaryDirectory() as tmp:
            probe = os.path.join(tmp, "probe.mjs")
            with open(probe, "w", encoding="utf-8") as f:
                f.write(script)
            proc = subprocess.run([NODE, "--no-warnings", probe], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [c["want"] for c in cases])


class BuiltPage(unittest.TestCase):
    def test_page_scenarios_in_headless_chrome(self):
        if not NODE:
            self.fail("Node.js is needed for the page tests: put node on PATH or set NODE")
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "app.html")
            with open(page, "w", encoding="utf-8") as f:
                f.write(build.page_html("app.html"))   # icons injected exactly as in the wheel
            results = os.path.join(tmp, "results.json")
            env = {**os.environ, "PAGE": page, "RESULTS": results,
                   "EXT_GROUPS": json.dumps(extended.normalize_settings(fakes.ext_settings()))}
            proc = subprocess.run([NODE, RUNNER], capture_output=True, text=True, timeout=600, env=env, cwd=os.path.join(ROOT, "ui"))
            self.assertEqual(proc.returncode, 0, proc.stdout[-6000:] + proc.stderr[-3000:])
            self.assertIn("PASS", proc.stdout)
            with open(results, encoding="utf-8") as f:
                done = json.load(f)
            self.assertGreaterEqual(len(done), 31)
            self.assertTrue(all(r["ok"] for r in done))


if __name__ == "__main__":
    unittest.main()
