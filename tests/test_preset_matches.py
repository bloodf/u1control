"""Remembered toolhead presets (matches.json, filmatch): a preset picked by hand on a toolhead card wins in Apply to
project filaments while it still fits; Spooler's matches.json is read first and written while Spooler is installed,
U1 Control's own otherwise; profile_overrides move into it once. Run: python3 -m unittest discover -s tests"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import filmatch  # noqa: E402
import u1  # noqa: E402

NAMES = ["Generic PETG @U1", "Polymaker PLA @U1", "Generic PLA @U1", "Generic PLA Silk @U1"]


class PresetMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.out = tempfile.mkdtemp()
        cls.artifact = str(build.build(out_dir=__import__("pathlib").Path(cls.out)))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.storage = os.path.join(self.root, "orca_plugins", "u1control_data")
        os.makedirs(self.storage)
        self.spooler = os.path.join(self.root, "spooler")
        self.orca = fakes.install_orca(filament_names=NAMES, storage=self.storage)
        self.ns = fakes.load_wheel(self.artifact)
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.heads = u1.summarize(self.fake.status())["heads"]
        self.view = {"heads": self.heads, "rfid": [None] * 4}
        self.pla = next(h["index"] for h in self.heads if h["loaded"] and h["type"] == "PLA")

    def applied(self):
        self.orca.filament_calls.clear()
        self.ns["sync_project"](self.heads, [None] * 4, {})
        return {slot: name for slot, name, _ in self.orca.filament_calls}

    def test_picked_by_hand_without_spooler(self):
        slot = self.pla + 1
        self.assertEqual(self.applied()[slot], "Generic PLA @U1")
        self.ns["pick_preset"](self.view, None, self.pla, "Polymaker PLA @U1")
        self.assertFalse(os.path.exists(os.path.join(self.spooler, filmatch.MATCHES_FILE)))
        own = filmatch.load_matches(os.path.join(self.storage, filmatch.MATCHES_FILE))
        self.assertEqual(len(own["entries"]), 1)
        self.assertEqual(self.applied()[slot], "Polymaker PLA @U1")
        row = next(m for m in self.ns["preset_matches"](self.view, None) if m["head"] == self.pla)
        self.assertEqual((row["name"], row["source"]), ("Polymaker PLA @U1", "remembered"))
        self.assertTrue(row["remembered_key"].startswith("mat:"))
        self.assertIn("Generic PLA Silk @U1", [c["name"] for c in row["candidates"]])
        self.assertNotIn("Generic PETG @U1", [c["name"] for c in row["candidates"]])
        with self.assertRaises(ValueError):   # another material
            self.ns["pick_preset"](self.view, None, self.pla, "Generic PETG @U1")
        with self.assertRaises(ValueError):
            self.ns["pick_preset"](self.view, None, 9, "Generic PLA @U1")
        self.ns["pick_preset"](self.view, None, self.pla, None)   # Automatic
        self.assertEqual(self.applied()[slot], "Generic PLA @U1")
        self.assertEqual(filmatch.load_matches(os.path.join(self.storage, filmatch.MATCHES_FILE))["entries"], {})

    def test_spoolers_store_first_and_written_while_spooler_is_installed(self):
        head = self.heads[self.pla]
        key = filmatch.toolhead_keys(head)[0]
        filmatch.remember(os.path.join(self.spooler, filmatch.MATCHES_FILE), {key: "Generic PLA Silk @U1"})   # as Spooler writes it
        filmatch.remember(os.path.join(self.storage, filmatch.MATCHES_FILE), {key: "Polymaker PLA @U1"})
        self.assertEqual(self.applied()[self.pla + 1], "Generic PLA Silk @U1")
        # Spooler installed (its settings file): a pick goes to Spooler's matches.json
        with open(os.path.join(self.spooler, "spooler_settings.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.ns["pick_preset"](self.view, None, self.pla, "Polymaker PLA @U1")
        shared = filmatch.load_matches(os.path.join(self.spooler, filmatch.MATCHES_FILE))
        self.assertIn("Polymaker PLA @U1", json.dumps(shared))
        # a remembered preset that is gone falls back to the next one, then to the scored pick
        os.remove(os.path.join(self.spooler, filmatch.MATCHES_FILE))
        os.remove(os.path.join(self.storage, filmatch.MATCHES_FILE))
        self.assertEqual(self.applied()[self.pla + 1], "Generic PLA @U1")

    def test_a_bound_spools_spooler_preset_beats_a_vendor_material_pick(self):
        """A preset remembered for a whole vendor + material (mat: key) doesn't replace the Spooler preset of the spool
        bound to the toolhead; one remembered for that very spool still does, and without a bound spool the mat: pick
        is used as before."""
        head = self.heads[self.pla]
        spooler = "_local/spooler/Acme PLA @Snapmaker U1"
        names = NAMES + [spooler]
        path = os.path.join(self.root, "m.json")
        mat = [k for k in filmatch.toolhead_keys(head) if k.startswith("mat:")][0]
        filmatch.remember(path, {mat: "Polymaker PLA @U1"})
        ctx = lambda: {"names": names, "colours": {}, "mine": [], "printer": "",   # noqa: E731
                       "preference": lambda n, h, t: spooler, "stores": [filmatch.load_matches(path)]}
        spool = {"id": 7}
        match = self.ns["head_match"](ctx(), head, {}, spool)
        self.assertEqual((match["name"], match["source"]), (spooler, "spooler"))
        self.assertEqual(self.ns["head_match"](ctx(), head, {}, None)["name"], "Polymaker PLA @U1")   # no spool bound
        filmatch.remember(path, {"spool:7": "Generic PLA Silk @U1"})   # picked by hand for this spool
        match = self.ns["head_match"](ctx(), head, {}, spool)
        self.assertEqual((match["name"], match["source"]), ("Generic PLA Silk @U1", "remembered"))

    def test_profile_overrides_move_once(self):
        head = self.heads[self.pla]
        store = self.ns["settings"].Store(path=os.path.join(self.storage, "settings.json"))
        store.update({"profile_overrides": {"%s|%s|" % (head["vendor"], head["type"]): "Generic PLA Silk @U1"}})
        self.assertEqual(self.ns["migrated_overrides"](store), {})
        self.assertTrue(store.effective()["overrides_migrated"])
        self.assertEqual(self.applied()[self.pla + 1], "Generic PLA Silk @U1")
        os.remove(os.path.join(self.storage, filmatch.MATCHES_FILE))
        self.assertEqual(self.ns["migrated_overrides"](store), {})   # once: not copied again
        self.assertFalse(os.path.exists(os.path.join(self.storage, filmatch.MATCHES_FILE)))


class OfdTests(PresetMatchTests):
    """The Open Filament Database: off by default and never contacted then; on, its proposals are added from the index
    kept in Spooler's folder (Spooler installed) or U1 Control's own, read again once a day."""

    def setUp(self):
        super().setUp()
        self.calls = []
        with open(os.path.join(ROOT, "tests", "fixtures", "ofd_index.json"), "rb") as f:
            body = f.read()

        def get(url, headers=None):
            self.calls.append(url)
            return 200, body, {}
        original = self.ns["filmatch"]._ofd_get
        self.ns["filmatch"]._ofd_get = get
        self.addCleanup(setattr, self.ns["filmatch"], "_ofd_get", original)
        self.store = self.ns["settings"].Store(path=os.path.join(self.storage, "settings.json"))
        self.polymaker = [{"vendor": "Polymaker", "type": "PLA", "sub_type": "Matte"} if h["index"] == self.pla else None for h in self.heads]

    def test_off_by_default(self):
        self.assertFalse(self.store.effective()["ofd_enabled"])
        self.assertEqual(self.ns["ofd_status"](self.store, refresh=True), {"on": False})
        matches = self.ns["preset_matches"]({**self.view, "rfid": self.polymaker}, None, ofd=False)
        self.assertTrue(matches and all(m["ofd"] == [] for m in matches))
        self.assertEqual(self.calls, [])
        self.assertNotIn(filmatch.OFD_ORIGIN, self.ns["network_grants"](type("Cap", (), {})()))

    def test_on(self):
        self.store.update({"ofd_enabled": True})
        state = self.ns["ofd_status"](self.store)
        self.assertEqual((state["on"], state["error"]), (True, ""))
        self.assertTrue(os.path.exists(os.path.join(self.storage, filmatch.OFD_DIR, filmatch.OFD_INDEX)))   # no Spooler: own folder
        row = next(m for m in self.ns["preset_matches"]({**self.view, "rfid": self.polymaker}, None, ofd=True) if m["head"] == self.pla)
        self.assertIn("Polymaker For Production Matte PLA (OFD)", [c["name"] for c in row["ofd"]])
        self.assertEqual(len(self.calls), 1)
        self.ns["ofd_status"](self.store, refresh=True)
        self.assertEqual(len(self.calls), 2)
        os.makedirs(self.spooler, exist_ok=True)
        with open(os.path.join(self.spooler, "spooler_settings.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(self.ns["ofd_folder"](), os.path.join(self.spooler, filmatch.OFD_DIR))   # Spooler's, shared


if __name__ == "__main__":
    unittest.main()
