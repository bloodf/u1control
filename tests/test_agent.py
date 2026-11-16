"""The u1control printer agent: status push, Device tab commands, and Print / Send from OrcaSlicer's dialog.
Fakes only (FakePrinter on 127.0.0.1); nothing here talks to a real U1."""

import json
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import agent  # noqa: E402
import fakes  # noqa: E402
import u1  # noqa: E402
from moonraker import Moonraker, UploadCancelled  # noqa: E402
from test_u1control import SAMPLE, wait_for  # noqa: E402

OPTIONS = {"purifier": "auto"}


def heads():
    return u1.describe_toolheads(fakes.task_config())


def view(**kw):
    return {"state": "standby", "machine_state": "IDLE", "heads": heads(), "progress": 0.25, "print_duration": 600,
            "extruders": [{"temp": 200, "target": 210, "active": True}], "bed": {"temp": 60, "target": 60},
            "fan": 0.5, "filename": "a.gcode", "layer": 3, "total_layers": 10, "light": True, **kw}


class PushTests(unittest.TestCase):
    def test_print_dialog_flags(self):
        p = agent.push_status(view())["print"]
        self.assertEqual(p["support_bed_leveling"], 1)
        self.assertIs(p["support_flow_calibration"], True)
        self.assertIs(p["support_timelapse"], True)
        self.assertIs(p["sdcard"], True)
        self.assertEqual(p["home_flag"] >> 8 & 3, agent.HAS_SDCARD_NORMAL)
        self.assertEqual(p["gcode_state"], "IDLE")

    def test_four_toolheads_are_one_four_tray_unit(self):
        block = agent.push_status(view(), {"Generic PLA @System": "GFL99"}.get)["print"]
        self.assertEqual(block["ams_exist_bits"], "1")
        self.assertEqual(block["tray_exist_bits"], "B")   # heads 1, 2 and 4 loaded; 3 empty
        unit, = block["ams"]
        self.assertEqual(unit["id"], "0")
        trays = unit["tray"]
        self.assertEqual([t["id"] for t in trays], ["0", "1", "2", "3"])
        self.assertEqual((trays[0]["tray_type"], trays[0]["tray_color"], trays[0]["tray_info_idx"]), ("PLA", "FF0000FF", "GFL99"))
        self.assertEqual(trays[1]["tray_type"], "PETG")
        self.assertEqual(trays[2]["tray_slot_placeholder"], "1")
        self.assertEqual(trays[3]["tray_type"], "PLA MATTE")
        self.assertEqual(trays[3]["tray_color"], "000000FF")

    def test_state_progress_and_light(self):
        p = agent.push_status(view(state="printing"))["print"]
        self.assertEqual((p["gcode_state"], p["mc_percent"], p["mc_remaining_time"]), ("RUNNING", 25, 30))
        self.assertEqual((p["layer_num"], p["total_layer_num"], p["fan_gear"]), (3, 10, 128))
        self.assertEqual(p["lights_report"], [{"node": "chamber_light", "mode": "on"}])
        self.assertEqual(agent.push_status(view(state="complete"))["print"]["gcode_state"], "FINISH")

    def test_loading_or_calibrating_is_not_idle(self):
        self.assertEqual(agent.push_status(view(machine_state="AUTO_LOAD"))["print"]["gcode_state"], "PREPARE")

    def test_tray_type(self):
        self.assertEqual(agent.tray_type("PLA", "Basic"), "PLA")
        self.assertEqual(agent.tray_type("pla", "SnapSpeed"), "PLA HIGH SPEED")
        self.assertEqual(agent.tray_type("PETG", "CF"), "PETG-CF")
        self.assertEqual(agent.tray_type("", ""), "PLA")


