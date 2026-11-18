"""The u1control printer agent: status push, Device tab commands, and Print / Send from OrcaSlicer's dialog.
Fakes only (FakePrinter on 127.0.0.1); nothing here talks to a real U1."""

import json
import re
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import agent  # noqa: E402
import spooler_bridge as sb  # noqa: E402
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

    def test_tray_ids_prefer_the_linked_spools_preset_then_generic_by_material(self):
        block = agent.push_status(view(), lambda h: {1: "SPL00000000AB"}.get(h["index"], ""))["print"]
        self.assertEqual([t["tray_info_idx"] for t in block["ams"][0]["tray"]],
                         ["OFDSrzZ8", "SPL00000000AB", "", "OFmY0l6t"])   # Generic PLA, Spooler's, empty, Generic PLA Matte

    def test_generic_ids_match_orcas_library(self):
        """GENERIC_IDS against OrcaFilamentLibrary at the commit in tests/fixtures/orca_generic_ids.json (made by
        scripts/generic_ids.py): a family missing from the library, or an id that differs, fails here."""
        with open(os.path.join(ROOT, "tests", "fixtures", "orca_generic_ids.json"), encoding="utf-8") as f:
            pinned = json.load(f)
        self.assertRegex(pinned["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual({k: pinned["ids"].get(k) for k in agent.GENERIC_IDS}, agent.GENERIC_IDS)

    def test_generic_id_by_the_real_material(self):
        self.assertEqual(agent.generic_filament_id("PETG"), "OFYPdQJh")
        self.assertEqual(agent.material_family("PLA WOOD"), "PLA")   # not in the table: by word
        self.assertEqual(agent.material_family("PETG-CF"), "PETG")
        self.assertEqual(agent.material_family("PLA-CF MATTE"), "PLA-CF")   # longest family
        self.assertEqual(agent.generic_filament_id("WEIRD"), "")
        self.assertTrue(set(agent.FILAMENT_FAMILIES.values()) <= set(agent.GENERIC_IDS))   # an id for every family

    def test_four_toolheads_are_one_four_tray_unit(self):
        block = agent.push_status(view())["print"]
        self.assertEqual(block["ams_exist_bits"], "1")
        self.assertEqual(block["tray_exist_bits"], "B")   # heads 1, 2 and 4 loaded; 3 empty
        unit, = block["ams"]
        self.assertEqual(unit["id"], "0")
        trays = unit["tray"]
        self.assertEqual([t["id"] for t in trays], ["0", "1", "2", "3"])
        self.assertEqual((trays[0]["tray_type"], trays[0]["tray_color"], trays[0]["tray_info_idx"]), ("PLA", "FF0000FF", "OFDSrzZ8"))
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

    def test_an_option_is_on_only_when_its_box_and_the_setting_are(self):
        # OrcaSlicer's dialog starts every box ticked: the setting decides, the box can only turn it off
        prefs = agent.job_prefs({"bed_level": False, "flow_calibrate": True, "time_lapse_camera": False,
                                 "auto_refill": True}, 1, 1, 1)
        self.assertEqual(prefs, {"bed_level": False, "flow_calibrate": True, "time_lapse_camera": False, "auto_refill": True})
        on = {"bed_level": True, "flow_calibrate": True, "time_lapse_camera": True}
        self.assertEqual(agent.job_prefs(on, 1, 0, False),                    # unticked: off, setting or not
                         {"bed_level": True, "flow_calibrate": False, "time_lapse_camera": False})

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
        with os.fdopen(fd, "w", newline="") as f:
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
        asked = []
        with self.assertRaises(UploadCancelled):   # stopped mid-way: the printer gets a cut-off body, keeps no file
            self.client.upload(self.path, "z.gcode", cancelled=lambda: asked.append(1) or len(asked) > 1)
        self.assertEqual(list(self.fake.uploads), ["x.gcode"])

    def test_print_maps_fixes_uploads_then_sets_options_then_starts(self):
        job = self.run_job()
        self.assertEqual([k for k, _ in self.fake.order], ["upload", "gcode", "start"])
        self.assertEqual(job["filename"], "My part.gcode")
        self.assertEqual(self.fake.started, ["My part.gcode"])
        script = self.fake.scripts[-1]
        self.assertIn("SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=0 MAP_EXTRUDER=3", script)   # the dialog's pick, not
        self.assertIn("SET_PRINT_EXTRUDER_MAP CONFIG_EXTRUDER=1 MAP_EXTRUDER=1", script)   # the colour match (T1)
        self.assertIn("SET_PRINT_USED_EXTRUDERS EXTRUDERS=1,3", script)
        self.assertIn("BED_LEVEL=0 FLOW_CALIBRATE=0 TIME_LAPSE_CAMERA=0 AUTO_REPLENISH_FILAMENT=1", script)
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

    def test_busy_or_toolhead_change_during_the_upload_starts_nothing(self):
        real = self.client.upload
        for change, why in ((lambda: setattr(self.fake, "state", "printing"), "busy"),
                            (lambda: self.fake.task["filament_type"].__setitem__(3, "PETG"), "T4 changed")):
            with self.subTest(why=why):
                self.fake.state, self.fake.task, self.fake.order[:] = "standby", fakes.task_config(), []

                def upload(*a, **kw):
                    real(*a, **kw)
                    change()
                self.client.upload = upload
                with self.assertRaisesRegex(agent.JobError, why):
                    self.run_job()
                self.assertEqual([k for k, _ in self.fake.order], ["upload"])   # no options, no start
                self.assertEqual(os.listdir(self.work), [])

    def test_cancel_after_the_options_starts_nothing(self):
        with self.assertRaises(agent.Cancelled):
            self.run_job(cancelled=lambda: bool(self.fake.scripts))
        self.assertEqual([k for k, _ in self.fake.order], ["upload", "gcode"])
        self.assertEqual(self.fake.started, [])

    def test_send_refuses_the_name_being_printed(self):
        self.fake.state = "printing"                                 # FakePrinter prints a.gcode
        with self.assertRaisesRegex(agent.JobError, "printing a.gcode"):
            agent.send_job(self.client, self.path, "a", 1, OPTIONS, "0.10.0", self.work)
        self.assertEqual(self.fake.order, [])
        self.assertEqual(agent.send_job(self.client, self.path, "b", 1, OPTIONS, "0.10.0", self.work), "b.gcode")

    def test_sweep_removes_only_stale_job_files(self):
        for name in ("job-0a1b.gcode", "job-ff.gcode", "keep.gcode", "job-x.txt"):
            open(os.path.join(self.work, name), "w").close()
        self.assertEqual(agent.sweep_jobs(self.work), 2)
        self.assertEqual(sorted(os.listdir(self.work)), ["job-x.txt", "keep.gcode"])
        self.assertEqual(agent.sweep_jobs(os.path.join(self.work, "missing")), 0)

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
        self.addCleanup(self.agent.on_unload)
        fd, self.path = tempfile.mkstemp(suffix=".gcode")
        with os.fdopen(fd, "w", newline="") as f:
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

    def test_printer_origin_is_asked_once_at_load(self):
        # GitHub #48: one scheme://host grant (every port and path) instead of one runtime prompt per URL.
        # Presets are never read at load (see test_no_preset_read_until_loaded): the origins come from the settings
        # and from the printers U1 Control already used, remembered in the settings store.
        storage = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, storage, ignore_errors=True)
        orca = fakes.install_orca(storage=storage)
        ns = fakes.load_wheel(self.artifact)
        ns["U1Control"]().register_capabilities()
        self.assertEqual(orca.permission_requests[-1]["network_http"], [])
        ns["remember_origins"](ns["get_store"](None), "https://U1.example.com:8443/u1/", "http://box:7912", "")
        orca = fakes.install_orca(storage=storage)
        fakes.load_wheel(self.artifact)["U1Control"]().register_capabilities()
        self.assertEqual(orca.permission_requests[-1]["network_http"], ["https://u1.example.com", "http://box"])
        self.assertTrue(orca.permission_requests[-1]["threading"])

    def test_raising_queued_callback_is_caught(self):
        """A callback queued to OrcaSlicer's UI thread that raises must not escape: OnExceptionInMainLoop would end
        OrcaSlicer."""
        queued, logged = [], []
        self.agent.set_queue_on_main_fn(queued.append)

        def boom(*args):
            raise RuntimeError("host gone")
        self.agent.set_on_printer_connected_fn(boom)
        self.agent._emit("printer_connected", "dev")
        old_log, self.ns["log"] = self.ns["log"], logged.append
        try:
            queued[0]()   # what OrcaSlicer's CallAfter runs later: must return normally
        finally:
            self.ns["log"] = old_log
        self.assertEqual(len(logged), 1)
        self.assertIn("printer_connected", logged[0])
        self.assertIn("host gone", logged[0])

    def test_no_preset_read_until_loaded(self):
        """OrcaSlicer 2.5.1 crashed (SIGSEGV in PresetBundle::full_fff_config on the plugin load thread, under
        PythonPluginBridge::finalize_plugin_capture) when a plugin read presets while the UI thread was still
        loading them. Nothing preset-related may run at import, class definition, capability construction,
        register_capabilities or on_load."""
        touched = []

        def guard(name):
            def call(*a, **k):
                touched.append(name)
                raise AssertionError("orca.host.%s read during plugin load" % name)
            return call
        orca = fakes.install_orca()
        orca.host.preset_bundle = guard("preset_bundle")
        orca.host.preset = type("Guard", (), {"__getattr__": lambda self, n: guard("preset." + n)()})()
        orca.registered.clear()
        ns = fakes.load_wheel(self.artifact)   # import and class definitions
        ns["U1Control"]().register_capabilities()
        for cls in list(orca.registered):
            cap = cls()
            if hasattr(cap, "on_load"):
                cap.on_load()
                self.addCleanup(cap.on_unload)
        self.assertEqual(touched, [])

    def test_default_settings_with_every_box_ticked(self):
        """OrcaSlicer's dialog starts every box ticked: U1 Control's defaults decide, time-lapse stays off."""
        p = self.params(task_bed_leveling=True, task_flow_cali=True, task_record_timelapse=True)
        self.assertEqual(self.agent.start_local_print(p, self.update, None), 0)
        self.assertIn("BED_LEVEL=1 FLOW_CALIBRATE=1 TIME_LAPSE_CAMERA=0", self.fake.scripts[-1])

    def test_unticked_box_wins_over_the_setting(self):
        # no print setup here: a remembered pop-up answer would become the next print's setting
        self.ns["get_store"](self.agent).update({"mode": "expert", "print_dialog": False,
                                                 "prefs": {"bed_level": True, "flow_calibrate": True,
                                                           "time_lapse_camera": True}})
        p = self.params(task_bed_leveling=False, task_flow_cali=True, task_record_timelapse=False)
        self.assertEqual(self.agent.start_local_print(p, self.update, None), 0)
        self.assertIn("BED_LEVEL=0 FLOW_CALIBRATE=1 TIME_LAPSE_CAMERA=0", self.fake.scripts[-1])
        p = self.params(task_bed_leveling=True, task_flow_cali=True, task_record_timelapse=True)
        self.fake.order[:] = []
        self.assertEqual(self.agent.start_local_print(p, self.update, None), 0)
        self.assertIn("BED_LEVEL=1 FLOW_CALIBRATE=1 TIME_LAPSE_CAMERA=1", self.fake.scripts[-1])   # both on

    def test_print_from_the_dialog(self):
        self.ns["get_store"](self.agent).update({"spoolman_url": "http://spoolman.test:7912"})   # else nothing to book
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

    # U1 print setup after OrcaSlicer's Print dialog --------------------------------------------------------
    def answer(self, reply, submit=True):
        """The print setup window answers `reply` at once (or never, submit=False); returns the windows opened."""
        windows = []

        class Silent(fakes.FakeWindow):
            def __init__(self, on_message, on_submit, answer):
                self.on_message, self.on_submit, self.answer, self.open, self.posted = on_message, on_submit, answer, True, []
                on_message({"ready": True})

        def create(html, on_message=None, on_submit=None, **kw):
            w = (fakes.FakeWindow if submit else Silent)(on_message, on_submit, reply)
            w.html = html
            windows.append(w)
            return w
        self.orca.host.ui.create_window = create
        return windows

    def setting(self, **kw):
        self.ns["get_store"](self.agent).update({"mode": "expert", **kw})

    def test_print_setup_choice_is_what_is_sent(self):
        windows = self.answer({"map": {"0": 3, "1": 1}, "prefs": {"bed_level": False, "flow_calibrate": True},
                               "purifier": "auto", "acknowledged": [], "remember": False})
        p = self.params(task_bed_leveling=True, task_flow_cali=True)
        self.assertEqual(self.agent.start_local_print(p, self.update, lambda: False), 0)
        self.assertEqual(len(windows), 1)                                  # first print: auto shows it
        data = json.loads(re.search(r'id="u1-boot">(.*?)</script>', windows[0].html, re.S).group(1))["data"]
        self.assertEqual(data["map"], {"0": 0, "1": 1})                    # starts from OrcaSlicer's slots
        self.assertEqual(data["printer"]["busy"], False)
        self.assertTrue(data["remember"])
        script = self.fake.scripts[-1]
        self.assertIn("CONFIG_EXTRUDER=0 MAP_EXTRUDER=3", script)
        self.assertIn("BED_LEVEL=0 FLOW_CALIBRATE=1", script)
        self.assertEqual(self.ns["get_store"](self.agent).effective()["prefs"], {})   # not remembered

    def test_print_setup_remembers_when_ticked(self):
        self.answer({"map": {}, "prefs": {"bed_level": False}, "purifier": "auto", "remember": True})
        self.assertEqual(self.agent.start_local_print(self.params(task_bed_leveling=True), self.update, None), 0)
        self.assertIs(self.ns["get_store"](self.agent).effective()["prefs"]["bed_level"], False)

    def test_print_setup_setting_off_and_on(self):
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.setting(print_dialog=False)
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertEqual(windows, [])
        self.setting(print_dialog=True, printed_before=True)
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertEqual(len(windows), 1)

    def test_print_setup_cancel_sends_nothing(self):
        self.answer({"cancelled": True})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), self.ns["ERR_CANCELED"])
        self.assertEqual(self.fake.order, [])

    def test_print_setup_warnings_must_be_acknowledged(self):
        self.answer({"map": {"0": 2}, "prefs": {}, "purifier": "auto", "acknowledged": []})   # T3 is empty
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), self.ns["ERR_LP_PUBLISH"])
        self.assertIn("weren't confirmed", self.updates[-1][2])
        self.assertEqual(self.fake.order, [])
        self.answer({"map": {"0": 2}, "prefs": {}, "purifier": "auto", "acknowledged": ["empty:0:2"]})
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertIn("CONFIG_EXTRUDER=0 MAP_EXTRUDER=2", self.fake.scripts[-1])

    def test_busy_u1_is_refused_before_the_print_setup(self):
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})
        self.fake.state = "printing"
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), self.ns["ERR_LP_PUBLISH"])
        self.assertEqual((windows, self.fake.order), ([], []))

    def test_orcaslicer_cancel_closes_the_print_setup(self):
        windows = self.answer(None, submit=False)
        code = self.agent.start_local_print(self.params(), self.update, lambda: bool(windows))
        self.assertEqual(code, self.ns["ERR_CANCELED"])
        self.assertFalse(windows[0].open)
        self.assertEqual(self.fake.order, [])

    def test_print_setup_shows_linked_spool_names(self):
        windows = self.answer({"map": {}, "prefs": {}, "purifier": "auto"})

        class Svc:
            @staticmethod
            def spool_names(host):
                return {"1": {"name": "Acme Cobalt", "colour": "#2850A8"}}
            target = None
        self.ns["_service"] = Svc()
        self.addCleanup(self.ns.__setitem__, "_service", None)
        self.assertEqual(self.agent.start_local_print(self.params(), self.update, None), 0)
        self.assertIn('"spools": {"1": {"name": "Acme Cobalt", "colour": "#2850A8"}}', windows[0].html)

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

    def test_linked_toolhead_reports_its_spooler_preset_id(self):
        """OrcaSlicer's sync from AMS matches presets on tray_info_idx: a toolhead linked to a Spoolman spool carries
        the SPL id of the spool's standalone Spooler preset (per spool here, from profiles.json); the others the
        Generic id of their material. The links come from Spoolman at connect, without the tab."""
        import threading
        import types
        name = "_local/spooler/Acme PLA #5 @Snapmaker U1"
        mine = {"name": name, "bundle_id": "spooler", "vendor": "Acme", "colour": "#00FF00"}
        self.ns["filament_catalog"] = lambda: ([mine], "Snapmaker U1")
        profiles = {"version": 1, "filaments": {}, "spools": {"5": {"Snapmaker U1": name}}, "ids": {name: "SPL00000005AA"}}
        self.ns["spooler_bridge"].read_json = lambda folder, name: profiles   # the wheel's own module object
        spool = {"id": 5, "location": "U1 T1", "filament": {"id": 9, "vendor": {"name": "Acme"}, "material": "PLA",
                                                              "color_hex": "FF0000"},
                 "extra": {"orca_filament_preset": '"My PLA"'}}
        self.ns["user_presets"] = lambda: 1 / 0   # OrcaSlicer won't list user presets: the link is ignored
        seen = []

        class FakeSpoolman:
            def __init__(self, url, client):
                seen.append((url, client is not None))

            def connect(self):
                return {}

            def spools(self):
                return [spool]
        self.ns["sm"].Spoolman = FakeSpoolman
        self.ns["get_store"](self.agent).update({"printer_name": "U1", "spoolman_url": "http://sm:7912"})
        messages = []
        self.agent.set_on_local_message_fn(lambda dev, text: messages.append(json.loads(text)))
        self.agent.set_queue_on_main_fn(lambda task: task())
        self.connect()
        self.assertTrue(wait_for(lambda: self.agent._links[1]))
        self.assertEqual(seen[0], ("http://sm:7912", True))
        messages.clear()
        self.agent._wake.set()
        self.assertTrue(wait_for(lambda: messages))
        trays = messages[-1]["print"]["ams"][0]["tray"]
        self.assertEqual((trays[0]["tray_type"], trays[0]["tray_info_idx"]), ("PLA", "SPL00000005AA"))
        self.assertEqual((trays[1]["tray_type"], trays[1]["tray_info_idx"]), ("PETG", "OFYPdQJh"))
        self.ns["_service"] = types.SimpleNamespace(   # the tab showing this U1 wins: its links are up to date
            lock=threading.RLock(), target=types.SimpleNamespace(host="http://%s/" % self.fake.host.split(":")[0]),
            spools=[{"id": 5, "filament_id": 9}], bindings={2: 5})
        self.assertEqual(list(self.agent._bound_spools()), [2])
        self.ns["_service"].target.host = "10.9.9.9"   # another U1 in the tab: the agent's own links
        self.assertEqual(list(self.agent._bound_spools()), [0])

    def test_toolhead_linked_to_a_standalone_user_preset_reports_its_id(self):
        """orca_filament_preset naming a standalone user preset: its filament_id (from its file), which OrcaSlicer's
        sync from AMS loads. One that inherits has its parent's id, so the sync can't load it: the usual id. Presets
        are read on OrcaSlicer's UI thread only (here: the test's main thread, or a queue_on_main task)."""
        import threading
        folder = tempfile.mkdtemp()
        standalone = os.path.join(folder, "My PLA.json")
        with open(standalone, "w", encoding="utf-8") as f:
            json.dump({"name": "My PLA", "inherits": "", "filament_id": "P1a2b3c"}, f)
        mine = [{"name": "My PLA", "file": standalone, "inherits": ""},
                {"name": "Child PETG", "file": standalone, "inherits": "Generic PETG @System"}]
        queued, off_ui = [], []

        def user_presets():
            if threading.current_thread() is not threading.main_thread() and not queued:
                off_ui.append(threading.current_thread().name)
            return mine
        self.ns["user_presets"] = user_presets
        self.ns["filament_catalog"] = lambda: ([], "Snapmaker U1")
        self.ns["spooler_bridge"].read_json = lambda folder, name: {}

        def extra(name):
            return {"orca_filament_preset": json.dumps(name)}
        spools = [{"id": 5, "location": "U1 T1", "extra": extra("my pla"), "filament": {"id": 1, "material": "PLA"}},
                  {"id": 6, "location": "U1 T2", "filament": {"id": 2, "material": "PETG", "extra": extra("Child PETG")}},
                  {"id": 7, "location": "U1 T4", "extra": extra("Ghost"), "filament": {"id": 3, "material": "PLA"}}]

        class FakeSpoolman:
            def __init__(self, url, client):
                pass

            def connect(self):
                return {}

            def spools(self):
                return spools
        self.ns["sm"].Spoolman = FakeSpoolman
        self.ns["get_store"](self.agent).update({"printer_name": "U1", "spoolman_url": "http://sm:7912"})
        messages = []
        self.agent.set_on_local_message_fn(lambda dev, text: messages.append(json.loads(text)))
        self.agent.set_queue_on_main_fn(lambda task: (queued.append(1), task(), queued.pop()))
        self.connect()
        self.assertTrue(wait_for(lambda: self.agent._links[1]))
        messages.clear()
        self.agent._wake.set()
        self.assertTrue(wait_for(lambda: messages))
        trays = messages[-1]["print"]["ams"][0]["tray"]
        self.assertEqual([t["tray_info_idx"] for t in trays], ["P1a2b3c", "OFYPdQJh", "", "OFmY0l6t"])
        self.assertEqual(off_ui, [])
        ghost = [n for n in self.orca.notifications if '"Ghost"' in n]   # AMS sync says it too, once per name
        self.assertEqual(len(ghost), 1)
        self.assertIn("T4: no compatible user preset", ghost[0])
        self.agent._wake.set()
        self.assertTrue(wait_for(lambda: len(messages) > 1))
        self.assertEqual(len([n for n in self.orca.notifications if '"Ghost"' in n]), 1)

    def connect(self, **kw):
        conn = self.orca.printer_agent.PrinterConnectionParams(**{"dev_id": "u1", "host": self.fake.host, **kw})
        self.assertEqual(self.agent.connect_printer(conn), 0)
        self.assertTrue(wait_for(lambda: self.agent.view is not None))

    def test_device_commands_run_in_order_on_one_worker(self):
        self.connect()
        lines = ["M117 %d" % i for i in range(8)]
        workers = set()
        for i, line in enumerate(lines):
            msg = json.dumps({"print": {"command": "gcode_line", "param": line, "sequence_id": str(i)}})
            self.assertEqual(self.agent.send_message_to_printer("u1", msg, 0, 0), 0)
            workers.add(self.agent._worker)
        self.assertTrue(wait_for(lambda: len(self.fake.scripts) >= len(lines)))
        self.assertEqual(self.fake.scripts, lines)                    # in the order sent
        worker, = workers                                             # one worker for all of them
        self.agent.on_unload()
        worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_stop_is_sent_at_once_while_a_long_gcode_line_runs(self):
        import threading
        self.fake.hold = threading.Event()
        self.addCleanup(self.fake.hold.set)
        self.connect()
        heat = json.dumps({"print": {"command": "gcode_line", "param": "M109 S220", "sequence_id": "1"}})
        light = json.dumps({"system": {"command": "ledctrl", "led_node": "chamber_light", "led_mode": "on"}})
        self.agent.send_message_to_printer("u1", heat, 0, 0)
        self.agent.send_message_to_printer("u1", light, 0, 0)          # queued behind M109
        for kind in ("pause", "resume", "stop"):
            self.assertEqual(self.agent.send_message_to_printer("u1", json.dumps({"print": {"command": kind}}), 0, 0), 0)
        self.assertTrue(wait_for(lambda: [k for k, _ in self.fake.order if k in ("pause", "resume", "cancel")]
                                 and ("cancel", None) in self.fake.order))
        self.assertEqual(self.fake.scripts, [])                         # M109 and the light still waiting
        self.fake.hold.set()
        self.assertTrue(wait_for(lambda: self.fake.scripts == ["M109 S220", agent.LIGHT_ON]))

    def test_queued_commands_never_reach_the_old_printer(self):
        import threading
        self.fake.hold = threading.Event()
        self.addCleanup(self.fake.hold.set)
        self.connect()
        heat = json.dumps({"print": {"command": "gcode_line", "param": "M109 S220", "sequence_id": "1"}})
        late = json.dumps({"print": {"command": "gcode_line", "param": "M117 late", "sequence_id": "2"}})
        self.agent.send_message_to_printer("u1", heat, 0, 0)
        self.assertTrue(wait_for(lambda: self.agent._commands.empty()))   # M109 taken, waiting on the printer
        self.agent.send_message_to_printer("u1", late, 0, 0)
        old = self.agent.client
        self.agent.disconnect_printer()
        self.assertTrue(self.agent._commands.empty())                   # dropped at disconnect
        self.agent._commands.put((old, {"kind": "gcode", "script": "M117 stale", "seq": "3"}))   # a race's leftover
        self.fake.hold.set()
        self.assertTrue(wait_for(lambda: self.agent._commands.empty()))
        self.agent._commands.put(None)
        self.agent._worker.join(5)
        self.assertEqual(self.fake.scripts, ["M109 S220"])              # only what was already running

    def test_connect_switches_printer_in_one_locked_step(self):
        """Every state a reader can see under the lock is all old printer or all new: id, host, key, client, stop."""
        import threading
        self.connect()
        old_stop = self.agent._stop
        seen, agent_ = [], self.agent

        class Recording:
            def __init__(self):
                self.lock = threading.Lock()

            def snap(self):
                seen.append((agent_.dev_id, agent_.host, agent_.api_key, agent_._stop is old_stop))

            def __enter__(self):
                self.lock.acquire()
                self.snap()

            def __exit__(self, *exc):
                self.snap()
                self.lock.release()
        self.agent._lock = Recording()
        conn = self.orca.printer_agent.PrinterConnectionParams(dev_id="u1-b", host="127.0.0.1:1", password="k2")
        self.assertEqual(self.agent.connect_printer(conn), 0)
        self.agent.disconnect_printer()
        old = ("u1", self.fake.host, "")   # what connect() set: dev_id "u1", no key
        for dev_id, host, key, same_stop in seen:
            state = (dev_id, host, key)
            self.assertIn(state, (old, ("u1-b", "127.0.0.1:1", "k2")), seen)
            if state == old:
                continue
            self.assertFalse(same_stop, "new printer seen with the old printer's stop event: %r" % (seen,))
        self.assertIn(("u1-b", "127.0.0.1:1", "k2", False), seen)

    def test_device_gcode_waits_like_the_console(self):
        seen = []
        client = type("C", (), {"gcode": lambda self, script, timeout=30: seen.append(timeout)})()
        self.agent._run_command(client, {"kind": "gcode", "script": "G28", "seq": "1"})
        self.assertEqual(seen, [600])

    def test_port_and_ssl_as_orcaslicer_gives_them(self):
        base_url = self.ns["base_url"]
        self.assertEqual(base_url("10.0.0.5", "7125", False), "http://10.0.0.5:7125")
        self.assertEqual(base_url("10.0.0.5", "", True), "https://10.0.0.5")
        self.assertEqual(base_url("http://10.0.0.5:80/", "7125"), "http://10.0.0.5:80")   # a port in the host wins
        self.assertEqual(base_url("https://u1.example.com/u1/", "", False), "https://u1.example.com/u1")   # a proxy
        self.assertEqual(base_url("u1.example.com/u1", "8443", True), "https://u1.example.com:8443/u1")
        host, port = self.fake.host.split(":")
        self.connect(host=host, port=port)
        self.assertEqual(self.agent.base, "http://" + self.fake.host)
        self.assertEqual(self.agent.client.candidates, ["http://" + self.fake.host])

    def test_poll_resets_firmware_and_drops_a_stale_view(self):
        self.agent.firmware = "old printer"
        self.connect()
        self.assertTrue(wait_for(lambda: self.agent.firmware == self.fake.version))
        self.fake.close()                                             # the U1 stops answering
        self.assertTrue(wait_for(lambda: self.agent.view is None, timeout=15))

    def test_poll_answer_after_disconnect_is_dropped(self):
        import threading
        stop = threading.Event()

        class Late:   # answers only after the agent was disconnected
            def info(self):
                return {}

            def query(self, objects):
                stop.set()
                return fakes.FakePrinter.status(self_fake)
        self_fake = self.fake
        self.agent._poll(stop, Late())
        self.assertIsNone(self.agent.view)

    def test_poll_firmware_answer_after_disconnect_is_dropped(self):
        import threading
        stop = threading.Event()

        class Late:
            def info(self):
                stop.set()   # the agent was disconnected while this answer was on its way
                return {"software_version": "old printer"}

            def query(self, objects):
                raise AssertionError("no status query after the disconnect")
        self.agent.firmware = ""
        self.agent._poll(stop, Late())
        self.assertEqual(self.agent.firmware, "")

    def test_stale_work_files_are_swept_on_load(self):
        work = os.path.join(self.ns["_storage"](), "jobs")
        os.makedirs(work, exist_ok=True)
        open(os.path.join(work, "job-abc123.gcode"), "w").close()
        self.agent.on_load()
        self.assertEqual(os.listdir(work), [])

    def test_send_refuses_the_running_file(self):
        self.fake.state = "printing"
        code = self.agent.start_send_gcode_to_sdcard(self.params(project_name="a"), self.update, None, None)
        self.assertEqual(code, self.ns["ERR_SG_UPLOAD"])
        self.assertIn("printing a.gcode", self.updates[-1][2])
        self.assertEqual(self.fake.uploads, {})

    def test_commands_need_a_connection(self):
        pause = json.dumps({"print": {"command": "pause"}})
        self.assertEqual(self.agent.send_message_to_printer("u1", pause, 0, 0), self.ns["ERR_CONNECT"])


