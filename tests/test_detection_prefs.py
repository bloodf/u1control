"""Camera checks, tangle sensitivity, flow-calibration heads and top-cover fan speeds: the commands they build.
Command names and values are the U1 firmware's (klippy/extras/defect_detection.py, print_task_config.py,
purifier.py)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import gcode  # noqa: E402
import u1  # noqa: E402
from moonraker import PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_corrections import with_machine  # noqa: E402


class CleanPrefs(unittest.TestCase):
    def test_drops_unknown_keys_and_values_the_firmware_refuses(self):
        self.assertEqual(u1.clean_prefs({
            "spaghetti_detect": 1, "bed_check": 0, "spaghetti_level": "HIGH", "bed_check_level": "medium",
            "tangle_level": "medium", "flow_calibrate_heads": [3, 0, 3, 7, -1, True, "1"],
            "exhaust_fan": 140, "inner_fan": 33.4, "bogus": True, "bed_level": None}), {
            "spaghetti_detect": True, "bed_check": False, "spaghetti_level": "high", "tangle_level": "medium",
            "flow_calibrate_heads": [0, 3], "exhaust_fan": 100, "inner_fan": 33})

    def test_fan_must_be_a_number(self):
        self.assertEqual(u1.clean_prefs({"exhaust_fan": "60", "inner_fan": True}), {})


class PreferenceCommands(unittest.TestCase):
    def test_camera_checks(self):
        lines = u1.preference_commands(u1.clean_prefs(
            {"spaghetti_detect": True, "spaghetti_level": "high", "bed_check": False, "bed_check_level": "low"}))
        self.assertEqual(lines, ["DEFECT_DETECTION_CONFIG MAIN_ENABLE=1 NOODLE_ENABLE=1 NOODLE_SENSITIVITY=high "
                                 "CLEAN_BED_ENABLE=0 CLEAN_BED_SENSITIVITY=low"])

    def test_turning_checks_off_leaves_the_main_switch_alone(self):
        self.assertEqual(u1.preference_commands({"spaghetti_detect": False, "bed_check": False}),
                         ["DEFECT_DETECTION_CONFIG NOODLE_ENABLE=0 CLEAN_BED_ENABLE=0"])

    def test_tangle_sensitivity_rides_on_set_print_preferences(self):
        self.assertEqual(u1.preference_commands({"tangle_detect": True, "tangle_level": "low"}),
                         ["SET_PRINT_PREFERENCES FILAMENT_ENTANGLE_DETECT=1 FILAMENT_ENTANGLE_SEN=low"])

    def test_flow_calibration_heads(self):
        self.assertEqual(u1.preference_commands({"flow_calibrate": True, "flow_calibrate_heads": [0, 2]}),
                         ["SET_PRINT_PREFERENCES FLOW_CALIBRATE=1 FLOW_CALIBRATE_EXTRUDERS=0,2"])
        # an empty list makes the firmware fail the whole command: no heads = no calibration
        self.assertEqual(u1.preference_commands({"flow_calibrate": True, "flow_calibrate_heads": []}),
                         ["SET_PRINT_PREFERENCES FLOW_CALIBRATE=0"])
        self.assertEqual(u1.preference_commands({"flow_calibrate": False, "flow_calibrate_heads": [1]}),
                         ["SET_PRINT_PREFERENCES FLOW_CALIBRATE=0"])

    def test_nothing_offered_sends_nothing(self):
        self.assertEqual(u1.preference_commands({}), [])

    def test_preprint_script_carries_everything(self):
        s = u1.preprint_script({0: 1}, {"bed_level": True, "flow_calibrate": True, "flow_calibrate_heads": [1],
                                        "tangle_detect": True, "tangle_level": "high", "bed_check": True,
                                        "bad": "x"})
        self.assertEqual(s.split("\n")[-2:], [
            "SET_PRINT_PREFERENCES BED_LEVEL=1 FLOW_CALIBRATE=1 FLOW_CALIBRATE_EXTRUDERS=1 "
            "FILAMENT_ENTANGLE_DETECT=1 FILAMENT_ENTANGLE_SEN=high",
            "DEFECT_DETECTION_CONFIG MAIN_ENABLE=1 CLEAN_BED_ENABLE=1"])


class PrinterReports(unittest.TestCase):
    DETECTION = {"main_enable": True, "noodle": {"enable": True, "sensitivity": "high"},
                 "clean_bed": {"enable": False, "sensitivity": "low"}}

    def test_options_and_tuning(self):
        task = {"filament_entangle_detect": True, "filament_entangle_sen": "medium",
                "flow_calib_extruders": [True, False, True, False]}
        self.assertEqual(u1.printer_options(task, self.DETECTION),
                         {"tangle_detect": True, "spaghetti_detect": True, "bed_check": False})
        self.assertEqual(u1.printer_tuning(task, self.DETECTION),
                         {"spaghetti_level": "high", "bed_check_level": "low", "tangle_level": "medium",
                          "flow_calibrate_heads": [0, 2]})

    def test_main_switch_off_means_checks_off(self):
        self.assertFalse(u1.printer_options({}, {**self.DETECTION, "main_enable": False})["spaghetti_detect"])

    def test_firmware_without_the_module_reports_nothing_new(self):
        self.assertEqual(u1.printer_options({}, None), {})
        self.assertEqual(u1.printer_tuning({}, None), {})


class CoverFans(unittest.TestCase):
    def test_fan_speed_goes_to_the_mode_fan(self):
        self.assertIn("FAN_SPEED=0.80", u1.purifier_command("strong", {"exhaust_fan": 80, "inner_fan": 20}))
        self.assertIn("FAN_SPEED=0.20", u1.purifier_command("keep-warm", {"exhaust_fan": 80, "inner_fan": 20}))
        self.assertEqual(u1.purifier_command("weak", {"inner_fan": 20}), u1.PURIFIER["weak"])

    def test_gcode_process_writes_the_speed(self):
        lines = ["PRINT_START", "SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45", ";LAYER_CHANGE"]
        out, mode = gcode.process(lines, {}, {"purifier": "weak", "exhaust_fan": 45, "chamber_wait": False})
        self.assertEqual(mode, "weak")
        self.assertIn("SET_PURIFIER_MODE MODE=1 DESIRE_TEMP=45 ALARM_TEMP=51 FAN_SPEED=0.45 DELAY_OFF=0", out)
        again = gcode.ensure_purifier(out, "weak")   # re-run restores the sliced line first
        self.assertIn(u1.PURIFIER["weak"], again)
        self.assertNotIn("FAN_SPEED=0.45", "\n".join(again))


class ServicePreferences(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host, spoolman_url="http://" + self.fake.host))
        self.svc.cmd_connect()

    def test_sends_detection_settings_when_idle(self):
        self.svc.cmd_preferences({"spaghetti_detect": True, "spaghetti_level": "low", "tangle_level": "high"})
        self.assertEqual(self.fake.scripts[-1], "SET_PRINT_PREFERENCES FILAMENT_ENTANGLE_SEN=high\n"
                                                "DEFECT_DETECTION_CONFIG MAIN_ENABLE=1 NOODLE_ENABLE=1 NOODLE_SENSITIVITY=low")

    def test_refuses_a_busy_printer(self):
        with_machine(self.fake, "PRINTING")
        with self.assertRaises(PrinterError):
            self.svc.cmd_preferences({"bed_check": True})
        self.assertEqual(self.fake.scripts, [])

    def test_bad_values_are_nothing_to_change(self):
        with self.assertRaises(ValueError):
            self.svc.cmd_preferences({"spaghetti_level": "medium"})   # the camera checks have no medium


if __name__ == "__main__":
    unittest.main()
