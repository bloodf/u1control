"""File manager: create folders and move files or folders between folders of one root."""

import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")]

import fakes  # noqa: E402
from test_review_fixes import call, make_service  # noqa: E402


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.svc, self.pub = make_service(self, self.fake)

    def run_cmd(self, cmd, **args):
        return call(self, self.svc, self.pub, cmd, **args)

    def test_mkdir(self):
        self.assertIn("result", self.run_cmd("mkdir", path="gcodes/Benchy prints"))
        self.assertEqual(self.fake.made, ["gcodes/Benchy prints"])
        for bad in ("gcodes", "gcodes/.hidden", "gcodes/a;b", "gcodes/../x", "config/x"):
            self.assertIn("error", self.run_cmd("mkdir", path=bad), bad)
        self.assertEqual(self.fake.made, ["gcodes/Benchy prints"])

    def test_folders_skips_hidden(self):
        self.assertEqual(self.run_cmd("folders", root="gcodes")["result"], ["gcodes", "gcodes/sub"])

    def test_move_keeps_name(self):
        self.assertEqual(self.run_cmd("move", path="gcodes/a.gcode", folder="gcodes/sub")["result"], {"path": "gcodes/sub/a.gcode"})
        self.assertEqual(self.fake.moved, [("gcodes/a.gcode", "gcodes/sub/a.gcode")])

    def test_move_refusals(self):
        for path, folder in (("gcodes/sub", "gcodes/sub/inner"), ("gcodes/a.gcode", "camera"),
                             ("gcodes", "gcodes/sub"), ("gcodes/../a", "gcodes")):
            self.assertIn("error", self.run_cmd("move", path=path, folder=folder), (path, folder))
        self.assertEqual(self.fake.moved, [])


if __name__ == "__main__":
    unittest.main()
