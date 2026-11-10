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


if __name__ == "__main__":
    unittest.main()