class CommandTests(unittest.TestCase):
    def kind(self, msg):
        return agent.parse_command(json.dumps(msg))

    def test_kinds(self):
        self.assertEqual(self.kind({"info": {"command": "get_version"}})["kind"], "get_version")
        self.assertEqual(self.kind({"pushing": {"command": "start"}})["kind"], "pushall")
        self.assertEqual(self.kind({"print": {"command": "pause", "sequence_id": "4"}}), {"kind": "pause", "seq": "4"})
        self.assertEqual(self.kind({"system": {"command": "ledctrl", "led_node": "chamber_light", "led_mode": "off"}}),
                         {"kind": "set_light", "on": False, "seq": ""})
        self.assertEqual(self.kind({"print": {"command": "gcode_line", "param": "M104 S200\n"}})["script"], "M104 S200\n")

    def test_unsupported_and_invalid(self):
        self.assertEqual(self.kind({"print": {"command": "calibration"}})["kind"], "unsupported")
        self.assertEqual(self.kind({"print": {"command": "gcode_line", "param": "  "}})["kind"], "unsupported")
        self.assertEqual(agent.parse_command("not json")["kind"], "invalid")
        self.assertEqual(agent.parse_command("[1]")["kind"], "invalid")


class JobPartsTests(unittest.TestCase):
    FILS = [{"index": 0, "type": "PLA", "colour": "#FF0000"}, {"index": 1, "type": "PETG", "colour": "#FFFFFF"}]

    def test_mapping_from_dialog_trays(self):
        self.assertEqual(agent.job_mapping("[3, 1]", self.FILS, heads()), {0: 3, 1: 1})
        self.assertEqual(agent.job_mapping([3, 1], self.FILS, heads()), {0: 3, 1: 1})   # a list as well as JSON

    def test_unmapped_or_bad_trays_use_the_automatic_match(self):
        auto = u1.auto_map(self.FILS, heads())
        for trays in ("[-1, -1]", "", "nonsense", '["0", true]', "[7, 4]"):
            with self.subTest(trays=trays):
                self.assertEqual(agent.job_mapping(trays, self.FILS, heads()), auto)

    def test_prefs_take_the_dialog_boxes(self):
        prefs = agent.job_prefs({"bed_level": False, "flow_calibrate": True, "time_lapse_camera": False,
                                 "auto_refill": True}, 1, 0, True)
        self.assertEqual(prefs, {"bed_level": True, "flow_calibrate": False, "time_lapse_camera": True, "auto_refill": True})

    def test_upload_name(self):
        self.assertEqual(agent.upload_name("Part #1; v2.3mf", "/x/y.gcode"), "Part _1_ v2.gcode")
        self.assertEqual(agent.upload_name("", "/tmp/.plate_1.gcode"), "plate_1.gcode")
        self.assertEqual(agent.upload_name('a/b"c', "x"), "b_c.gcode")

    def test_plate_gcode_from_3mf(self):
        fd, path = tempfile.mkstemp(suffix=".gcode.3mf")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Metadata/plate_2.gcode", "G28\n")
            z.writestr("Metadata/plate_1.gcode", "G1\n")
        with tempfile.SpooledTemporaryFile() as out:
            agent.plate_gcode(path, 2, out)
            out.seek(0)
            self.assertEqual(out.read(), b"G28\n")
        with tempfile.SpooledTemporaryFile() as out, self.assertRaises(agent.JobError):
            agent.plate_gcode(path, 5, out)


class FakeJobTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.client = Moonraker(self.fake.host, timeout=5)
        self.work = tempfile.mkdtemp()
        fd, self.path = tempfile.mkstemp(suffix=".gcode")
        with os.fdopen(fd, "w") as f:
            f.write(SAMPLE)
        self.addCleanup(os.remove, self.path)

    def run_job(self, ams="[3, 1]", task=None, **kw):
        task = task or {"bed_leveling": True, "flow_cali": False, "timelapse": True}
        return agent.run_job(self.client, self.path, "My part", 1, ams, OPTIONS,
                             lambda v: {"bed_level": False, "flow_calibrate": True, "time_lapse_camera": False,
                                        "auto_refill": v["options"]["auto_refill"]},
                             task, "0.10.0", self.work, **kw)

    def test_upload_streams_with_progress_and_can_stop(self):
        seen = []
        self.client.upload(self.path, "x.gcode", progress=lambda s, t: seen.append((s, t)))
        self.assertEqual(self.fake.uploads["x.gcode"], SAMPLE.encode())
        self.assertEqual(seen[-1], (len(SAMPLE), len(SAMPLE)))
        with self.assertRaises(UploadCancelled):
            self.client.upload(self.path, "y.gcode", cancelled=lambda: True)
        self.assertNotIn("y.gcode", self.fake.uploads)

    def test_print_maps_fixes_uploads_then_sets_options_then_starts(self):
        job = self.run_job()
        self.assertEqual([k for k, _ in self.fake.order], ["upload", "gcode", "start"])
        self.assertEqual(job["filename"], "My part.gcode")
        self.assertEqual(self.fake.started, ["My part.gcode"])
        script = self.fake.scripts[-1]
        self.assertIn("SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=0 MAP_EXTRUDER=3", script)   # the dialog's pick, not
        self.assertIn("SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=1 MAP_EXTRUDER=1", script)   # the colour match (T1)
        self.assertIn("SET_PRINT_USED_EXTRUDERS EXTRUDERS=1,3", script)
        self.assertIn("BED_LEVEL=1 FLOW_CALIBRATE=0 TIME_LAPSE_CAMERA=1 AUTO_REPLENISH_FILAMENT=1", script)
        sent = self.fake.uploads["My part.gcode"].decode()
        self.assertIn("; u1control", sent)                                   # G-code fixes applied
        self.assertIn("BED_MESH_CALIBRATE PROBE_COUNT=11,11", sent)
        self.assertEqual(os.listdir(self.work), [])                            # work file removed
        with open(self.path) as f:
            self.assertEqual(f.read(), SAMPLE)                                 # OrcaSlicer's file untouched

    def test_busy_printer_gets_nothing(self):
        self.fake.state = "printing"
        with self.assertRaisesRegex(agent.JobError, "busy"):
            self.run_job()
        self.assertEqual(self.fake.order, [])

    def test_warnings_refuse_the_job(self):
        with self.assertRaisesRegex(agent.JobError, "T3: toolhead is empty"):
            self.run_job(ams="[2, 1]")
        self.assertEqual(self.fake.order, [])
        self.assertEqual(os.listdir(self.work), [])

    def test_not_a_u1_print(self):
        with open(self.path, "w") as f:
            f.write("G28\n; printer_model = Other\n")
        with self.assertRaisesRegex(agent.JobError, "Snapmaker U1"):
            self.run_job()
        self.assertEqual(self.fake.order, [])

    def test_cancel_during_upload_starts_nothing(self):
        with self.assertRaises(agent.Cancelled):
            self.run_job(cancelled=lambda: True)
        self.assertEqual(self.fake.started, [])
        self.assertEqual(self.fake.scripts, [])

    def test_send_uploads_fixed_gcode_only(self):
        name = agent.send_job(self.client, self.path, "", 1, OPTIONS, "0.10.0", self.work)
        self.assertEqual(name, os.path.basename(self.path))
        self.assertEqual([k for k, _ in self.fake.order], ["upload"])
        self.assertIn("; u1control", self.fake.uploads[name].decode())


