"""What a toolhead's print_task_config record means: every colour of a multi-colour spool (filament_color_multi), and
a loaded head nobody has named (all NONE), which is neither empty nor a filament a preset can be matched to."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import agent  # noqa: E402
import u1  # noqa: E402


def task():
    """The fake U1 of the GUI tests: T2 a three-colour silk, T4 loaded but never named."""
    return {
        "filament_vendor": ["Snapmaker", "Generic", "Generic", "NONE"],
        "filament_type": ["PLA", "PLA", "PLA", "NONE"],
        "filament_sub_type": ["Basic", "Silk", "Silk", "NONE"],
        "filament_color_rgba": ["E53935FF", "FF0000FF", "FDD835FF", "FFFFFFFF"],
        "filament_color_multi": [{"nums": 1, "alpha": 255, "colors": ["E53935"], "mode": 0},
                                 {"nums": 3, "alpha": 255, "colors": ["FF0000", "00FF00", "0000FF"], "mode": 0},
                                 {"nums": 1, "alpha": 255, "colors": ["FDD835"], "mode": 0},
                                 {"nums": 1, "alpha": 255, "colors": ["FFFFFF"], "mode": 0}],
        "filament_official": [True, False, False, False],
        "filament_exist": [True, True, True, True],
    }


class MultiColourTests(unittest.TestCase):
    def test_every_colour_of_a_multi_colour_spool(self):
        heads = u1.describe_toolheads(task())
        self.assertEqual(heads[1]["colours"], ["#FF0000", "#00FF00", "#0000FF"])
        self.assertEqual(heads[1]["colour"], "#FF0000")
        self.assertEqual(heads[0]["colours"], ["#E53935"])

    def test_nums_counts_the_colours_but_never_more_than_listed(self):
        self.assertEqual(u1.multi_colours({"nums": 2, "colors": ["FF0000", "00FF00", "0000FF"]}), ["#FF0000", "#00FF00"])
        self.assertEqual(u1.multi_colours({"nums": 4, "colors": ["FF0000", "00FF00"]}), ["#FF0000", "#00FF00"])
        self.assertEqual(u1.multi_colours({"colors": ["FF0000", "00FF00"]}), ["#FF0000", "#00FF00"])
        self.assertEqual(u1.multi_colours({"nums": 2, "mode": 1, "colors": ["FF0000", "00FF00"]}), ["#FF0000", "#00FF00"])

    def test_a_broken_record_gives_no_colours(self):
        for bad in (None, [], "FF0000", {"nums": 2}, {"nums": 2, "colors": "FF0000"}, {"colors": ["nope"]}):
            self.assertEqual(u1.multi_colours(bad), [], bad)
        self.assertEqual(u1.multi_colours({"nums": True, "colors": ["FF0000", "00FF00"]}), ["#FF0000", "#00FF00"])

    def test_the_agent_tray_carries_every_colour_as_segments(self):
        tray = agent.ams_block(u1.describe_toolheads(task()))["ams"]["ams"][0]["tray"][1]
        self.assertEqual(tray["cols"], ["FF0000FF", "00FF00FF", "0000FFFF"])
        self.assertEqual(tray["ctype"], 1)   # OrcaSlicer: 0 gradient, 1 segments


class UnnamedHeadTests(unittest.TestCase):
    def setUp(self):
        self.heads = u1.describe_toolheads(task())

    def test_loaded_but_not_named(self):
        h = self.heads[3]
        self.assertTrue(h["unnamed"])
        self.assertFalse(h["loaded"])   # no type to match a preset or a mapping to
        self.assertEqual((h["type"], h["vendor"], h["sub_type"]), ("", "", ""))
        self.assertEqual(h["colour"], "#FFFFFF")
        self.assertFalse(any(x["unnamed"] for x in self.heads[:3]))

    def test_an_empty_head_is_not_unnamed(self):
        t = task()
        t["filament_exist"] = [True, True, True, False]
        self.assertFalse(u1.describe_toolheads(t)[3]["unnamed"])
        del t["filament_exist"]   # older firmware: nothing says there is filament
        self.assertFalse(u1.describe_toolheads(t)[3]["unnamed"])

    def test_mapping_to_it_warns_that_it_is_not_named(self):
        fils = [{"index": 0, "type": "PLA"}]
        self.assertEqual(u1.warning_ids(fils, self.heads, {0: 3}), ["unnamed:0:3"])
        self.assertIn("not named", u1.mapping_warnings(fils, self.heads, {0: 3})[0])
        self.assertNotIn(3, u1.auto_map(fils * 1, self.heads).values())

    def test_the_agent_leaves_the_project_filament_there(self):
        tray = agent.ams_block(self.heads)["ams"]["ams"][0]["tray"][3]
        self.assertEqual((tray["tray_info_idx"], tray["tray_type"], tray.get("tray_slot_placeholder")), ("", "", "1"))


if __name__ == "__main__":
    unittest.main()
