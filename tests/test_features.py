"""Features of 0.7.0: rename in the file manager, saving the camera picture, and the file list's filament column."""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import service as service_mod  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import wait_for  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"frame" * 10


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


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.fake.files["camera/monitor.jpg"] = JPEG
        self.home = tempfile.mkdtemp()
        patch = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        patch.start()
        self.addCleanup(patch.stop)
        self.svc, self.pub = make(self, self.fake, name="Bench U1")
        self.svc.firmware = {"kind": "stock", "version": ""}
        self.svc.client.ws_call = lambda *a, **k: None   # camera.start_monitor (websocket only)

    def test_saves_the_last_picture(self):
        self.svc._push_frame()
        reply = call(self, self.svc, self.pub, "snapshot")
        path = reply["result"]
        self.assertEqual(os.path.dirname(path), os.path.join(self.home, "Downloads", "u1control"))
        self.assertTrue(os.path.basename(path).startswith("Bench U1 ") and path.endswith(".jpg"), path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), JPEG)
        again = call(self, self.svc, self.pub, "snapshot")["result"]
        self.assertNotEqual(again, path)   # never overwrites
        self.assertTrue(os.path.exists(path))

    def test_without_a_picture_nothing_is_saved(self):
        self.assertIn("camera", call(self, self.svc, self.pub, "snapshot").get("error", ""))
        self.assertFalse(os.path.exists(os.path.join(self.home, "Downloads", "u1control")))

    def test_an_old_picture_is_not_saved(self):
        self.svc._push_frame()
        with mock.patch.object(service_mod, "SNAPSHOT_MAX_AGE", 0.0):
            time.sleep(0.01)
            self.assertIn("error", call(self, self.svc, self.pub, "snapshot"))

    def test_a_picture_of_the_previous_printer_is_not_saved(self):
        self.svc._push_frame()
        other = fakes.FakePrinter()
        self.addCleanup(other.close)
        self.svc.set_target(Target(other.host))
        self.assertIn("error", call(self, self.svc, self.pub, "snapshot"))

    def test_runs_beside_a_long_command(self):
        self.assertIn("snapshot", service_mod.DEDICATED)


class FileWeightTests(unittest.TestCase):
    def test_listing_carries_the_filament_weight(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.listing = {"dirs": [], "files": [{"filename": "a.gcode", "filament_weight_total": 12.3}]}
        svc, _ = make(self, fake)
        self.assertEqual(svc.cmd_files("gcodes")["files"][0]["weight"], 12.3)


if __name__ == "__main__":
    unittest.main()