class PluginAgentTests(unittest.TestCase):
    """The agent class in the built wheel, against a fake orca module and FakePrinter."""

    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=pathlib.Path(tempfile.mkdtemp())))

    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.orca = fakes.install_orca()
        self.ns = fakes.load_wheel(self.artifact)
        self.ns["U1Control"]().register_capabilities()
        self.agent = self.ns["U1Agent"]()
        self.addCleanup(self.agent.disconnect_printer)
        fd, self.path = tempfile.mkstemp(suffix=".gcode")
        with os.fdopen(fd, "w") as f:
            f.write(SAMPLE)
        self.addCleanup(os.remove, self.path)
        self.updates = []

    def params(self, **kw):
        return self.orca.printer_agent.PrintParams(**{"filename": self.path, "dev_ip": self.fake.host,
                                                      "project_name": "part", "ams_mapping": "[0, 1]", **kw})

    def update(self, stage, code, text):
        self.updates.append((stage, code, text))

    def test_registered_with_its_id_and_job_read_grant(self):
        self.assertIn("U1Agent", [c.__name__ for c in self.orca.registered])
        info = self.agent.get_agent_info()
        self.assertEqual(info.id, "u1control")
        reads = self.orca.permission_requests[0]["fs_read"]
        self.assertTrue(reads and all(r.endswith("/*") for r in reads))

    def test_print_from_the_dialog(self):
        p = self.params(task_bed_leveling=True, task_flow_cali=True, task_record_timelapse=False)
        self.assertEqual(self.agent.start_local_print(p, self.update, lambda: False), 0)
        self.assertEqual(self.fake.started, ["part.gcode"])
        self.assertIn("BED_LEVEL=1 FLOW_CALIBRATE=1 TIME_LAPSE_CAMERA=0", self.fake.scripts[-1])
        self.assertEqual(self.updates[-1][0], self.ns["STAGE_FINISHED"])
        self.assertIn(self.ns["STAGE_UPLOAD"], [u[0] for u in self.updates])
        job, = self.ns["service"]().ledger.jobs.values()            # filament use booked for Spoolman
        self.assertEqual((job.path, job.per_head), ("part.gcode", {0: 3.5, 1: 1.2}))

    def test_refusal_is_reported_and_nothing_starts(self):
        self.fake.state = "paused"
        code = self.agent.start_local_print(self.params(), self.update, None)
        self.assertEqual(code, self.ns["ERR_LP_PUBLISH"])
        self.assertEqual(self.updates[-1][0], self.ns["STAGE_ERROR"])
        self.assertIn("busy", self.updates[-1][2])
        self.assertEqual(self.fake.order, [])

    def test_cancelled_before_start(self):
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, lambda: True), self.ns["ERR_CANCELED"])
        self.assertEqual(self.fake.order, [])

    def test_send_and_verify(self):
        self.assertEqual(self.agent.start_send_gcode_to_sdcard(self.params(), self.update, None, None), 0)
        self.assertEqual(list(self.fake.uploads), ["part.gcode"])
        self.assertEqual(self.fake.started, [])
        self.assertEqual(self.agent.start_send_gcode_to_sdcard(self.params(project_name="verify_job"), None, None, None), 0)
        self.assertEqual(list(self.fake.uploads), ["part.gcode"])   # the check uploads nothing

    def test_connect_pushes_status_and_answers_commands(self):
        messages, connected = [], []
        self.agent.set_on_local_message_fn(lambda dev, text: messages.append(json.loads(text)))
        self.agent.set_on_printer_connected_fn(connected.append)
        conn = self.orca.printer_agent.PrinterConnectionParams(dev_id="u1", host=self.fake.host)
        self.assertEqual(self.agent.connect_printer(conn), 0)
        self.assertTrue(wait_for(lambda: messages and connected))
        push = messages[0]["print"]
        self.assertEqual(push["ams"][0]["tray"][1]["tray_type"], "PETG")
        self.assertIs(push["support_timelapse"], True)
        light = json.dumps({"system": {"command": "ledctrl", "led_node": "chamber_light", "led_mode": "on"}})
        self.assertEqual(self.agent.send_message_to_printer("u1", light, 0, 0), 0)
        self.assertTrue(wait_for(lambda: agent.LIGHT_ON in self.fake.scripts))
        line = json.dumps({"print": {"command": "gcode_line", "param": "M140 S50", "sequence_id": "9"}})
        self.agent.send_message_to_printer("u1", line, 0, 0)
        self.assertTrue(wait_for(lambda: any(m.get("print", {}).get("command") == "gcode_line" for m in messages)))
        reply = [m for m in messages if m.get("print", {}).get("command") == "gcode_line"][-1]["print"]
        self.assertEqual((reply["sequence_id"], reply["result"]), ("9", "success"))
        self.assertEqual(self.agent.send_message_to_printer("u1", json.dumps({"print": {"command": "calibration"}}), 0, 0),
                         agent.UNSUPPORTED)

    def test_commands_need_a_connection(self):
        pause = json.dumps({"print": {"command": "pause"}})
        self.assertEqual(self.agent.send_message_to_printer("u1", pause, 0, 0), self.ns["ERR_CONNECT"])


if __name__ == "__main__":
    unittest.main()
