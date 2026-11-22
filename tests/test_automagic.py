"""Automagic/Expert settings, print dialog rules, auto-add pipeline, Spooler interop."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import settings  # noqa: E402
import spooler_bridge as sb  # noqa: E402
import u1  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import SAMPLE, wait_for  # noqa: E402


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


class SettingsTests(unittest.TestCase):
    def store(self):
        d = tempfile.mkdtemp()
        return settings.Store(os.path.join(d, "settings.json")), d

    def test_modes(self):
        st, d = self.store()
        eff = st.effective()
        self.assertEqual((eff["mode"], eff["print_dialog"], eff["printer_name"]), ("automagic", True, "Snapmaker U1"))
        st.update({"print_dialog": False, "chamber_wait": False, "host": "1.2.3.4", "bogus": 1, "purifier": "nope"})
        eff = st.effective()
        self.assertEqual((eff["print_dialog"], eff["chamber_wait"], eff["host"]), (True, True, "1.2.3.4"))  # ignored
        st.update({"mode": "expert"})
        eff = st.effective()
        self.assertEqual((eff["print_dialog"], eff["chamber_wait"], eff["purifier"]), (False, False, "auto"))
        self.assertEqual(settings.Store(os.path.join(d, "settings.json")).effective(), eff)  # persisted

    def test_camera_fps(self):
        """Live camera rate: 5 fps by default, the same in both modes, only the offered rates are kept."""
        st, d = self.store()
        self.assertEqual(st.effective()["camera_fps"], 5)
        for bad in (60, 0, True, 30.0, "30", None):
            self.assertEqual(st.update({"camera_fps": bad})["camera_fps"], 5, bad)
        self.assertEqual(st.update({"camera_fps": 30})["camera_fps"], 30)
        self.assertEqual(st.update({"mode": "expert"})["camera_fps"], 30)
        write(os.path.join(d, "settings.json"), json.dumps({"camera_fps": 60}))
        self.assertEqual(settings.Store(os.path.join(d, "settings.json")).effective()["camera_fps"], 5)  # hand-edited

    def test_ui_theme(self):
        """Settings > Appearance: auto by default, only auto/light/dark are kept."""
        st, d = self.store()
        self.assertEqual(st.effective()["ui_theme"], "auto")
        self.assertEqual(st.update({"ui_theme": "dark"})["ui_theme"], "dark")
        for bad in ("purple", True, None, 1):
            self.assertEqual(st.update({"ui_theme": bad})["ui_theme"], "dark", bad)
        self.assertEqual(settings.Store(os.path.join(d, "settings.json")).effective()["ui_theme"], "dark")  # persisted
        write(os.path.join(d, "settings.json"), json.dumps({"ui_theme": "neon"}))
        self.assertEqual(settings.Store(os.path.join(d, "settings.json")).effective()["ui_theme"], "auto")  # hand-edited

    def test_callable_backend(self):
        box = {}
        st = settings.Store(load=lambda: box.get("t", "{}"), save=lambda t: box.update(t=t))
        st.update({"mode": "expert"})
        self.assertEqual(settings.Store(load=lambda: box["t"]).effective()["mode"], "expert")

    def test_strings(self):
        self.assertEqual(settings.with_pipeline(""), '"U1 print setup"')
        self.assertEqual(settings.with_pipeline("Other"), 'Other;"U1 print setup"')
        self.assertEqual(settings.with_pipeline(["Other"]), 'Other;"U1 print setup"')
        self.assertIsNone(settings.with_pipeline('"U1 print setup"'))
        self.assertEqual(settings.parse_strings('a;"b c";"d\\"e"'), ["a", "b c", 'd"e'])


class PluginBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=__import__("pathlib").Path(tempfile.mkdtemp())))

    def load(self, **kw):
        orca = fakes.install_orca(**kw)
        return orca, fakes.load_wheel(self.artifact)


class PipelineTests(PluginBase):
    def page(self, preset, **kw):
        orca, ns = self.load(preset={"name": "Snapmaker U1 (0.4 nozzle)", "printer_model": "Snapmaker U1", **preset}, **kw)
        return orca, ns, ns["U1ControlPage"]()

    def test_adds_once_per_preset(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": ["Other"]})
        self.assertEqual(ns["ensure_pipeline"](page._config()), "Snapmaker U1 (0.4 nozzle)")
        self.assertEqual(orca.process_calls[0][1], {"slicing_pipeline_plugin": 'Other;"U1 print setup"'})
        self.assertIn("save the preset", orca.notifications[0])
        self.assertIsNone(ns["ensure_pipeline"](page._config()))  # guard
        self.assertEqual(len(orca.process_calls), 1)

    def test_printer_preset_gets_u1_controls_address_so_print_is_offered(self):
        """OrcaSlicer greys out Print (only Export G-code) while the printer preset has no print_host; the address
        typed in U1 Control's Settings fills it once, unsaved like the pipeline step."""
        orca, ns, page = self.page({"slicing_pipeline_plugin": '"U1 print setup"'})
        page._settings().update({"host": "192.168.1.5", "api_key": "k"})
        page._auto_pipeline()
        self.assertTrue(wait_for(lambda: orca.printer_calls))
        self.assertEqual(orca.printer_calls, [{"print_host": "192.168.1.5", "printhost_apikey": "k"}])
        self.assertTrue(wait_for(lambda: any("Print button" in m.get("text", "") for m in page.posted)))
        page._auto_pipeline()   # filled now: nothing more
        time.sleep(0.2)
        self.assertEqual(len(orca.printer_calls), 1)

    def test_preset_address_is_left_alone_when_set_or_adding_is_off(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": '"U1 print setup"', "print_host": "192.168.1.9"})
        page._settings().update({"host": "192.168.1.5"})
        self.assertIsNone(ns["host_plan"](page._config()))
        orca, ns, page = self.page({"slicing_pipeline_plugin": '"U1 print setup"'})
        page._settings().update({"host": "192.168.1.5", "mode": "expert", "auto_add_pipeline": False})
        page._auto_pipeline()
        self.assertTrue(wait_for(lambda: any("Wi-Fi icon" in m.get("text", "") for m in page.posted)))
        self.assertEqual(orca.printer_calls, [])

    def test_config_says_whether_the_preset_runs_print_setup(self):
        _, _, page = self.page({"slicing_pipeline_plugin": ["Other"], "name": "My process"})
        self.assertEqual(page._config_message()["pipeline"], {"preset": "My process", "on": False})
        _, _, page = self.page({"slicing_pipeline_plugin": 'Other;"U1 print setup"', "name": "My process"})
        self.assertEqual(page._config_message()["pipeline"], {"preset": "My process", "on": True})
        _, _, page = self.page({"printer_model": "Voron 2.4", "name": "Voron", "slicing_pipeline_plugin": ""})
        self.assertIsNone(page._config_message()["pipeline"])   # not a U1: nothing to say

    def test_config_is_sent_even_when_another_preset_edit_holds_the_lock(self):
        _, ns, page = self.page({"slicing_pipeline_plugin": 'Other;"U1 print setup"', "name": "Now selected"})
        lock = ns["_presets_lock"]
        self.assertTrue(lock.acquire(blocking=False))
        try:
            page._auto_pipeline()
        finally:
            lock.release()
        configs = [m for m in getattr(page, "posted", []) if m["type"] == "config"]
        self.assertEqual(configs[-1]["pipeline"], {"preset": "Now selected", "on": True})

    def test_presets_are_read_on_the_ui_thread_and_written_off_it(self):
        """_auto_pipeline runs on the UI thread (page messages, lifecycle events): it reads the presets there and
        only the write (begin_update, which blocks until the UI thread applies it) runs on a plugin thread."""
        import threading
        orca, ns, page = self.page({"slicing_pipeline_plugin": ["Other"], "name": "My process"})
        readers, real = [], orca.host.preset_bundle

        def bundle():
            readers.append(threading.current_thread().name)
            return real()
        orca.host.preset_bundle = bundle
        page._auto_pipeline()
        self.assertTrue(wait_for(lambda: any(m["type"] == "config" for m in getattr(page, "posted", []))))
        self.assertEqual(len(orca.process_calls), 1)
        self.assertTrue(readers)
        self.assertEqual(set(readers), {threading.current_thread().name})
        config = [m for m in page.posted if m["type"] == "config"][-1]
        self.assertEqual(config["pipeline"], {"preset": "My process", "on": True})

    def test_busy_lock_leaves_the_preset_to_offer_again(self):
        _, ns, page = self.page({"slicing_pipeline_plugin": ["Other"], "name": "My process"})
        lock = ns["_presets_lock"]
        self.assertTrue(lock.acquire(blocking=False))
        try:
            page._auto_pipeline()
        finally:
            lock.release()
        self.assertEqual(ns["ensure_pipeline"](page._config()), "My process")

    def off_main(self, fn):
        """fn() on a worker thread, as OrcaSlicer runs scripts and preset jobs; its result or exception."""
        import threading
        box = {}

        def run():
            try:
                box["value"] = fn()
            except BaseException as e:
                box["error"] = e
        t = threading.Thread(target=run, name="worker")
        t.start()
        t.join(10)
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def with_ui_queue(self, orca, ns):
        """queue_on_main that runs tasks on a thread named "ui"; records the thread of every preset read and write."""
        import threading
        seen = []

        def queue(task):
            threading.Thread(target=task, name="ui").start()
        ns["U1Agent"]().set_queue_on_main_fn(queue)
        self.addCleanup(ns.__setitem__, "_queue_on_main", None)
        real_bundle, filament, process = orca.host.preset_bundle, orca.host.preset.filament, orca.host.preset.process

        def bundle():
            seen.append(("read", threading.current_thread().name))
            return real_bundle()

        def update(real):
            def begin(*a):
                seen.append(("write", threading.current_thread().name))
                return real(*a)
            return begin
        orca.host.preset_bundle = bundle
        filament.begin_update, process.begin_update = update(filament.begin_update), update(process.begin_update)
        return seen

    def test_scripts_read_presets_on_the_ui_thread(self):
        """Scripts run on a worker thread: on_ui_thread has queue_on_main run the read on the UI thread and waits."""
        import threading
        orca, ns, _ = self.page({})
        self.with_ui_queue(orca, ns)
        ran = []
        self.assertEqual(self.off_main(lambda: ns["on_ui_thread"](lambda: ran.append(threading.current_thread().name) or 7)), 7)
        self.assertEqual(ran, ["ui"])
        self.assertEqual(ns["on_ui_thread"](lambda: threading.current_thread().name), threading.current_thread().name)  # on it already

        def no_address():
            raise ValueError("no address")
        with self.assertRaises(ValueError):
            self.off_main(lambda: ns["on_ui_thread"](no_address))
        ns["_queue_on_main"], ns["UI_WAIT"] = (lambda task: None), 0.05   # the UI thread does not answer in time
        with self.assertRaises(TimeoutError):
            self.off_main(lambda: ns["on_ui_thread"](lambda: 1))

    def test_sync_project_reads_on_the_ui_thread_and_writes_off_it(self):
        meta = {"Generic PLA @Snapmaker U1": {"default_filament_colour": ["#0000FF"]}}
        orca, ns = self.load(filament_names=list(meta), filament_meta=meta)
        seen = self.with_ui_queue(orca, ns)
        heads = [{"index": 0, "loaded": True, "type": "PLA", "vendor": "Generic", "colour": "#0000FF", "sub_type": ""}]
        spool = {"id": 5, "filament_id": 1, "vendor": "Generic", "material": "PLA", "name": "x", "colour": "#0000FF"}
        done, problems = self.off_main(lambda: ns["sync_project"](heads, [], {}, bound=lambda i: spool))
        self.assertEqual((len(done), problems), (1, []))
        self.assertEqual(sorted(set(seen)), [("read", "ui"), ("write", "worker")])

    def test_process_tuning_reads_on_the_ui_thread_and_writes_off_it(self):
        orca, ns, _ = self.page({"name": "0.20 Standard @Snapmaker U1", "wall_generator": "arachne"})
        seen = self.with_ui_queue(orca, ns)
        result = self.off_main(lambda: ns["ApplyForkTuning"]().execute())
        self.assertIn("Updated", result.message)
        self.assertEqual(sorted(set(seen)), [("read", "ui"), ("write", "worker")])

    def test_skips(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": '"U1 print setup"'})
        self.assertIsNone(ns["ensure_pipeline"](page._config()))
        orca, ns, page = self.page({"printer_model": "Bambu X1", "name": "X1C", "slicing_pipeline_plugin": ""})
        self.assertIsNone(ns["ensure_pipeline"](page._config()))
        orca, ns, page = self.page({"slicing_pipeline_plugin": ""})
        page._settings().update({"auto_add_pipeline": False, "mode": "expert"})
        self.assertIsNone(ns["ensure_pipeline"](page._config()))
        self.assertEqual(orca.process_calls, [])

    def test_lifecycle_and_failure(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": ""})
        ctx = type("C", (), {"msg": "print", "name": "0.20"})()
        page.on_lifecycle_event(orca.LifecycleEvent.PresetSelected, ctx)
        self.assertTrue(wait_for(lambda: len(orca.process_calls) == 1))
        orca.host.preset.process.begin_update = lambda n: (_ for _ in ()).throw(RuntimeError("busy"))
        orca2, ns2, page2 = self.page({"slicing_pipeline_plugin": ""})
        orca2.host.preset.process.begin_update = orca.host.preset.process.begin_update
        page2.on_lifecycle_event(orca2.LifecycleEvent.ProjectOpened, ctx)  # logged, no raise
        time.sleep(0.3)
        self.assertEqual(orca2.process_calls, [])

    def test_hello_config_message(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": ""})
        msg = page._config_message()
        self.assertEqual(msg["mode"], "automagic")
        self.assertTrue(any(a["key"] == "print_dialog" and a["choices"] is None for a in msg["automations"]))
        self.assertFalse(msg["spooler"]["installed"])
        page.on_message({"type": "save_settings", "settings": {"spooler_hint_dismissed": True, "api_key": "••••", "host": "127.0.0.1:1"}})
        config = [m for m in page.posted if m["type"] == "config"][-1]
        self.assertTrue(config["spooler"]["dismissed"])
        self.assertTrue(wait_for(lambda: any("U1 print setup added" in m.get("text", "") for m in page.posted)))
        ns["service"]().close()

    def test_requirements_check_again_looks_for_spooler_again(self):
        orca, ns, page = self.page({"slicing_pipeline_plugin": ""})
        self.addCleanup(lambda: ns["service"]().close())
        page.on_message({"type": "requirements", "recheck": True})
        config = [m for m in page.posted if m["type"] == "config"]
        self.assertEqual(len(config), 1)
        self.assertFalse(config[0]["spooler"]["installed"])
        items = next(m for m in page.posted if m["type"] == "requirements")["items"]
        self.assertEqual(next(i for i in items if i["id"] == "spooler")["status"], "missing")
        self.assertFalse([m for m in page.posted if m["type"] == "cmd"])   # the printer is not touched

    def test_camera_fps_message_paces_frames(self):
        _, ns, page = self.page({"slicing_pipeline_plugin": ""})
        svc = ns["service"]()
        self.addCleanup(svc.close)
        self.assertAlmostEqual(svc.frame_interval, 0.2)
        page.on_message({"type": "camera_fps", "value": 30})
        self.assertAlmostEqual(svc.frame_interval, 1 / 30)
        self.assertEqual(page._config_message()["settings"]["camera_fps"], 30)
        page.on_message({"type": "camera_fps", "value": 120})   # not offered: the stored rate stays
        self.assertAlmostEqual(svc.frame_interval, 1 / 30)


class DialogFlowTests(PluginBase):
    def test_every_print_shows_the_setup(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        write(path, SAMPLE)
        ctx = type("X", (), dict(step="post", gcode_path=path, host="OctoPrint", output_name="p.gcode",
                                 config_value=lambda self, k: {"print_host": fake.host}.get(k, "")))()
        orca, ns = self.load(answer={"map": {}, "prefs": {}, "purifier": "auto"})
        cap = ns["U1PrintSetup"]()
        self.assertEqual(cap.execute(ctx).status, "success")
        self.assertEqual(len(orca.windows), 1)  # first print
        write(path, SAMPLE)
        fake.task["filament_type"] = ["PLA", "PETG", "NONE", "PLA"]
        self.assertEqual(cap.execute(ctx).status, "success")
        self.assertEqual(len(orca.windows), 2)   # shown before every print while the setting is on


class SpoolerTests(PluginBase):
    def meta(self, name, colour="#FF0000", vendor="Elegoo", printers=("Snapmaker U1 (0.4 nozzle)",)):
        return {"name": name, "bundle_id": "spooler", "compatible_printers": list(printers), "colour": colour,
                "vendor": vendor}

    def test_detect(self):
        self.assertEqual(sb.detect([], [], False), {"installed": False, "presets": 0})
        self.assertTrue(sb.detect(["spooler"], [], False)["installed"])
        self.assertTrue(sb.detect([], [], True)["installed"])
        found = sb.detect([], [self.meta("a"), {"name": "b", "bundle_id": ""}])
        self.assertEqual(found, {"installed": True, "presets": 1})

    def test_presets_compat(self):
        a, b = self.meta("a"), self.meta("b", printers=("Other",))
        self.assertEqual(sb.spooler_presets([a, b, {"name": "x", "bundle_id": ""}], ("My U1", "Snapmaker U1 (0.4 nozzle)")), [a])
        self.assertEqual(len(sb.spooler_presets([a, b], ())), 2)  # unknown printer: lenient

    def test_nearest_colour_preference(self):
        spool = {"vendor": "Elegoo", "material": "PLA", "name": "Fire Red", "colour": "#FF0000"}
        presets = [self.meta("Elegoo PLA Fire Red @Snapmaker U1"), self.meta("Elegoo PLA Blue @Snapmaker U1", "#0000FF"),
                   self.meta("_local/spooler/Elegoo PLA Fire Red #4 @Snapmaker U1 0.6")]
        self.assertEqual(sb.preset_for_spool(presets, spool), "Elegoo PLA Fire Red @Snapmaker U1")
        near = {**spool, "name": "Other Red", "colour": "#F01010"}  # no such preset: nearest colour, same vendor+material
        self.assertEqual(sb.preset_for_spool(presets, near), "Elegoo PLA Fire Red @Snapmaker U1")
        self.assertIsNone(sb.preset_for_spool(presets, {**near, "vendor": "Nope"}))
        self.assertIsNone(sb.preset_for_spool(presets, {**near, "colour": "#00FF00"}))

    def test_profiles_json_lookup(self):
        presets = [self.meta("Elegoo PLA Fire Red @Snapmaker U1"), self.meta("Weird name @Snapmaker U1")]
        spool = {"filament_id": 12, "vendor": "Elegoo", "material": "PLA", "name": "Fire Red", "colour": "#FF0000"}
        profiles = {"version": 1, "filaments": {"12": {"Snapmaker U1": "_local/spooler/Weird name @Snapmaker U1"}}}
        self.assertEqual(sb.preset_for_spool(presets, spool, profiles, "Snapmaker U1"), "Weird name @Snapmaker U1")
        self.assertEqual(sb.preset_for_spool(presets, spool, profiles, "Other"), "Elegoo PLA Fire Red @Snapmaker U1")
        self.assertEqual(sb.preset_for_spool(presets, spool, {"filaments": {}}, "Snapmaker U1"),
                         "Elegoo PLA Fire Red @Snapmaker U1")
        longer = {"version": 1, "filaments": {"12": {"Snapmaker U1 0.4": "p"}}}
        self.assertEqual(sb.profile_lookup(longer, 12, "snapmaker u1"), "p")

    def test_files_and_marker(self):
        root = tempfile.mkdtemp()
        store = os.path.join(root, "OrcaSlicer", "orca_plugins", "plugin_data", "u1")
        os.makedirs(store)
        folder = sb.data_dir(store)
        self.assertEqual(folder, os.path.join(root, "OrcaSlicer", "spooler"))
        self.assertEqual(sb.data_dir("/nowhere/else"), "")
        self.assertIsNone(sb.read_json(folder, sb.PROFILES_FILE))  # missing
        os.makedirs(folder)
        write(os.path.join(folder, sb.PROFILES_FILE), "{not json")
        self.assertIsNone(sb.read_json(folder, sb.PROFILES_FILE))  # invalid
        write(os.path.join(folder, sb.PROFILES_FILE), '{"version": 1}')
        self.assertEqual(sb.read_json(folder, sb.PROFILES_FILE), {"version": 1})
        now = 1000.0
        self.assertTrue(sb.keep_slots_active({"active": True, "ts": now - 5}, now))
        self.assertFalse(sb.keep_slots_active({"active": True, "ts": now - 31}, now))
        self.assertFalse(sb.keep_slots_active({"active": False, "ts": now}, now))
        self.assertFalse(sb.keep_slots_active({"active": True}, now))
        self.assertFalse(sb.keep_slots_active(None, now))

    def test_sync_prefers_spooler_and_colour_tiebreak(self):
        meta = {"Generic PLA @Snapmaker U1": {"default_filament_colour": ["#0000FF"]},
                "Generic PLA Red @Snapmaker U1": {"default_filament_colour": ["#FF0000"], "bundle_id": "spooler",
                                                  "compatible_printers": ["Snapmaker U1 (0.4 nozzle)"]},
                "Elegoo PLA Fire @Snapmaker U1": {"default_filament_colour": ["#EE1111"], "bundle_id": "spooler",
                                                  "filament_vendor": ["Elegoo"],
                                                  "compatible_printers": ["Snapmaker U1 (0.4 nozzle)"]}}
        orca, ns = self.load(filament_names=list(meta), filament_meta=meta, bundle_ids=["spooler"])
        self.assertTrue(ns["spooler_state"]()["installed"])
        pick = ns["pick_filament_preset"]
        names = list(meta)
        colours = {n: m["default_filament_colour"][0] for n, m in meta.items()}
        head = {"type": "PLA", "vendor": "Generic", "colour": "#FF0000"}
        tie = ["Generic PLA @Snapmaker U1", "Generic PLA Red @Snapmaker U1"]
        self.assertEqual(pick(tie, head), "Generic PLA @Snapmaker U1")  # plain tie: shortest name
        self.assertEqual(pick(tie, head, colours=colours), "Generic PLA Red @Snapmaker U1")  # colour-aware
        heads = [{"index": 0, "loaded": True, "type": "PLA", "vendor": "Generic", "colour": "#0000FF", "sub_type": ""}]
        spool = {"id": 5, "filament_id": 1, "vendor": "Elegoo", "material": "PLA", "name": "Fire", "colour": "#EE1111"}
        ns["sync_project"](heads, [], {}, bound=lambda i: spool)
        self.assertEqual(orca.filament_calls[-1][1], "Elegoo PLA Fire @Snapmaker U1")  # Spooler preset of the bound spool
        ns["sync_project"](heads, [], {}, bound=lambda i: None)
        self.assertEqual(orca.filament_calls[-1][1], "Generic PLA @Snapmaker U1")  # fallback: scorer
        self.assertEqual(names, list(meta))

    def test_auto_sync_blocked_while_spooler_keeps_slots(self):
        root = tempfile.mkdtemp()
        store = os.path.join(root, "orca_plugins", "plugin_data", "u1")
        os.makedirs(store)
        folder = os.path.join(root, "spooler")
        os.makedirs(folder)
        orca, ns = self.load(storage=store)
        page = ns["U1ControlPage"]()
        write(os.path.join(folder, sb.KEEP_SLOTS_FILE), json.dumps({"active": True, "printer": "Snapmaker U1", "ts": time.time()}))
        page.on_message({"type": "sync_project", "auto": True})
        self.assertEqual(page.posted[-1]["text"], "Spooler is keeping slots synced")
        write(os.path.join(folder, sb.KEEP_SLOTS_FILE), json.dumps({"active": True, "ts": time.time() - 60}))
        page.on_message({"type": "sync_project", "auto": True})
        self.assertIn("No printer status", page.posted[-1]["text"])  # stale marker: runs
        write(os.path.join(folder, sb.KEEP_SLOTS_FILE), json.dumps({"active": True, "ts": time.time()}))
        page.on_message({"type": "sync_project"})  # manual still runs
        self.assertIn("No printer status", page.posted[-1]["text"])
        ns["service"]().close()

    def test_apply_button_gets_an_answer_for_its_click(self):
        # The header button asks with an id and stays busy until this reply: what was applied, or why not.
        orca, ns = self.load()
        page = ns["U1ControlPage"]()
        svc = ns["service"]()
        self.addCleanup(svc.close)
        page.on_message({"type": "sync_project", "id": 7})
        self.assertEqual(page.posted[-1]["id"], 7)
        self.assertEqual(page.posted[-1]["result"]["problems"], 1)
        self.assertIn("No printer status", page.posted[-1]["result"]["text"])
        svc.last_view = {"heads": [], "rfid": []}
        answered = threading.Event()
        page.post_message = lambda m: (page.posted.append(m), answered.set())
        ns["sync_project"] = lambda *a, **kw: (["1: Generic PLA"], [])
        page.on_message({"type": "sync_project", "id": 8})
        self.assertTrue(answered.wait(5))
        self.assertEqual(page.posted[-1]["id"], 8)
        self.assertEqual(page.posted[-1]["result"], {"text": "Project filaments 1: Generic PLA", "done": 1, "problems": 0})


class StorageOutsideCallbackTests(PluginBase):
    """OrcaSlicer 2.5 answers plugin.storage() only inside plugin callbacks; page messages and worker threads
    get "plugin.storage() must be called from a plugin callback". The folder seen while loading must be kept."""

    def test_storage_folder_is_kept_from_the_load_callback(self):
        root = tempfile.mkdtemp()
        store = os.path.join(root, "orca_plugins", "plugin_data", "u1")
        os.makedirs(store)
        os.makedirs(os.path.join(root, "spooler"))
        orca, ns = self.load(storage=store)
        inside = {"callback": False}

        def strict_storage():
            if not inside["callback"]:
                raise RuntimeError("plugin.storage() must be called from a plugin callback")
            return store

        orca.host.plugin.storage = strict_storage
        self.assertEqual(ns["spooler_dir"](), "")  # nothing known yet, outside a callback
        inside["callback"] = True
        ns["U1Control"]().register_capabilities()
        inside["callback"] = False
        self.assertEqual(ns["_storage"](), store)
        self.assertEqual(ns["spooler_dir"](), os.path.join(root, "spooler"))  # from a message or thread later


class BindTests(unittest.TestCase):
    def test_bind_writes_printer_and_no_rebind_loop(self):
        fake = fakes.FakePrinter(spoolman=False)
        self.addCleanup(fake.close)
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host, spoolman_url="http://" + fake.host))

        def call(cmd, **args):
            rid = len(pub) + 1000
            svc.submit(rid, cmd, args)
            self.assertTrue(wait_for(lambda: any(m.get("id") == rid for m in pub)))
            return next(m for m in pub if m.get("id") == rid)

        call("connect")
        self.assertNotIn("error", call("bind_spool", head=3, spool_id=7))
        self.assertTrue(fake.scripts[-1].startswith("SET_PRINT_FILAMENT_CONFIG CONFIG_EXTRUDER=3 VENDOR=Generic"))
        svc.touch()
        self.assertTrue(wait_for(lambda: svc.last_view is not None))
        # the printer now reports what we wrote: not a user change, so no rebind / no extra write
        fake.task["filament_color_rgba"][3] = "111111FF"
        fake.task["filament_type"][3] = "PLA"
        fake.task["filament_vendor"][3] = "Generic"
        writes, patches = len(fake.scripts), len(fake.patches)
        end = time.time() + 5
        while time.time() < end:
            svc.touch()
            time.sleep(0.3)
        self.assertEqual((len(fake.scripts), len(fake.patches)), (writes, patches))
        self.assertEqual(svc.written, {})

    def test_write_printer_off(self):
        fake = fakes.FakePrinter(spoolman=False)
        self.addCleanup(fake.close)
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host, spoolman_url="http://" + fake.host, spoolman_write_printer=False))
        svc.submit(1, "bind_spool", {"head": 1, "spool_id": 7})
        self.assertTrue(wait_for(lambda: any(m.get("id") == 1 for m in pub)))
        self.assertEqual(fake.scripts, [])
        self.assertIn((7, {"location": "Snapmaker U1 T2"}), fake.patches)


if __name__ == "__main__":
    unittest.main()


class SpoolerContractGapTests(unittest.TestCase):
    """Gaps found by Spooler's side of the contract review."""

    def test_printer_label_keeps_u1_suffix(self):
        import settings
        self.assertEqual(settings.printer_label("Bob"), "Bob U1")
        self.assertEqual(settings.printer_label("Workshop  u1"), "Workshop u1")
        self.assertEqual(settings.printer_label(""), "Snapmaker U1")
        store = settings.Store()
        self.assertEqual(store.update({"printer_name": "Bob"})["printer_name"], "Bob U1")

    def test_keep_slots_marker_scoped_to_printer(self):
        import spooler_bridge as sb
        marker = {"active": True, "printer": "Snapmaker U1 0.4", "ts": 100}
        self.assertTrue(sb.keep_slots_active(marker, 110, ("Snapmaker U1",)))
        self.assertFalse(sb.keep_slots_active(dict(marker, printer="Sovol SV06"), 110, ("Snapmaker U1",)))
        self.assertTrue(sb.keep_slots_active(dict(marker, printer=""), 110, ("Snapmaker U1",)))
        self.assertFalse(sb.keep_slots_active(marker, 200, ("Snapmaker U1",)))