def bridge_preset(name, vendor="Generic", colour="#FF0000"):
    return {"name": sb.NAME_PREFIX + name, "bundle_id": sb.BUNDLE_ID, "compatible_printers": ["Snapmaker U1"],
            "colour": colour, "vendor": vendor}


class TrayIdTests(unittest.TestCase):
    """tray_filament_id: the SPL id of a linked spool's standalone Spooler preset, from profiles.json "ids"."""
    LABEL = "Snapmaker U1"
    SPOOL = {"id": 12, "filament_id": 7, "vendor": "SUNLU", "material": "PLA", "colour": "#101010"}
    MATTE = "SUNLU PLA Matte Black @Snapmaker U1"

    def presets(self, *names):
        return [bridge_preset(n, vendor="SUNLU", colour="#101010") for n in names]

    def test_linked_spool_reports_its_spooler_preset_id(self):
        profiles = {"version": 1, "filaments": {"7": {self.LABEL: "_local/spooler/" + self.MATTE}},
                    "ids": {"_local/spooler/" + self.MATTE: "SPLAAAA000001"}}
        self.assertEqual(sb.tray_filament_id(self.SPOOL, self.presets(self.MATTE), profiles, self.LABEL), "SPLAAAA000001")
        by_colour = {"version": 1, "filaments": {}, "ids": profiles["ids"]}   # not listed: same vendor, material, colour
        self.assertEqual(sb.tray_filament_id(self.SPOOL, self.presets(self.MATTE), by_colour, self.LABEL), "SPLAAAA000001")

    def test_per_spool_preset_wins_over_the_filament_one(self):
        three, twelve = "SUNLU PLA #3 @Snapmaker U1", "SUNLU PLA #12 @Snapmaker U1"
        profiles = {"version": 1, "filaments": {"7": {self.LABEL: "_local/spooler/" + three}},
                    "spools": {"12": {self.LABEL: "_local/spooler/" + twelve}, "3": {self.LABEL: "_local/spooler/" + three}},
                    "ids": {"_local/spooler/" + three: "SPL0000000003", "_local/spooler/" + twelve: "SPL0000000012"}}
        self.assertEqual(sb.profile_lookup(profiles, 7, self.LABEL, 12), "_local/spooler/" + twelve)
        self.assertEqual(sb.profile_lookup(profiles, 7, self.LABEL, 99), "_local/spooler/" + three)
        presets = self.presets(three, twelve)
        self.assertEqual(sb.tray_filament_id(self.SPOOL, presets, profiles, self.LABEL), "SPL0000000012")
        self.assertEqual(sb.tray_filament_id({**self.SPOOL, "id": 3}, presets, profiles, self.LABEL), "SPL0000000003")

    def test_no_id_leaves_it_to_the_generic_preset(self):
        listed = {"version": 1, "filaments": {"7": {self.LABEL: "_local/spooler/" + self.MATTE}}}
        presets = self.presets(self.MATTE)
        self.assertEqual(sb.tray_filament_id(self.SPOOL, presets, listed, self.LABEL), "")   # an inheriting preset
        self.assertEqual(sb.tray_filament_id(self.SPOOL, presets, None, self.LABEL), "")     # no profiles.json
        self.assertEqual(sb.tray_filament_id(None, presets, listed), "")                     # nothing linked
        ids = {**listed, "ids": {"_local/spooler/" + self.MATTE: "SPLAAAA000001"}}
        self.assertEqual(sb.tray_filament_id({**self.SPOOL, "id": 1, "filament_id": 1, "material": "ASA"}, presets, ids), "")


if __name__ == "__main__":
    unittest.main()
