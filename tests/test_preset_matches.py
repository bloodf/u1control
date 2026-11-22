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


if __name__ == "__main__":
    unittest.main()
