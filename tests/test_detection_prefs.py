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


U1_COMMANDS = frozenset({"SET_PRINT_PREFERENCES", "DEFECT_DETECTION_CONFIG", "SET_PURIFIER", "SET_PURIFIER_MODE"})
EVERYTHING = {"spaghetti_detect": True, "spaghetti_level": "high", "bed_check": True, "bed_check_level": "low",
              "tangle_detect": True, "tangle_level": "high", "flow_calibrate": True, "flow_calibrate_heads": [0],
              "exhaust_fan": 70, "inner_fan": 30}


class CommandDetection(unittest.TestCase):
    def test_command_present_keeps_the_option(self):
        self.assertEqual(u1.clean_prefs(EVERYTHING, U1_COMMANDS), EVERYTHING)

    def test_command_absent_drops_the_option(self):
        no_camera = U1_COMMANDS - {"DEFECT_DETECTION_CONFIG"}
        kept = u1.clean_prefs(EVERYTHING, no_camera)
        self.assertNotIn("spaghetti_detect", kept)
        self.assertNotIn("bed_check_level", kept)
        self.assertEqual(kept["tangle_level"], "high")
        self.assertNotIn("DEFECT_DETECTION_CONFIG", u1.preprint_script({0: 0}, EVERYTHING, no_camera))
        fans = u1.clean_prefs(EVERYTHING, U1_COMMANDS - {"SET_PURIFIER_MODE"})
        self.assertFalse(set(u1.COVER_FANS) & set(fans))

    def test_unknown_command_list_sends_only_the_original_options(self):
        self.assertEqual(u1.clean_prefs(EVERYTHING, None), {"tangle_detect": True, "flow_calibrate": True})
        self.assertEqual(u1.clean_prefs(EVERYTHING, frozenset()), {"tangle_detect": True, "flow_calibrate": True})


class Features(unittest.TestCase):
    def test_features_follow_the_command_list(self):
        self.assertEqual(set(u1.features(U1_COMMANDS)), set(u1.FEATURE_COMMANDS) | {"cover_fan"})
        self.assertEqual(u1.features(frozenset({"SET_PRINT_PREFERENCES"})), ["tangle_level", "flow_calibrate_heads"])
        self.assertEqual(u1.features(None), [])

    def test_connect_reads_the_list_and_status_carries_it(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        del fake.commands["DEFECT_DETECTION_CONFIG"]
        svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host, spoolman_url="http://" + fake.host))
        svc.cmd_connect()
        self.assertNotIn("DEFECT_DETECTION_CONFIG", svc.gcode_cmds)
        self.assertIn("SET_PURIFIER", svc.gcode_cmds)


class ExhaustBlock(unittest.TestCase):
    def test_recirculation_modes(self):
        for mode in (2, 3, "keep-warm"):
            self.assertTrue(u1.exhaust_blocked(mode), mode)
        for mode in (0, 1, "weak", "strong", None, True):
            self.assertFalse(u1.exhaust_blocked(mode), mode)
        self.assertTrue(u1.summarize({"purifier": {"mode": 2}})["purifier"]["recirculating"])

    def test_live_command(self):
        with self.assertRaises(ValueError):
            u1.cover_fan_command("exhaust", 30, 2)
        self.assertEqual(u1.cover_fan_command("exhaust", 30, 1), "SET_PURIFIER FAN=exhaust SPEED=0.30")

    def test_keep_warm_print_never_takes_the_exhaust_speed(self):
        self.assertEqual(u1.purifier_command("keep-warm", {"exhaust_fan": 90}), u1.PURIFIER["keep-warm"])


