"""filmatch (the shared matcher from @orca-plugins/ui-foundation) keeps U1 Control's picks, and the committed copy is
the foundation's. Run: python3 -m unittest discover -s tests"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402,F401  (the stand-in `orca` module)
import agent  # noqa: E402
import filmatch  # noqa: E402
import u1  # noqa: E402

SHARED = os.path.join(ROOT, "ui", "node_modules", "@orca-plugins", "ui-foundation", "python", "filmatch.py")


def _read(path):
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")   # a git checkout on Windows may give CRLF


class FilmatchParityTest(unittest.TestCase):
    """fixtures/filmatch_parity.json holds the picks before the code moved to filmatch."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "tests", "fixtures", "filmatch_parity.json"), encoding="utf-8") as f:
            cls.golden = json.load(f)

    def test_pick_filament_preset_unchanged(self):
        g, pick = self.golden, filmatch.pick_filament_preset
        names, colours, overrides = g["names"], g["colours"], g["overrides"]
        self.assertGreater(len(g["cases"]), 2000)
        changed = [c for c in g["cases"] if pick(names, {"type": c[0], "vendor": c[1], "sub_type": c[2], "colour": c[3]},
                                                 None, None, c[4], None, colours if c[5] else None) != c[6]]
        self.assertEqual(changed, [])
        head = {"type": "PLA", "vendor": "Generic"}
        changed = [c for c in g["tag_cases"] if pick(names, head, {"type": c[0], "vendor": c[1], "sub_type": c[2],
                                                                   "uid": "AABB", "sku": "S1"}) != c[3]]
        self.assertEqual(changed, [])
        self.assertEqual([pick(names, head, tag, overrides) for tag, _ in g["override_cases"]],
                         [want for _, want in g["override_cases"]])

    def test_generic_ids_and_colours_unchanged(self):
        got = [[m, agent.material_family(m), agent.generic_filament_id(m), agent.tray_type(m, "Matte"), u1.material_family(m)]
               for m, *_ in self.golden["generic"]]
        self.assertEqual(got, self.golden["generic"])
        self.assertEqual([[a, b, u1.colour_distance(a, b)] for a, b, _ in self.golden["colour_distance"]],
                         self.golden["colour_distance"])

    def test_committed_copy_is_the_foundations(self):
        self.assertTrue(os.path.exists(SHARED), "run npm ci in ui/")
        self.assertEqual(_read(os.path.join(ROOT, "src", "u1control", "filmatch.py")), _read(SHARED),
                         "src/u1control/filmatch.py differs from ui-foundation's; run `npm run build` in ui/")


if __name__ == "__main__":
    unittest.main()
