"""Extended Firmware remote screen: frames on the Dashboard and taps on the touchscreen."""

import os
import sys
import time
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")]

import fakes  # noqa: E402
from test_review_fixes import call, make_service, wait_for  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter(version="2.0.0.205-paxx12", extended=True)
        self.addCleanup(self.fake.close)
        self.svc, self.pub = make_service(self, self.fake)
        call(self, self.svc, self.pub, "connect")

    def frames(self, kind):
        return [m for m in self.pub if m.get("type") == kind]

    def test_streams_screen_only_when_changed(self):
        self.fake.screen = PNG
        self.svc.touch(screen=True)
        self.assertTrue(wait_for(lambda: self.frames("screen")))
        self.assertTrue(self.frames("screen")[0]["image"].startswith("data:image/png;base64,"))
        time.sleep(1.2)                                 # two more polls of the same picture
        self.assertEqual(len(self.frames("screen")), 1)

    def test_screen_disabled_reports_error(self):
        self.svc.touch(screen=True)                     # fake serves no snapshot: 404
        self.assertTrue(wait_for(lambda: self.frames("screen_error")))
        self.assertFalse(self.frames("screen"))

    def test_tap_and_bounds(self):
        self.assertTrue(call(self, self.svc, self.pub, "screen_touch", x=512, y=300)["result"])
        self.assertEqual(self.fake.taps, [{"a": "tap", "x": "512", "y": "300"}])
        self.assertIn("error", call(self, self.svc, self.pub, "screen_touch", x=-1, y=5))

    def swipe(self, points):
        return call(self, self.svc, self.pub, "screen_swipe", points=points)

    def test_swipe_sends_down_moves_up_in_order(self):
        self.assertTrue(self.swipe([[10, 20], [11, 30], [12, 40]])["result"])
        self.assertEqual(self.fake.taps, [{"a": "down", "x": "10", "y": "20"}, {"a": "move", "x": "11", "y": "30"},
                                          {"a": "move", "x": "12", "y": "40"}, {"a": "up"}])

    def test_swipe_refuses_bad_points_before_sending(self):
        for bad in ([[1, 1], [4096, 5]], [[1, 1], [-1, 5]], [[1, 1]], [[1, 1], [2]], [[1, 1], ["a", 2]], "xy", None):
            self.assertIn("error", self.swipe(bad), bad)
        self.assertEqual(self.fake.taps, [])

    def test_swipe_thins_long_paths_keeping_ends(self):
        self.assertTrue(self.swipe([[i, 2 * i] for i in range(200)])["result"])
        taps = self.fake.taps
        self.assertEqual(len(taps), 24 + 1)             # 24 points: down + 23 moves, then up
        self.assertEqual(taps[0], {"a": "down", "x": "0", "y": "0"})
        self.assertEqual(taps[-2], {"a": "move", "x": "199", "y": "398"})
        self.assertEqual(taps[-1], {"a": "up"})

    def test_swipe_still_releases_when_a_move_fails(self):
        self.fake.fail_touch = "move"
        self.assertIn("error", self.swipe([[1, 1], [2, 2], [3, 3]]))
        self.assertEqual([t["a"] for t in self.fake.taps], ["down", "move", "up"])

    def test_swipe_releases_when_the_press_itself_fails(self):
        self.fake.fail_touch = "down"   # the firmware may have acted on it before answering with an error
        self.assertIn("error", self.swipe([[1, 1], [2, 2]]))
        self.assertEqual([t["a"] for t in self.fake.taps], ["down", "up"])


if __name__ == "__main__":
    unittest.main()
