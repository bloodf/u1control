"""Joint integration test: u1control and Spooler (github.com/bloodf/spooler) loaded in one process,
on one fake OrcaSlicer, one fake U1 + Spoolman and one OrcaSlicer data folder.

Spooler's source: env SPOOLER_SRC (repo root or the spooler_any.py file), else the sibling ../spooler.
The shared contract under test:
  1. toolhead -> spool: print_task_config.filament_spool_id, else Spoolman location "<printer> T<n>"
  2. <data dir>/spooler/profiles.json (Spooler writes, u1control picks presets from it)
  3. <data dir>/spooler/keep_slots.json (Spooler writes, u1control pauses automatic project sync)
  4. u1control writes the bound spool to the head; sub type = filament name, Spooler tie-breaks on it
  5. only u1control books U1 filament usage
"""

import asyncio
import importlib.util
import json
import os
import runpy
import shutil
import sys
import tempfile
import time
import types
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src" / "u1control"), str(ROOT / "tests"), str(ROOT / "scripts")]

import build  # noqa: E402
import fakes  # noqa: E402
import spooler_bridge as sb  # noqa: E402
from test_u1control import wait_for  # noqa: E402

PRINTER_NAME = "Snapmaker U1"
U1_TARGET = "Snapmaker U1 (0.4 nozzle)"


def find_spooler():
    """(repo root, spooler_any.py). Raises when Spooler can't be found: no silent skip."""
    env = os.environ.get("SPOOLER_SRC", "").strip()
    candidates = [Path(env).expanduser()] if env else [ROOT.parent / "spooler"]
    for c in candidates:
        plugin = c if c.is_file() else c / "plugin" / "spooler" / "spooler_any.py"
        if plugin.is_file():
            return plugin.parent.parent.parent if not c.is_file() else c.parent.parent.parent, plugin
    raise RuntimeError(
        "Spooler source not found (looked at %s). Set SPOOLER_SRC to a checkout of github.com/bloodf/spooler "
        "(branch feat/u1control-contract or later) or put it next to this repo as ../spooler; "
        "expected <checkout>/plugin/spooler/spooler_any.py." % ", ".join(str(c) for c in candidates))


SPOOLER_ROOT, SPOOLER_FILE = find_spooler()
FIXTURES = SPOOLER_ROOT / "tests" / "fixtures"
if not (FIXTURES / "orca_parents.json").is_file():
    raise RuntimeError("Spooler checkout %s lacks tests/fixtures/orca_parents.json" % SPOOLER_ROOT)
PARENTS = json.loads((FIXTURES / "orca_parents.json").read_text(encoding="utf-8"))
SPOOLER_PRINTERS = [{"target": U1_TARGET, "label": PRINTER_NAME, "model": PRINTER_NAME, "hosts": []}]


def spoolman_spool(sid, fid, vendor, material, name, colour, location="", tag=None, last_used=None):
    return {"id": sid, "archived": False, "remaining_weight": 700.0, "initial_weight": 1000.0,
            "location": location, "last_used": last_used, "extra": {"tag": json.dumps(tag)} if tag else {},
            "filament": {"id": fid, "name": name, "material": material, "color_hex": colour, "density": 1.24,
                         "diameter": 1.75, "weight": 1000.0, "vendor": {"name": vendor}}}


def stock_spools():
    return [
        spoolman_spool(9, 31, "Snapmaker", "PLA", "Fire Red", "EE1111"),
        spoolman_spool(7, 30, "Generic", "PLA", "Matte Black", "111111"),
        spoolman_spool(11, 32, "Generic", "PETG", "White", "FAFAFA", tag="AABBCC11"),
        spoolman_spool(13, 33, "Snapmaker", "PLA", "Silk Gold", "F4C032"),
    ]


