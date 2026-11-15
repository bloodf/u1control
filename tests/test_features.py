"""Features of 0.7.0: rename in the file manager, and the file list's filament column."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import wait_for  # noqa: E402

def make(test, fake, **target):
    pub = []
    svc = Service(pub.append, log=lambda m: None)
    test.addCleanup(svc.close)
    svc.set_target(Target(fake.host, **target))
    return svc, pub


def call(test, svc, pub, cmd, **args):
    rid = len(pub) + 9000
    svc.submit(rid, cmd, args)
    test.assertTrue(wait_for(lambda: any(m.get("id") == rid for m in pub)))
    return next(m for m in pub if m.get("id") == rid)


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.fake.listing = {"dirs": [{"dirname": "sub"}], "files": [{"filename": "a.gcode"}, {"filename": "b.gcode"},
                                                                     {"filename": "clip.mp4"}]}
        self.svc, self.pub = make(self, self.fake)

    def test_renames_a_file_in_its_folder(self):
        reply = call(self, self.svc, self.pub, "rename", path="gcodes/a.gcode", name="  boat v2.gcode ")
        self.assertEqual(reply["result"], {"path": "gcodes/boat v2.gcode"})
        self.assertEqual(self.fake.moved, [("gcodes/a.gcode", "gcodes/boat v2.gcode")])

    def test_renames_a_folder(self):
        self.assertEqual(self.svc.cmd_rename("gcodes/sub", "parts"), {"path": "gcodes/parts"})
        self.assertEqual(self.fake.moved, [("gcodes/sub", "gcodes/parts")])

    def test_same_name_does_nothing(self):
        self.assertEqual(self.svc.cmd_rename("gcodes/a.gcode", "a.gcode"), {"path": "gcodes/a.gcode"})
        self.assertEqual(self.fake.moved, [])

    def test_refusals_send_nothing(self):
        cases = (("gcodes/a.gcode", "b.gcode"),        # taken: Moonraker would replace it
                 ("gcodes/a.gcode", "sub"),            # taken by a folder
                 ("gcodes/a.gcode", "a.txt"),          # a print file keeps a G-code extension
                 ("gcodes/a.gcode", ""), ("gcodes/a.gcode", "../a.gcode"), ("gcodes/a.gcode", "x/a.gcode"),
                 ("gcodes/a.gcode", ".hidden.gcode"), ("gcodes/a.gcode", "a:b.gcode"), ("gcodes/a.gcode", "a\x01.gcode"),
                 ("gcodes/a.gcode", "x" * 250 + ".gcode"),
                 ("gcodes", "other"), ("camera", "x"),  # roots
                 ("gcodes/gone.gcode", "c.gcode"),     # no longer there
                 ("gcodes/../a.gcode", "c.gcode"))
        for path, name in cases:
            with self.subTest(path=path, name=name):
                self.assertIn("error", call(self, self.svc, self.pub, "rename", path=path, name=name))
        self.assertEqual(self.fake.moved, [])

    def test_other_files_keep_any_extension(self):
        self.assertEqual(self.svc.cmd_rename("gcodes/clip.mp4", "clip-old.mp4"), {"path": "gcodes/clip-old.mp4"})
        self.assertEqual(self.svc.cmd_rename("gcodes/b.gcode", "b.GCO"), {"path": "gcodes/b.GCO"})


class FileWeightTests(unittest.TestCase):
    def test_listing_carries_the_filament_weight(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.listing = {"dirs": [], "files": [{"filename": "a.gcode", "filament_weight_total": 12.3}]}
        svc, _ = make(self, fake)
        self.assertEqual(svc.cmd_files("gcodes")["files"][0]["weight"], 12.3)


if __name__ == "__main__":
    unittest.main()
