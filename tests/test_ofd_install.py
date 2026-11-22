"""Installing an Open Filament Database preset from a toolhead card: without Spooler (or without a Spoolman spool on
the head) U1 Control writes it, flattened with a filament_id of its own, into its own local bundle and remembers it for
the head; with Spooler installed and a Spoolman spool on the head, Spooler installs it into its preset of that
filament. The network is never reached here. Run: python3 -m unittest discover -s tests"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import filmatch  # noqa: E402
import test_preset_matches as tpm  # noqa: E402

OFD_ID = "f6670de4-545e-537e-8152-fd09f7e5ff37"   # Polymaker Draft PLA (OFD), inherits Generic PLA @System


class OfdInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tpm.PresetMatchTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        tpm.PresetMatchTests.tearDownClass.__func__(cls)

    def setUp(self):
        tpm.PresetMatchTests.setUp(self)
        with open(os.path.join(ROOT, "tests", "fixtures", "ofd_index.json"), "rb") as f:
            self.index = f.read()
        profile = next(p for p in json.loads(self.index)["profiles"] if p["id"] == OFD_ID)
        self.preset = {"name": profile["profile_name"], "inherits": profile["inherits"], "from": "User", "version": "2.0.2.0",
                       "filament_type": ["PLA"], "filament_vendor": ["Polymaker"], "nozzle_temperature": ["215"],
                       "filament_density": ["1.2"], "filament_notes": ["Generated from the Open Filament Database."]}
        self.calls, self.reloads = [], []
        fm = self.ns["filmatch"]
        original = fm._ofd_get
        fm._ofd_get = self.get
        self.addCleanup(setattr, fm, "_ofd_get", original)
        self.names = list(tpm.NAMES) + ["Generic PLA @System"]
        filaments = self.orca.host.preset_bundle().filaments

        class Preset:
            def __init__(self, name):
                self.name, self.is_system, self.bundle_id, self.file = name, name.endswith("@System"), "", ""
                self.is_compatible = True

            def is_user(self):
                return False

            def config_keys(self):
                return ["nozzle_temperature", "filament_flow_ratio", "filament_id"] if self.is_system else []

            def config_value(self, key):
                return {"nozzle_temperature": "200,200", "filament_flow_ratio": "0.98,0.98", "filament_id": "OFDSrzZ8"}.get(key) \
                    if self.is_system else None
        filaments.size = lambda: len(self.names)
        filaments.preset = lambda i: Preset(self.names[i])
        filaments.find_preset = lambda name: Preset(name) if name in self.names else None

        def reload(bundle):
            self.reloads.append(bundle)
            self.names.append("_local/%s/%s" % (bundle, self.preset["name"]))
        self.orca.host.preset.bundles.reload_local = reload
        self.store = self.ns["settings"].Store(path=os.path.join(self.storage, "settings.json"))
        self.store.update({"ofd_enabled": True})
        self.tags = [{"vendor": "Polymaker", "type": "PLA"} if h["index"] == self.pla else None for h in self.heads]
        self.view = {**self.view, "rfid": self.tags}

    def get(self, url, headers=None):
        self.calls.append(url)
        return 200, (self.index if url.endswith(filmatch.OFD_INDEX) else json.dumps(self.preset).encode("utf-8")), {}

    def test_own_bundle_without_spooler(self):
        self.assertEqual(self.ns["install_ofd"](self.view, None, self.pla, OFD_ID, self.store), "")
        self.assertEqual(self.reloads, ["u1control_ofd"])
        path = os.path.join(self.root, "user", "default", "_local", "u1control_ofd", "filament", "Polymaker Draft PLA (OFD).json")
        with open(path, encoding="utf-8") as f:
            written = json.load(f)
        self.assertEqual((written["inherits"], written["filament_id"][:3], written["compatible_printers"]), ("", "UOD", []))
        self.assertEqual((written["nozzle_temperature"], written["filament_flow_ratio"]), (["215", "215"], "0.98,0.98"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "user", "default", "filament")))   # no user preset folder touched
        row = next(m for m in self.ns["preset_matches"](self.view, None) if m["head"] == self.pla)
        self.assertEqual((row["name"], row["source"]), ("_local/u1control_ofd/Polymaker Draft PLA (OFD)", "remembered"))
        self.orca.filament_calls.clear()
        self.ns["sync_project"](self.heads, self.tags, {})
        self.assertIn((self.pla + 1, "_local/u1control_ofd/Polymaker Draft PLA (OFD)"),
                      [(slot, name) for slot, name, _ in self.orca.filament_calls])

    def test_spooler_installs_for_a_spoolman_spool(self):
        os.makedirs(self.spooler, exist_ok=True)
        with open(os.path.join(self.spooler, "spooler_settings.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        spool = {"id": 7, "filament_id": 9, "vendor": "Polymaker", "name": "Draft White"}
        note = self.ns["install_ofd"](self.view, lambda i: spool if i == self.pla else None, self.pla, OFD_ID, self.store)
        self.assertIn("#7", note)
        self.assertEqual(self.reloads, [])   # nothing installed by U1 Control
        shared = filmatch.load_matches(os.path.join(self.spooler, filmatch.MATCHES_FILE))
        self.assertEqual(shared["entries"]["filament:9"]["default"], "ofd:" + OFD_ID)
        self.assertTrue(os.path.exists(os.path.join(self.spooler, filmatch.OFD_DIR, filmatch.OFD_PRESETS, OFD_ID + ".json")))

    def test_refused(self):
        with self.assertRaises(ValueError):
            self.ns["install_ofd"](self.view, None, self.pla, "not-an-id", self.store)
        self.preset["post_process"] = ["x"]
        with self.assertRaises(ValueError) as caught:
            self.ns["install_ofd"](self.view, None, self.pla, OFD_ID, self.store)
        self.assertIn("post_process", str(caught.exception))
        self.store.update({"ofd_enabled": False})
        with self.assertRaises(ValueError):
            self.ns["install_ofd"](self.view, None, self.pla, OFD_ID, self.store)
        self.assertEqual(self.reloads, [])


if __name__ == "__main__":
    unittest.main()
