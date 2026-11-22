"""Nozzle type check, multiACE (step aside, read-only units, dry on a click) and per-spool pressure advance.

multiACE payloads follow decay71/multiACE docs/ENGINE_API.md (api_version 1); no printer is contacted."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import gcode  # noqa: E402
import spoolman as sm  # noqa: E402
import u1  # noqa: E402
from moonraker import PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_automagic import PluginBase, write  # noqa: E402
from test_corrections import with_machine  # noqa: E402
from test_u1control import SAMPLE  # noqa: E402


def ace_status(mode="multi", api=1, drying=False):
    """The `ace` object as ENGINE_API section 4 shows it: two units, unit 0 feeding head 0 from slot 1."""
    slot = lambda m, c: {"index": 0, "status": "ready" if m else "empty", "material": m, "brand": "", "rfid": 0, "color": c}
    unit = lambda i: {"idx": i, "connected": True, "kind": "v2", "caps": {"has_dryer": True}, "unit_name": "",
                      "unit_present": True, "temp": 26, "humidity": 41,
                      "dryer_status": {"status": "drying" if drying and i == 0 else "stop", "target_temp": 50,
                                       "duration": 240, "remain_time": 3600 if drying and i == 0 else 0},
                      "slots": [slot("PLA", [255, 0, 0]), slot("PETG", [0, 0, 0]), slot("", [0, 0, 0]), slot("TPU", [1, 2, 3])]}
    return {"api_version": api, "mode": mode, "swap_in_progress": False,
            "head_source": {"0": {"ace_index": 0, "slot": 1, "type": "PETG"}, "1": None, "2": None, "3": None},
            "aces": [unit(0), unit(1)]}


class NozzleCheck(unittest.TestCase):
    def test_sliced_nozzle_follows_filament_map(self):
        cfg = {"nozzle_volume_type": "Standard,High Flow,Standard,Standard", "filament_map": "2,1,1,1,3"}
        self.assertEqual(gcode.sliced_nozzles(cfg)[:6], ["high_flow", "standard", "standard", "standard", "standard", ""])
        self.assertEqual(gcode.sliced_nozzles({})[:2], ["", ""])   # an older OrcaSlicer: unknown, no warning

    def test_warning_only_when_both_sides_know(self):
        heads = [{"index": i, "loaded": True, "type": "PLA", "nozzle": n} for i, n in enumerate(("high_flow", "", "standard", "standard"))]
        fils = [{"index": 0, "type": "PLA", "nozzle": "standard"}, {"index": 1, "type": "PLA", "nozzle": "standard"},
                {"index": 2, "type": "PLA", "nozzle": ""}]
        self.assertEqual(u1.warning_ids(fils, heads, {0: 0, 1: 1, 2: 2}), ["nozzle:0:0"])
        self.assertIn("High Flow", u1.mapping_warnings(fils, heads, {0: 0, 1: 1, 2: 2})[0])

    def test_status_carries_nozzle_and_pressure_advance(self):
        view = u1.summarize({"extruder": {"nozzle_volume_type": "high_flow", "pressure_advance": 0.03251},
                             "print_task_config": fakes.task_config()})
        self.assertEqual((view["heads"][0]["nozzle"], view["heads"][1]["nozzle"]), ("high_flow", ""))
        self.assertEqual((view["extruders"][0]["pa"], view["extruders"][1]["pa"]), (0.0325, None))


class MultiAce(unittest.TestCase):
    def test_absent_normal_or_other_api_is_no_multiace(self):
        for ace in (None, ace_status(mode="normal"), ace_status(api=2), "junk"):
            self.assertIsNone(u1.ace_view(ace), ace if not isinstance(ace, dict) else ace["mode"])
        self.assertFalse(u1.multiace(u1.summarize({})))

    def test_view_of_units_slots_and_heads(self):
        view = u1.ace_view(ace_status(drying=True))
        self.assertEqual(view["heads"], {"0": [0, 1], "1": None, "2": None, "3": None})
        unit = view["units"][0]
        self.assertEqual((unit["temp"], unit["humidity"], unit["dryer"], unit["drying"]), (26, 41, True, {"temp": 50, "left": 3600}))
        self.assertEqual([s["colour"] for s in unit["slots"]], ["#FF0000", "#000000", None, "#010203"])   # black only with a material
        self.assertIsNone(view["units"][1]["drying"])

    def test_no_toolhead_map_when_multiace_routes(self):
        script = u1.preprint_script({}, {"bed_level": True}, None)
        self.assertNotIn("SET_PRINT_EXTRUDER_MAP", script)
        self.assertNotIn("SET_PRINT_USED_EXTRUDERS", script)
        self.assertIn("BED_LEVEL=1", script)


class AceDry(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.fake.commands["ACE_DRY"] = ""
        self.fake.extra["ace"] = ace_status()
        self.svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host))
        self.svc.cmd_connect()

    def test_start_and_stop_on_an_idle_u1(self):
        self.svc.cmd_ace_dry(1, True)
        self.svc.cmd_ace_dry(0, False)
        self.assertEqual(self.fake.scripts, ["ACE_DRY ACE=1", "ACE_STOP_DRYING ACE=0"])

    def test_refused_while_printing_swapping_or_without_multiace(self):
        with_machine(self.fake, "PRINTING")
        with self.assertRaises(PrinterError):
            self.svc.cmd_ace_dry(0, True)
        with_machine(self.fake, "IDLE")
        self.fake.extra["ace"] = {**ace_status(), "swap_in_progress": True}
        with self.assertRaises(PrinterError):
            self.svc.cmd_ace_dry(0, True)
        self.fake.extra["ace"] = ace_status()
        for bad in (5, True, "0"):
            with self.assertRaises(ValueError):
                self.svc.cmd_ace_dry(bad, True)
        del self.fake.commands["ACE_DRY"]
        with self.assertRaises(ValueError):
            self.svc.cmd_ace_dry(0, True)
        self.assertEqual(self.fake.scripts, [])


class PressureAdvance(unittest.TestCase):
    def test_matrix_read_tolerantly(self):
        self.assertEqual(sm.pa_matrix({"extra": {sm.PA_FIELD: json.dumps(json.dumps({"0.4_standard": 0.032}))}}), {"0.4_standard": 0.032})
        self.assertEqual(sm.pa_matrix({"extra": {sm.PA_FIELD: '{"0.6_high_flow": 0.05, "x": "no"}'}}), {"0.6_high_flow": 0.05})
        self.assertEqual(sm.pa_matrix({"extra": {sm.PA_FIELD: "garbage"}}), {})

    def test_stored_value_for_the_nozzle_the_head_has(self):
        heads = [{"nozzle": "standard"}, {"nozzle": "high_flow"}, {"nozzle": ""}, {"nozzle": "standard"}]
        spools = {"0": {"pa": {"0.4_standard": 0.032}}, "1": {"pa": {"0.4_standard": 0.04}}, "2": {"pa": {"0.4_standard": 0.05}},
                  "3": {"pa": {"0.4_standard": 9}}}
        self.assertEqual(u1.stored_pa(heads, [0.4, 0.4, 0.4, 0.4], spools), {0: 0.032, 2: 0.05})   # no type = standard
        self.assertEqual(u1.stored_pa(heads, [None] * 4, spools), {})

    def test_set_right_after_print_start(self):
        lines = ["G28", "PRINT_START EXTRUDER=0", "G1 X1"]
        out = gcode.stored_pressure_advance(lines, {2: 0.041})
        self.assertEqual(out[2].split(";")[0].strip(), "SET_PRESSURE_ADVANCE EXTRUDER=extruder2 ADVANCE=0.0410")
        self.assertEqual(gcode.stored_pressure_advance(["G1 X1"], {0: 0.03}), ["G1 X1"])

    def test_save_to_the_bound_spool_only_on_request(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.extra.update({"extruder1": {"pressure_advance": 0.0375, "nozzle_volume_type": "high_flow"},
                           "configfile": {"settings": {"extruder1": {"nozzle_diameter": 0.4}}}})
        svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host, spoolman_url="http://" + fake.host))
        svc.cmd_connect()
        svc.cmd_spools()
        with self.assertRaises(ValueError):
            svc.cmd_save_pa(1)   # no spool on T2
        svc.bindings[1] = 9
        result = svc.cmd_save_pa(1)
        self.assertEqual((result["key"], result["value"]), ("0.4_high_flow", 0.0375))
        self.assertEqual(fake.fields[0]["key"], sm.PA_FIELD)
        self.assertEqual(sm.pa_matrix(fake.patches[-1][1]), {"0.4_high_flow": 0.0375})
        self.assertEqual(fake.scripts, [])   # nothing went to the printer


class PrintSetupSteps(PluginBase):
    def run_setup(self, ace=None, answer=None):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        if ace:
            fake.extra["ace"] = ace
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        write(path, SAMPLE)
        ctx = type("X", (), dict(step="post", gcode_path=path, host="OctoPrint", output_name="p.gcode",
                                 config_value=lambda self, k: {"print_host": fake.host}.get(k, "")))()
        orca, ns = self.load(answer=answer or {"map": {}, "prefs": {}, "purifier": "auto"})
        self.assertEqual(ns["U1PrintSetup"]().execute(ctx).status, "success")
        with open(path) as f:
            return fake, orca, f.read()

    def test_multiace_routes_so_the_file_and_the_map_are_left_alone(self):
        fake, orca, text = self.run_setup(ace_status())
        self.assertEqual(text, SAMPLE)   # no u1control lines: multiACE's own tools refuse a file marked by U1 Control
        self.assertFalse(any("SET_PRINT_EXTRUDER_MAP" in sc or "SET_PRINT_USED_EXTRUDERS" in sc for sc in fake.scripts))
        self.assertIn('"multiace":true', orca.windows[0].html.replace(" ", ""))

    def test_without_multiace_nothing_changes(self):
        fake, orca, text = self.run_setup(ace_status(mode="normal"))
        self.assertIn(gcode.MARK, text)
        self.assertTrue(any("SET_PRINT_EXTRUDER_MAP" in sc for sc in fake.scripts))


if __name__ == "__main__":
    unittest.main()