def http_json(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def apply_scripts(fake, scripts):
    """Make the fake U1 behave: SET_PRINT_FILAMENT_CONFIG changes what print_task_config reports."""
    for script in scripts:
        if not script.startswith("SET_PRINT_FILAMENT_CONFIG"):
            continue
        kv = dict(p.split("=", 1) for p in script.split()[1:])
        h = int(kv["CONFIG_EXTRUDER"])
        fake.task["filament_vendor"][h] = kv["VENDOR"]
        fake.task["filament_type"][h] = kv["FILAMENT_TYPE"]
        fake.task["filament_sub_type"][h] = kv["FILAMENT_SUBTYPE"]
        fake.task["filament_color_rgba"][h] = kv["FILAMENT_COLOR_RGBA"]
        fake.task["filament_exist"][h] = True


class JointCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.artifact = str(build.build(out_dir=Path(tempfile.mkdtemp())))

    def setUp(self):
        # <tmp>/OrcaSlicer is Orca's data folder; Spooler sits in orca_plugins next to u1control's storage.
        self.tmp = Path(tempfile.mkdtemp(prefix="joint-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp / "OrcaSlicer"
        self.storage = self.data / "orca_plugins" / "plugin_data" / "u1control"
        self.storage.mkdir(parents=True)
        self.bridge = self.data / "spooler"
        plugin_dir = self.data / "orca_plugins" / "spooler"
        plugin_dir.mkdir()
        shutil.copy(SPOOLER_FILE, plugin_dir / "spooler_any.py")

        self.orca = fakes.install_orca(preset={"name": U1_TARGET, "printer_model": PRINTER_NAME}, storage=str(self.storage))
        self.orca.host.preset.bundles.reload_local = lambda bundle: None
        self.orca.PluginType = types.SimpleNamespace(Pages="Pages")
        self.orca.slicing.Step.posSlice = "slice"
        pages = types.ModuleType("orca.pages")
        pages.PagesPluginCapabilityBase = self.orca.pages.PagesPluginCapabilityBase
        sys.modules["orca.pages"] = pages
        self.addCleanup(sys.modules.pop, "orca.pages", None)

        self.u1ns = runpy.run_path(self.artifact)
        spec = importlib.util.spec_from_file_location("spooler_plugin_joint", plugin_dir / "spooler_any.py")
        self.sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sp)
        self.assertEqual(self.sp._orca_data_dir(), self.data)  # Spooler resolves the same data folder
        self.assertEqual(sb.data_dir(str(self.storage)), str(self.bridge))
        self.assertEqual(self.sp.bridge_dir(), self.bridge)
        self.sp._ui_snap.clear()
        self.sp._ui_snap.update(printers=SPOOLER_PRINTERS, selected=U1_TARGET)
        self.sp._profiles.update(names={}, failed=("", 0.0))
        self.addCleanup(self.sp._ui_snap.clear)

    # ---------------------------------------------------------------- helpers

    def start(self, extended=False, spools=None):
        fake = fakes.FakePrinter(extended=extended, version="2.0.0.205-paxx12" if extended else "2.0.0.205")
        self.addCleanup(fake.close)
        fake.spools = spools if spools is not None else stock_spools()
        fake.task["filament_exist"] = [True] * 4
        self.fake = fake
        svc = self.u1ns["service"]()
        self.addCleanup(svc.close)
        svc.set_target(self.u1ns["Target"](fake.host, name=PRINTER_NAME, spoolman_url="http://" + fake.host))
        svc.cmd_connect()
        self.svc = svc
        return fake, svc

    def spoolman(self):
        return http_json("http://%s/api/v1/spool" % self.fake.host)

    def printer_status(self):
        return http_json("http://%s/printer/objects/query" % self.fake.host)["result"]["status"]

    def spooler_trays(self):
        doc, heads = self.sp.moon_report(self.printer_status(), None, self.spoolman(), U1_TARGET)
        self.assertTrue(heads)
        return doc["print"]["ams"]["ams"][0]["tray"]

    def bind(self, head, spool_id):
        before = len(self.fake.scripts)
        result = self.svc.cmd_bind_spool(head, spool_id)
        self.assertEqual(result["bindings"][str(head)], spool_id)
        apply_scripts(self.fake, self.fake.scripts[before:])

    def spooler_profile_sync(self):
        snapshot = {"names": {p["name"] for p in PARENTS}, "parents": PARENTS, "folder": "4242",
                    "printers": SPOOLER_PRINTERS}
        state = self.sp.profile_sync(self.spoolman(), snapshot)
        self.assertEqual(state["error"], "")
        profiles = json.loads((self.bridge / "profiles.json").read_text(encoding="utf-8"))
        # OrcaSlicer's list of filament presets, as u1control reads it: Spooler's whole bundle.
        folder = self.data / "user" / "4242" / "_local" / "spooler" / "filament"
        metas = []
        for f in sorted(folder.glob("*.json")):
            cfg = json.loads(f.read_text(encoding="utf-8"))
            metas.append({"name": "_local/spooler/" + f.stem, "bundle_id": "spooler",
                          "compatible_printers": cfg.get("compatible_printers") or [],
                          "colour": (cfg.get("default_filament_colour") or [""])[0],
                          "vendor": (cfg.get("filament_vendor") or [""])[0]})
        self.orca.host.preset_bundle().filaments = types.SimpleNamespace(
            preset_names=lambda: [m["name"] for m in metas], size=lambda: len(metas),
            preset=lambda i: types.SimpleNamespace(
                name=metas[i]["name"], bundle_id="spooler",
                config_value=lambda key, m=metas[i]: {
                    "compatible_printers": m["compatible_printers"], "default_filament_colour": [m["colour"]],
                    "filament_vendor": [m["vendor"]]}.get(key)))
        return profiles

    def u1control_sync(self):
        """u1control's project sync as the print setup runs it; {slot: preset} of what it wrote."""
        self.svc._push_status()
        view = self.svc.last_view
        start = len(self.orca.filament_calls)
        done, problems = self.u1ns["sync_project"](view["heads"], view["rfid"], {},
                                                   bound=self.u1ns["bound_spool_lookup"](self.svc))
        self.assertEqual(problems, [])
        return {slot: name for slot, name, _ in self.orca.filament_calls[start:]}


class StockFirmwareTest(JointCase):
    def test_mixed_setup_both_plugins_resolve_the_same_spools(self):
        fake, svc = self.start()
        self.bind(0, 9)   # by Spoolman location
        self.bind(1, 7)   # by Spoolman location
        # T3: not bound, an RFID card the printer read; T4: not bound, only vendor/material/colour/sub type.
        fake.tags[2] = {"CARD_UID": "AABBCC11", "VENDOR": "Generic", "MAIN_TYPE": "PETG"}
        fake.task.update(filament_vendor=["x", "x", "Generic", "Snapmaker"],
                         filament_type=["x", "x", "PETG", "PLA"],
                         filament_sub_type=["x", "x", "Basic", "Silk_Gold"],
                         filament_color_rgba=["x", "x", "FAFAFAFF", "F4C032FF"])
        apply_scripts(fake, [s for s in fake.scripts if s.startswith("SET_PRINT")])  # T1/T2 as u1control wrote them

        # u1control's side: Spoolman locations ("<printer name> T<n>", 1-based) and the head's filament.
        by_id = {s["id"]: s for s in self.spoolman()}
        self.assertEqual(by_id[9]["location"], "Snapmaker U1 T1")
        self.assertEqual(by_id[7]["location"], "Snapmaker U1 T2")
        self.assertEqual(by_id[11]["location"], "")
        self.assertEqual(by_id[13]["location"], "")
        self.assertIn((9, {"location": "Snapmaker U1 T1"}), fake.patches)
        t1 = next(s for s in fake.scripts if "CONFIG_EXTRUDER=0" in s)
        self.assertTrue(t1.startswith("SET_PRINT_FILAMENT_CONFIG CONFIG_EXTRUDER=0 VENDOR=Snapmaker FILAMENT_TYPE=PLA "
                                      "FILAMENT_SUBTYPE=Fire_Red FILAMENT_COLOR_RGBA=EE1111FF"), t1)
        self.assertEqual(fake.task["filament_sub_type"][:2], ["Fire_Red", "Matte_Black"])  # name, spaces -> "_"
        svc.cmd_spools()
        self.assertEqual(svc.bindings, {0: 9, 1: 7})  # a re-read of Spoolman gives the same bindings

        # Spooler's side, fed the printer state and Spoolman's list as they stand now.
        trays = self.spooler_trays()
        self.assertEqual([t["spool_id"] for t in trays], [9, 7, 11, 13])
        self.assertEqual([t.get("linked", "") for t in trays], ["u1control", "u1control", "", ""])
        # ...and it agrees with u1control for every head u1control bound.
        for head, spool_id in svc.bindings.items():
            self.assertEqual(trays[head]["spool_id"], spool_id)

    def test_name_ending_in_u1_and_renamed_printer_still_bind(self):
        fake, svc = self.start()
        svc.target.name = "Workshop U1"  # the printer renamed in u1control's settings
        svc.bindings = {}
        self.bind(0, 9)
        self.assertEqual({s["id"]: s["location"] for s in self.spoolman()}[9], "Workshop U1 T1")
        self.assertEqual(self.spooler_trays()[0]["spool_id"], 9)  # Spooler accepts any name ending in "U1"

    def test_sub_type_u1control_wrote_breaks_a_colour_tie(self):
        twins = [spoolman_spool(21, 41, "Snapmaker", "PLA", "Basic Black", "080A0D"),
                 spoolman_spool(22, 42, "Snapmaker", "PLA", "Silk Black", "080A0D")]
        fake, svc = self.start(spools=twins)
        self.bind(3, 22)
        for s in self.spoolman():  # location gone: only the head's own report is left to decide
            fake.spools[[x["id"] for x in fake.spools].index(s["id"])]["location"] = ""
        self.assertEqual(fake.task["filament_sub_type"][3], "Silk_Black")
        self.assertEqual(self.spooler_trays()[3]["spool_id"], 22)


class ExtendedFirmwareTest(JointCase):
    def test_reported_spool_ids_resolve_identically(self):
        spools = stock_spools()
        spools[1]["location"] = "Snapmaker U1 T1"  # stale stock-firmware location; the reported id wins
        fake, svc = self.start(extended=True, spools=spools)
        self.assertEqual(svc.firmware["kind"], "extended")
        fake.task["filament_spool_id"] = [9, 7, 11, 13]
        svc._push_status()
        self.assertEqual(svc.bindings, {0: 9, 1: 7, 2: 11, 3: 13})
        svc.cmd_spools()
        self.assertEqual(svc.bindings, {0: 9, 1: 7, 2: 11, 3: 13})  # locations are not consulted
        trays = self.spooler_trays()
        self.assertEqual([t["spool_id"] for t in trays], [9, 7, 11, 13])
        self.assertTrue(all("linked" not in t for t in trays))  # by id, not by location
        lookup = self.u1ns["bound_spool_lookup"](svc)
        self.assertEqual([lookup(h)["id"] for h in range(4)], [t["spool_id"] for t in trays])

    def test_binding_on_extended_firmware_sets_the_id_not_a_location(self):
        fake, svc = self.start(extended=True)
        svc.cmd_bind_spool(2, 11)
        self.assertEqual(fake.scripts[-1], "SET_SPOOL_ID CHANNEL=2 SPOOL_ID=11")
        self.assertEqual(fake.patches, [])  # u1control writes no Spoolman location on this firmware
        fake.task["filament_spool_id"] = [0, 0, 11, 0]  # what the firmware then reports
        self.assertEqual(self.spooler_trays()[2]["spool_id"], 11)


class PresetsTest(JointCase):
    def bind_all(self):
        for head, spool_id in enumerate((9, 7, 11, 13)):
            self.bind(head, spool_id)

    def test_profile_sync_and_project_sync_choose_the_same_presets(self):
        self.start()
        self.bind_all()
        profiles = self.spooler_profile_sync()
        self.assertEqual(profiles["version"], 1)
        self.assertEqual(sorted(profiles["filaments"]), ["30", "31", "32", "33"])
        for fid, per_printer in profiles["filaments"].items():
            self.assertEqual(list(per_printer), [PRINTER_NAME])
            self.assertTrue(per_printer[PRINTER_NAME].startswith("_local/spooler/"), per_printer)
        # u1control reads the very file Spooler wrote, from its own storage path.
        self.assertEqual(sb.read_json(sb.data_dir(str(self.storage)), sb.PROFILES_FILE), profiles)

        written = self.u1control_sync()
        expected = {head + 1: profiles["filaments"][str(fid)][PRINTER_NAME]
                    for head, fid in enumerate((31, 30, 32, 33))}  # spools 9, 7, 11, 13
        self.assertEqual(written, expected)  # same slot = head + 1, exactly Spooler's names

    def test_keep_slots_leaves_what_u1control_wrote_over_three_passes(self):
        self.start()
        self.bind_all()
        profiles = self.spooler_profile_sync()
        sp = self.sp
        names = {sp.PROFILE_PREFIX + n for n in sp._profiles["names"].values()}
        seen = {}
        for gen in (1, 2, 3):
            held = self.u1control_sync()
            trays = self.spooler_trays()
            # Spooler's own plan for the plate is what u1control just wrote...
            plan, missing = sp.slot_plan(trays, 4, names)
            self.assertEqual(missing, [])
            self.assertEqual(dict(plan), held)
            # ...so Keep Slots Synced has nothing to change, pass after pass.
            current = [(held[slot], False) for slot in (1, 2, 3, 4)]
            self.assertEqual(sp.keep_plan(trays, 4, names, current, gen, seen), [], "pass %d" % gen)
        self.assertEqual(sorted(seen), [1, 2, 3, 4])
        self.assertEqual(len({n for n in held.values()}), 4, profiles)  # four distinct presets, none shared

    def test_unbound_heads_do_not_flip_flop_either(self):
        # Nothing bound: u1control picks by colour/material. Spooler's matcher still sees spools by
        # tag/colour. Whatever u1control wrote, a later Keep Slots pass must settle (second pass no changes).
        self.start()
        self.fake.tags[2] = {"CARD_UID": "AABBCC11", "VENDOR": "Generic", "MAIN_TYPE": "PETG"}
        self.fake.task.update(filament_vendor=["Snapmaker", "Generic", "Generic", "Snapmaker"],
                              filament_type=["PLA", "PLA", "PETG", "PLA"],
                              filament_sub_type=["Basic", "Matte", "Basic", "Silk_Gold"],
                              filament_color_rgba=["EE1111FF", "111111FF", "FAFAFAFF", "F4C032FF"])
        self.spooler_profile_sync()
        sp = self.sp
        names = {sp.PROFILE_PREFIX + n for n in sp._profiles["names"].values()}
        trays = self.spooler_trays()
        self.assertEqual([t["spool_id"] for t in trays], [9, 7, 11, 13])
        held, seen = self.u1control_sync(), {}
        current = [(held[s], False) for s in (1, 2, 3, 4)]
        first = sp.keep_plan(trays, 4, names, current, 1, seen)
        for slot, name in first:  # Spooler's first pass may take slots over once
            current[slot - 1] = (name, False)
        for gen in (2, 3):
            self.assertEqual(sp.keep_plan(trays, 4, names, current, gen, seen), [], "pass %d" % gen)
        self.assertEqual({s: n for s, n in sp.slot_plan(trays, 4, names)[0]},
                         {s: current[s - 1][0] for s in (1, 2, 3, 4)})


class KeepSlotsMarkerTest(JointCase):
    def setUp(self):
        super().setUp()
        self.fake, self.svc = self.start()
        self.bind(0, 9)
        self.page = self.u1ns["U1ControlPage"]()
        self.svc._push_status()
        sp = self.sp
        patches = [mock.patch.object(sp, "sync_for", lambda snap: set()),
                   mock.patch.object(sp, "printer_trays", lambda base: []),
                   mock.patch.object(sp, "MOON_POLL", 0.02)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        sp._ui_snap.update(host="http://u1", slots=4, names=set(), current=[], gen=1)
        self.addCleanup(lambda: sp._keep.update(run=None))

    def sync(self, **extra):
        self.page.on_message({"type": "sync_project", **extra})
        return self.page.posted[-1]["text"]

    def test_auto_sync_pauses_while_spooler_keeps_slots_and_resumes_after(self):
        sp, orca = self.sp, self.orca
        results = {}

        async def scenario():
            run = asyncio.ensure_future(sp.SpoolerKeepSlots().execute())
            await asyncio.sleep(0.1)
            marker = json.loads((self.bridge / "keep_slots.json").read_text(encoding="utf-8"))
            self.assertEqual((marker["active"], marker["printer"]), (True, PRINTER_NAME))
            calls = len(orca.filament_calls)
            results["auto_active"] = self.sync(auto=True)
            results["calls_blocked"] = len(orca.filament_calls) - calls
            results["manual_active"] = self.sync()
            results["calls_manual"] = len(orca.filament_calls) - calls
            await sp.SpoolerKeepSlots().execute()  # run it again: stops it
            await asyncio.wait_for(run, 2)

        asyncio.run(scenario())
        self.assertEqual(results["auto_active"], "Spooler is keeping slots synced")
        self.assertEqual(results["calls_blocked"], 0)  # auto sync touched no slot
        self.assertTrue(results["manual_active"].startswith("Project filaments 1:"), results["manual_active"])
        self.assertGreater(results["calls_manual"], 0)  # manual sync still works

        stopped = json.loads((self.bridge / "keep_slots.json").read_text(encoding="utf-8"))
        self.assertFalse(stopped["active"])
        before = len(orca.filament_calls)
        self.assertTrue(self.sync(auto=True).startswith("Project filaments 1:"))  # stopped marker: auto runs
        self.assertGreater(len(orca.filament_calls), before)

    def test_stale_marker_does_not_block_auto_sync(self):
        # Spooler crashed without writing "stopped": u1control must not stay locked out.
        self.sp.mark_keep_slots(True, PRINTER_NAME)
        marker = json.loads((self.bridge / "keep_slots.json").read_text(encoding="utf-8"))
        self.assertEqual(self.sync(auto=True), "Spooler is keeping slots synced")
        marker["ts"] = time.time() - (sb.KEEP_SLOTS_FRESH + 5)
        (self.bridge / "keep_slots.json").write_text(json.dumps(marker), encoding="utf-8")
        self.assertTrue(self.sync(auto=True).startswith("Project filaments 1:"))

    def test_unload_while_running_releases_u1control(self):
        sp = self.sp

        async def scenario():
            capability = sp.SpoolerKeepSlots()
            run = asyncio.ensure_future(capability.execute())
            await asyncio.sleep(0.1)
            self.assertEqual(self.sync(auto=True), "Spooler is keeping slots synced")
            capability.on_unload()
            await asyncio.wait_for(run, 2)

        asyncio.run(scenario())
        self.assertTrue(self.sync(auto=True).startswith("Project filaments 1:"))


class UsageTest(JointCase):
    def run_print(self):
        fake, svc = self.fake, self.svc
        svc.remember_job("a.gcode", {0: 0, 1: 3}, [{"index": 0, "weight": 3.5}, {"index": 1, "weight": 1.5}])
        events = []
        sp = self.sp
        with mock.patch.object(sp, "source", return_value="spoolman"), \
                mock.patch.object(sp, "usage_mode", return_value="auto"), \
                mock.patch.object(sp, "usage_event", side_effect=lambda *e: events.append(e)):
            for state, gcode_state, pct in (("printing", "RUNNING", 5), ("printing", "RUNNING", 60),
                                            ("complete", "FINISH", 100), ("complete", "FINISH", 100)):
                fake.state = state
                svc._push_status()  # u1control's monitor pass
                doc, _ = sp.moon_report(self.printer_status(), None, self.spoolman(), U1_TARGET)
                doc["print"].update(gcode_state=gcode_state, mc_percent=pct)
                sp.live_apply("auto-u1", "U1", doc, link="auto-u1")  # Spooler's Moonraker poll of the same printer
        sp._live["printers"].clear()
        return events

    def test_one_booking_per_used_toolhead_from_u1control_none_from_spooler(self):
        self.start()
        self.bind(0, 9)
        self.bind(3, 13)
        self.assertEqual(self.svc.bindings, {0: 9, 3: 13})
        spooler_events = self.run_print()
        self.assertEqual(spooler_events, [])  # Spooler books nothing for a Moonraker printer
        self.assertEqual(sorted((sid, body["use_weight"]) for sid, body in self.fake.uses), [(9, 3.5), (13, 1.5)])
        self.assertEqual(len(self.fake.uses), 2)  # and no repeat on the later "complete" passes
        self.assertEqual({"state": self.svc.last_state}, {"state": "complete"})

    def test_usage_tracker_returns_nothing_for_a_moonraker_printer(self):
        state = {"link": "auto-u1", "job": {"gcode_state": "FINISH", "mc_percent": 100}}
        with mock.patch.object(self.sp, "source", return_value="spoolman"), \
                mock.patch.object(self.sp, "usage_mode", return_value="auto"):
            self.assertEqual(self.sp.usage_track("auto-u1", state, True), [])

    def test_no_booking_on_extended_firmware_either_from_spooler(self):
        self.start(extended=True)
        self.fake.task["filament_spool_id"] = [9, 7, 11, 13]
        self.assertEqual(self.run_print(), [])
        self.assertEqual(self.fake.uses, [])  # extended firmware: SpoolLink books, not u1control and not Spooler


if __name__ == "__main__":
    unittest.main()
