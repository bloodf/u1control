"""The print setup window after OrcaSlicer's Print: offered options by command list, the answer as sent, the
top-cover fans, Heads settings, the Plugin settings link, the job facts and the preview. Never contacts a printer:
FakePrinter is a local HTTP server."""

import base64
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import preview  # noqa: E402
from test_agent import PluginAgentTests as _B  # noqa: E402

# _B: test_agent's wheel fixture and helpers, borrowed (its tests are not run here)


def boot(window):
    return json.loads(re.search(r'id="u1-boot">(.*?)</script>', window.html, re.S).group(1))["data"]


class PreviewTests(unittest.TestCase):
    LINES = ["G28", "G1 X5 Y5 E1",            # start G-code: never drawn
             ";LAYER_CHANGE", "T0", "M83", "G1 X0 Y0", "G1 X10 Y0 E0.5", "G1 X10 Y10 E0.5",
             "T1", "G1 X0 Y10 E0.5", "G1 X0 Y0", "T0", ";LAYER_CHANGE", "G1 X20 Y20 E1"]

    @staticmethod
    def cells(view):
        """[(tool, height, tools)] per cell, row by row from the front, from the run-length map."""
        raw, out = base64.b64decode(view["runs"]), []
        for i in range(0, len(raw), 4):
            out += [tuple(raw[i + 1:i + 4])] * raw[i]
        return out

    def at(self, view, x, y):
        x0, y0, x1, y1 = view["bounds"]
        cell = max(x1 - x0, y1 - y0) / max(view["w"], view["h"])
        return self.cells(view)[int((y - y0) / cell) * view["w"] + int((x - x0) / cell)]

    def test_top_view_by_tool_and_bounds(self):
        v = preview.top_view(self.LINES)
        self.assertEqual(v["bounds"], [-1.0, -1.0, 21.0, 21.0])   # the extrusion with 1 mm around
        self.assertEqual(v["w"], preview.CELLS)
        self.assertEqual(len(self.cells(v)), v["w"] * v["h"])
        self.assertEqual(self.at(v, 5, 0)[0], 0)          # T0's first wall
        self.assertEqual(self.at(v, 5, 10)[0], 1)         # T1's
        self.assertEqual(self.at(v, 15, 15)[0], 0)        # the second layer's line, on top
        self.assertEqual(self.at(v, 15, 15)[1], 255)
        self.assertLess(self.at(v, 5, 0)[1], 255)          # the first layer is lower
        self.assertEqual(self.at(v, 7, 3), (255, 0, 0))   # nothing printed
        self.assertEqual(self.at(v, 1, 3)[0], 255)        # the travel move is not drawn
        self.assertIsNone(preview.top_view(["G28", "G1 X1 Y1"]))
        self.assertIsNone(preview.top_view([";LAYER_CHANGE", "G1 X1 Y1", "G1 X5 Y1"]))

    def test_hidden_filament_is_kept_under_the_top(self):
        # White text in the first layer (T1) under a blue top (T0): the top view's cell is blue, with T1 in its tools
        lines = ["M83", ";LAYER_CHANGE", "T1", "G1 X4 Y5", "G1 X6 Y5 E0.1"]
        for _ in range(3):
            lines += [";LAYER_CHANGE", "T0"] + sum((["G1 X0 Y%d" % y, "G1 X10 Y%d E0.5" % y] for y in range(11)), [])
        v = preview.top_view(lines)
        tool, height, tools = self.at(v, 5, 5)
        self.assertEqual((tool, height), (0, 255))
        self.assertEqual(tools, 0b11)
        self.assertEqual(self.at(v, 1, 1)[2], 0b01)

    def test_prime_tower_and_skirt_left_out(self):
        lines = ["M83", ";LAYER_CHANGE", ";TYPE:Skirt", "G1 X-30 Y0", "G1 X-30 Y30 E1", ";TYPE:Prime tower",
                 "G1 X100 Y100", "G1 X120 Y100 E1", ";TYPE:Outer wall", "G1 X0 Y0", "G1 X10 Y0 E1"]
        self.assertEqual(preview.top_view(lines)["bounds"], [-1.0, -1.0, 11.0, 1.0])

    def test_long_print_samples_its_layers(self):
        # 2000 layers of a 100 mm square: only MAX_LAYERS are parsed, the top ones always, and it stays quick
        lines = ["M83"]
        for layer in range(2000):
            lines += [";LAYER_CHANGE", "G1 X0 Y0"] + ["G1 X%d Y%d E0.1" % (x, layer % 100) for x in range(1, 101)]
        lines += [";LAYER_CHANGE", "T1", "G1 X40 Y40", "G1 X60 Y40 E1"]
        started = time.time()
        v = preview.top_view(lines)
        self.assertLess(time.time() - started, 5)
        self.assertEqual(self.at(v, 50, 40)[:2], (1, 255))   # the last layer
        self.assertEqual(v["bounds"], [-1.0, -1.0, 101.0, 100.0])
        printed = sum(1 for c in self.cells(v) if c[0] != 255)
        self.assertGreater(printed, len(self.cells(v)) // 3)   # sampled layers from all of the height
        self.assertLess(len(v["runs"]), 60000)

    def test_tool_changes(self):
        self.assertEqual(preview.tool_changes(self.LINES), 2)
        self.assertEqual(preview.tool_changes(["T0", "T0"]), 0)


class WindowTests(unittest.TestCase):   # noqa: D101
    """Agent path (start_local_print); the slicing-pipeline path shares open_setup / ask_setup."""
    setUpClass = classmethod(_B.setUpClass.__func__)
    setUp, params, update, answer, setting = _B.setUp, _B.params, _B.update, _B.answer, _B.setting

    def test_extras_offered_only_with_their_command(self):
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        data = boot(windows[0])
        self.assertIn("exhaust_fan", data["prefs"])
        self.assertIn("cover_fan", data["features"])
        self.assertEqual(data["levels"]["tangle_level"], ["low", "medium", "high"])
        self.assertEqual(data["job"]["tool_changes"], 1)
        self.assertEqual(len(data["tags"]), 4)   # one RFID flag per head (Heads settings asks before FORCE)
        self.fake.commands.clear()   # an older firmware: no command list, only the original options
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        data = boot(windows[1])
        self.assertNotIn("exhaust_fan", data["prefs"])
        self.assertEqual(data["features"], [])

    def test_answer_keeps_levels_and_fans_and_drops_what_was_not_offered(self):
        self.answer({"map": {}, "prefs": {"tangle_level": "high", "exhaust_fan": 35, "made_up": True},
                     "purifier": "strong"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        uploaded = self.fake.uploads["part.gcode"].decode()
        self.assertIn("FAN_SPEED=0.35", uploaded)
        self.assertNotIn("made_up", " ".join(self.fake.scripts))

    def test_exhaust_not_sent_while_the_cover_recirculates(self):
        self.answer({"map": {}, "prefs": {"exhaust_fan": 90, "inner_fan": 40}, "purifier": "keep-warm"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        uploaded = self.fake.uploads["part.gcode"].decode()
        self.assertNotIn("FAN_SPEED=0.90", uploaded)
        self.assertIn("FAN_SPEED=0.40", uploaded)

    def test_setting_off_still_refuses_a_mismatch(self):
        self.setting(print_dialog=False)
        windows = self.answer({"cancelled": True})
        code = self.agent.start_local_print(self.params(ams_mapping="[1, 0]"), self.update, None)   # PETG on PLA
        self.assertEqual((code, windows, self.fake.order), (self.ns["ERR_LP_PUBLISH"], [], []))

    def test_marked_gcode_skips_the_window_and_the_fixes(self):
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        with open(self.path, "a", newline="") as f:   # "\n" as the rest of the file, on Windows too
            f.write("\n; u1control: print setup done\n")
        with open(self.path, newline="") as f:
            before = f.read()
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertEqual(windows, [])
        self.assertEqual(self.fake.uploads["part.gcode"].decode(), before)   # uploaded unchanged
        self.assertEqual(len([s for s in self.fake.scripts if "SET_PRINT_EXTRUDER_MAP" in s]), 1)   # one script

    def test_agent_marks_what_it_set_up(self):
        self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertTrue(self.fake.uploads["part.gcode"].decode().rstrip().endswith("; u1control: print setup done"))

    def test_plugin_settings_never_raises(self):
        class Gone:
            def post_message(self, m):
                raise RuntimeError("webview gone")
        self.ns["_page_ref"] = lambda: Gone()
        self.addCleanup(self.ns.__setitem__, "_page_ref", lambda: None)
        self.ns["show_settings_tab"]()   # logged, no raise

    def test_title_and_plugin_settings_link(self):
        posted = []
        page = type("P", (), {"post_message": lambda self, m: posted.append(m)})()
        self.ns["_page_ref"] = lambda: page
        self.addCleanup(self.ns.__setitem__, "_page_ref", lambda: None)
        titles = []

        def create(html, title="", on_message=None, on_submit=None, **kw):
            titles.append(title)
            on_message({"ready": True})
            on_message({"open_settings": True})
            w = fakes.FakeWindow(lambda m: None, on_submit, {"cancelled": True})
            w.html = html
            return w
        self.orca.host.ui.create_window = create
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), self.ns["ERR_CANCELED"])
        self.assertEqual(titles, ["U1 Control — print setup"])
        self.assertEqual(posted, [{"type": "show_tab", "tab": "settings"}])

    def test_top_view_comes_after_the_window(self):
        # The window opens without the top view (a placeholder holds its place); it is posted once the page listens
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        job = boot(windows[0])["job"]
        self.assertIsNone(job["preview"])
        self.assertTrue(job["preview_pending"])
        self.assertEqual(job["tool_changes"], 1)   # the other job facts are there at once

    def test_top_view_posted_once_the_page_is_ready(self):
        later = self.ns["Later"](lambda: {"w": 1})
        window = type("W", (), {"posted": [], "post": lambda self, m: self.posted.append(m)})()
        ready, stop = threading.Event(), threading.Event()
        t = threading.Thread(target=self.ns["_post_top_view"], args=(window, later, ready, stop))
        t.start()
        time.sleep(0.3)
        self.assertEqual(window.posted, [])   # not before the page listens
        ready.set()
        t.join(2)
        self.assertEqual(window.posted, [{"preview": {"w": 1}}])
        failed = self.ns["Later"](lambda: 1 / 0)
        window.posted.clear()
        self.ns["_post_top_view"](window, failed, ready, stop)
        self.assertEqual(window.posted, [{"preview": None}])   # the placeholder goes away
        stop.set()
        ready.clear()
        window.posted.clear()
        self.ns["_post_top_view"](window, later, ready, stop)
        self.assertEqual(window.posted, [])   # the window was answered meanwhile

    def test_thumbnail_left_out_when_the_page_would_still_be_too_big(self):
        # A 614,400-character thumbnail (the first 8000 lines are its only bound) is too big even without the preview
        with open(self.path, encoding="utf-8") as f:
            sliced = f.read()
        with open(self.path, "w", newline="") as f:
            f.write("; thumbnail begin 900x900 614400\n" + "; %s\n" % ("A" * 1024) * 600 + "; thumbnail end\n" + sliced)
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertIsNone(boot(windows[0])["job"]["thumbnail"])
        self.assertLessEqual(len(windows[0].html.encode("utf-8")), self.ns["WEBVIEW_PAGE_LIMIT"])
        self.ns["WEBVIEW_PAGE_LIMIT"], limit = 10 ** 9, self.ns["WEBVIEW_PAGE_LIMIT"]
        self.addCleanup(self.ns.__setitem__, "WEBVIEW_PAGE_LIMIT", limit)
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertEqual(len(boot(windows[1])["job"]["thumbnail"]), 614400)   # kept when the page fits

    def _slow_window(self, show, ready_after):
        """A window OrcaSlicer creates at once (show) or never; its page says "ready" ready_after s later."""
        self.ns["SETUP_SHOW_WAIT"], wait = 0.3, self.ns["SETUP_SHOW_WAIT"]
        self.addCleanup(self.ns.__setitem__, "SETUP_SHOW_WAIT", wait)
        windows = []

        class Win(fakes.FakeWindow):
            def __init__(self, on_message, on_submit, html):
                self.on_message, self.on_submit, self.open, self.posted, self.html = on_message, on_submit, True, [], html
                self.created = time.monotonic()
                if show:
                    on_message({"shown": True})   # the page's first script ran; the app is still loading

        def create(html, on_message=None, on_submit=None, **kw):
            windows.append(Win(on_message, on_submit, html))
            return windows[-1]

        def stop():   # polled by the waiting job thread
            w = windows[0] if windows else None
            if w and w.open and show and time.monotonic() - w.created > ready_after:
                w.open = False
                w.on_message({"ready": True})
                w.on_submit({"map": {}, "prefs": {}, "purifier": "auto"})
            return False
        self.orca.host.ui.create_window = create
        return windows, stop

    def test_window_that_shows_but_loads_slowly_is_waited_for(self):
        windows, stop = self._slow_window(show=True, ready_after=0.8)   # "ready" well after SETUP_SHOW_WAIT
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, stop), 0)
        self.assertIn(self.ns["SHOWN_PING"], windows[0].html)
        self.assertTrue(any("SET_PRINT_EXTRUDER_MAP" in s for s in self.fake.scripts))

    def test_window_never_created_gives_up_and_sends_nothing(self):
        windows, stop = self._slow_window(show=False, ready_after=0)
        started = time.monotonic()
        self.assertNotEqual(self.agent.start_local_print(self.params(), self.update, stop), 0)
        self.assertGreaterEqual(time.monotonic() - started, 0.3)
        self.assertFalse(windows[0].open)   # closed, so a late window doesn't stay up
        self.assertEqual(self.fake.scripts, [])

    def test_heads_settings_need_the_tab_for_this_printer(self):
        windows = []

        class Win(fakes.FakeWindow):
            def __init__(self, on_message, on_submit, answer):
                self.on_message, self.on_submit, self.open, self.posted = on_message, on_submit, True, []
                on_message({"ready": True})

        def create(html, on_message=None, on_submit=None, **kw):
            w = Win(on_message, on_submit, None)
            windows.append(w)
            return w

        def stop():   # polled by the waiting job thread once the window exists
            if windows and not getattr(windows[0], "asked", False):
                windows[0].asked = True
                windows[0].on_message({"type": "cmd", "id": 1, "cmd": "set_filament", "args": {"head": 0}})
                windows[0].on_message({"type": "cmd", "id": 2, "cmd": "gcode", "args": {"script": "M112"}})
            if windows and len([m for m in windows[0].posted if m.get("type") == "reply"]) >= 2:
                windows[0].on_submit({"cancelled": True})
            return False
        self.orca.host.ui.create_window = create
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, stop), self.ns["ERR_CANCELED"])
        replies = {m["id"]: m for m in windows[0].posted if m.get("type") == "reply"}
        self.assertIn("U1 Control tab", replies[1]["error"])
        self.assertEqual(replies[2]["error"], "unknown command")   # only the Heads settings commands
        self.assertEqual(self.fake.order, [])



del _B   # not collected a second time from this module


if __name__ == "__main__":
    unittest.main()
