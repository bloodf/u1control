"""The print setup window after OrcaSlicer's Print: offered options by command list, the answer as sent, the
top-cover fans, Heads settings, the Plugin settings link, the job facts and the preview. Never contacts a printer:
FakePrinter is a local HTTP server."""

import json
import os
import re
import sys
import tempfile
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

    def test_paths_by_tool_and_bounds(self):
        p = preview.paths(self.LINES)
        self.assertEqual(p["tools"]["0"][:4], [0.0, 0.0, 10.0, 0.0])
        self.assertEqual(p["tools"]["1"], [10.0, 10.0, 0.0, 10.0])
        self.assertEqual(p["bounds"], [0.0, 0.0, 20.0, 20.0])

    def test_budget_samples_layers(self):
        lines = []
        for layer in range(100):
            lines += [";LAYER_CHANGE", "G1 X0 Y0"] + ["G1 X%d Y1 E%d" % (i, layer * 50 + i) for i in range(1, 50)]
        small = preview.paths(lines, budget=500)   # absolute E (M82): extrusion is the rise in E
        drawn = sum(len(v) // 4 for v in small["tools"].values())
        self.assertTrue(0 < drawn <= 500, drawn)
        self.assertIsNone(preview.paths(["G28", "G1 X1 Y1"]))

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

    def test_preview_left_out_when_the_page_would_be_too_big(self):
        real = self.ns["preview"]
        big = {"bounds": [0, 0, 1, 1], "tools": {"0": [0.0, 0.0, 1.0, 1.0] * 50000}}   # ~1 MB of JSON
        self.ns["preview"] = type("P", (), {"paths": staticmethod(lambda lines: big),
                                            "tool_changes": staticmethod(real.tool_changes)})
        self.addCleanup(self.ns.__setitem__, "preview", real)
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertIsNone(boot(windows[0])["job"]["preview"])   # over the default limit
        self.ns["SETUP_PAGE_LIMIT"], limit = 10 ** 9, self.ns["SETUP_PAGE_LIMIT"]
        self.addCleanup(self.ns.__setitem__, "SETUP_PAGE_LIMIT", limit)
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertEqual(boot(windows[1])["job"]["preview"], big)   # kept when the page fits
        self.assertEqual(boot(windows[0])["job"]["tool_changes"], 1)   # the other job facts stay

    def test_long_plate_page_stays_under_the_limit_with_its_preview(self):
        # A long plate (300 layers of 1000 moves, two heads): the sampled preview keeps the page small enough for
        # OrcaSlicer's WebView2 on Windows, so the preview is kept, not dropped by the safety net.
        with open(self.path, "a", newline="") as f:   # "\n" as written, also on Windows
            f.write("\nM83\n")   # SAMPLE has no final newline
            for layer in range(300):
                f.write(";LAYER_CHANGE\nT%d\n" % (layer % 2))
                f.writelines("G1 X%.3f Y%.3f E0.04\n" % (i % 250 + 0.123, layer % 250 + 0.456) for i in range(1000))
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertIsNotNone(boot(windows[0])["job"]["preview"])
        self.assertLess(len(windows[0].html.encode("utf-8")), self.ns["SETUP_PAGE_LIMIT"])

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
            if windows and not windows[0].posted and not getattr(windows[0], "asked", False):
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
