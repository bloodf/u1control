"""Automagic/Expert settings, print dialog rules, auto-add pipeline, Spooler interop."""

import json
import os
import runpy
import sys
import tempfile
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
        self.assertEqual((eff["mode"], eff["print_dialog"], eff["printer_name"]), ("automagic", "auto", "Snapmaker U1"))
        st.update({"print_dialog": "never", "chamber_wait": False, "host": "1.2.3.4", "bogus": 1, "purifier": "nope"})
        eff = st.effective()
        self.assertEqual((eff["print_dialog"], eff["chamber_wait"], eff["host"]), ("auto", True, "1.2.3.4"))  # ignored
        st.update({"mode": "expert"})
        eff = st.effective()
        self.assertEqual((eff["print_dialog"], eff["chamber_wait"], eff["purifier"]), ("never", False, "auto"))
        self.assertEqual(settings.Store(os.path.join(d, "settings.json")).effective(), eff)  # persisted

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


class DialogTests(unittest.TestCase):
    def setUp(self):
        self.heads = u1.describe_toolheads(fakes.task_config())
        self.fils = [{"index": 0, "type": "PLA", "colour": "#FF0000"}, {"index": 1, "type": "PETG", "colour": "#FFFFFF"}]
        self.mapping = u1.auto_map(self.fils, self.heads)

    def nd(self, fils=None, mapping=None, known=True, first=False):
        fils = fils or self.fils
        return u1.needs_dialog(fils, self.heads, mapping or u1.auto_map(fils, self.heads), known, first)

    def test_cases(self):
        self.assertFalse(self.nd())
        self.assertTrue(self.nd(first=True))
        self.assertTrue(self.nd(known=False))
        self.assertTrue(self.nd(mapping={0: 2, 1: 1}))  # empty head -> warning
        self.assertTrue(self.nd(fils=[{"index": 0, "type": "ABS", "colour": "#FF0000"}]))  # no head with ABS
        self.assertTrue(self.nd(fils=[{"index": 0, "type": "PLA+", "colour": "#FF0000"}]))  # family only
        both = [{"index": 0, "type": "PETG", "colour": "#FFFFFF"}, {"index": 1, "type": "PETG", "colour": "#EEEEEE"}]
        self.assertTrue(self.nd(fils=both))  # two filaments want the single PETG head


class PluginBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=__import__("pathlib").Path(tempfile.mkdtemp())))

    def load(self, **kw):
        orca = fakes.install_orca(**kw)
        return orca, runpy.run_path(self.artifact)


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
        self.assertTrue(any(a["key"] == "print_dialog" and a["choices"] for a in msg["automations"]))
        self.assertFalse(msg["spooler"]["installed"])
        page.on_message({"type": "save_settings", "settings": {"spooler_hint_dismissed": True, "api_key": "••••", "host": "127.0.0.1:1"}})
        config = [m for m in page.posted if m["type"] == "config"][-1]
        self.assertTrue(config["spooler"]["dismissed"])
        self.assertTrue(wait_for(lambda: any("U1 print setup added" in m.get("text", "") for m in page.posted)))
        ns["service"]().close()


class DialogFlowTests(PluginBase):
    def test_second_print_skips_dialog(self):
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
        # second print: options known, mapping clean -> auto mode sends without the pop-up
        self.assertEqual(len(orca.windows), 1)


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
        longer = {"filaments": {"12": {"Snapmaker U1 0.4": "p"}}}
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