class Offering(unittest.TestCase):
    VIEW = {"options": {"tangle_detect": False, "spaghetti_detect": True, "bed_check": False, "bed_level": True},
            "tuning": {"spaghetti_level": "low", "bed_check_level": "high", "flow_calibrate_heads": [0, 1, 2, 3]},
            "purifier": {"fitted": True}}

    def test_offers_what_the_printer_has_with_saved_choices_first(self):
        self.assertEqual(u1.offered_extras({"spaghetti_level": "high", "exhaust_fan": 90}, self.VIEW, U1_COMMANDS), {
            "spaghetti_detect": True, "bed_check": False, "spaghetti_level": "high", "bed_check_level": "high",
            "tangle_level": "medium", "flow_calibrate_heads": [0, 1, 2, 3], "exhaust_fan": 90, "inner_fan": 60})

    def test_offers_nothing_the_printer_cannot_take(self):
        self.assertEqual(u1.offered_extras({}, self.VIEW, frozenset({"SET_PRINT_PREFERENCES"})),
                         {"tangle_level": "medium", "flow_calibrate_heads": [0, 1, 2, 3]})
        self.assertEqual(u1.offered_extras({}, self.VIEW, None), {})

    def test_no_cover_no_fans(self):
        offered = u1.offered_extras({}, {**self.VIEW, "purifier": {"fitted": False}}, U1_COMMANDS)
        self.assertFalse(set(u1.COVER_FANS) & set(offered))

    def test_answer_is_limited_to_what_was_offered(self):
        offered = {"spaghetti_detect": True, "spaghetti_level": "low"}
        self.assertEqual(u1.pick_prefs(offered, {"spaghetti_level": "high", "bed_check": True, "exhaust_fan": 5}),
                         {"spaghetti_detect": True, "spaghetti_level": "high"})


class GcodeHelp(unittest.TestCase):
    def test_reads_the_command_list(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        from moonraker import Moonraker
        fake.commands = {"set_purifier": "", "PAUSE": ""}
        self.assertEqual(Moonraker(fake.host).gcode_commands(), frozenset({"SET_PURIFIER", "PAUSE"}))
        self.assertEqual(fake.scripts, [])   # a read: nothing sent to the printer


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

    def test_hidden_when_the_printer_lacks_the_command(self):
        del self.fake.commands["DEFECT_DETECTION_CONFIG"]
        with self.assertRaises(ValueError):
            self.svc.cmd_preferences({"spaghetti_detect": True})
        self.assertEqual(self.fake.scripts, [])

    def test_cover_fan_now(self):
        self.svc.cmd_cover_fan("exhaust", 75)
        self.assertEqual(self.fake.scripts[-1], "SET_PURIFIER FAN=exhaust SPEED=0.75")
        self.svc.cmd_cover_fan("inner", 0)
        self.assertEqual(self.fake.scripts[-1], "SET_PURIFIER FAN=inner SPEED=0.00")
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_cover_fan("side", 50)
        self.assertIn("top-cover fan", str(e.exception))

    def test_exhaust_refused_while_the_cover_recirculates(self):
        base = self.fake.status
        self.fake.status = lambda: {**base(), "purifier": {"power_detected": True, "mode": 3}}
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_cover_fan("exhaust", 50)
        self.assertIn("recirculates", str(e.exception))
        self.svc.cmd_cover_fan("exhaust", 0)    # turning it off is fine
        self.svc.cmd_cover_fan("inner", 40)     # the recirculation fan itself is fine
        self.assertEqual(self.fake.scripts, ["SET_PURIFIER FAN=exhaust SPEED=0.00", "SET_PURIFIER FAN=inner SPEED=0.40"])

    def test_cover_fan_needs_the_command_and_an_idle_printer(self):
        del self.fake.commands["SET_PURIFIER"]
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_cover_fan("exhaust", 50)
        self.assertIn("not supported by this firmware", str(e.exception))
        self.fake.commands["SET_PURIFIER"] = ""
        with_machine(self.fake, "PRINTING")
        with self.assertRaises(PrinterError):
            self.svc.cmd_cover_fan("exhaust", 50)
        self.assertEqual(self.fake.scripts, [])


if __name__ == "__main__":
    unittest.main()
