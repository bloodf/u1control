"""Spool links shared with Spooler: a location Spooler writes is read here (a renamed printer included), a link
made here moves this plugin's presence "links" so Spooler re-reads at once, and the page's Spoolman refresh setting."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import peers  # noqa: E402
from unittest import mock  # noqa: E402
from service import Service, Target  # noqa: E402
import settings  # noqa: E402
import spoolman as sm  # noqa: E402
from test_unified import spooler_presence  # noqa: E402

NOW = 1_800_000_000.0


def spool(sid, location, last_used=""):
    return {"id": sid, "location": location, "last_used": last_used}


class SpoolerWrittenLocations(unittest.TestCase):
    def test_spooler_format_is_read(self):
        # Spooler's Assign writes "<printer model> T<n>".
        self.assertEqual(sm.bindings_from_locations([spool(7, "Snapmaker U1 T2")], "Snapmaker U1"), {1: 7})

    def test_renamed_printer_still_reads_spoolers_link(self):
        name = settings.printer_label("Workshop")   # stored as "Workshop U1"
        self.assertEqual(sm.bindings_from_locations([spool(7, "Snapmaker U1 T3")], name), {2: 7})

    def test_own_name_wins_over_model_name(self):
        spools = [spool(7, "Snapmaker U1 T1", "2026-01-02"), spool(8, "Workshop U1 T1", "2026-01-01")]
        self.assertEqual(sm.bindings_from_locations(spools, "Workshop U1"), {0: 8})

    def test_written_here_is_what_spooler_reads(self):
        # Spooler reads "<name> T<n>" for any name ending in "U1"; u1control writes that form.
        self.assertEqual(sm.LOCATION_FMT % ("Workshop U1", 2), "Workshop U1 T2")


class RefreshSetting(unittest.TestCase):
    def store(self):
        d = tempfile.mkdtemp()
        return settings.Store(os.path.join(d, "s.json"))

    def test_default_is_30(self):
        self.assertEqual(self.store().effective()["spoolman_refresh_s"], 30)

    def test_range_and_off(self):
        st = self.store()
        for value, want in ((10, 10), (300, 300), (0, 0), (9, 0), (301, 0), (True, 0), ("30", 0), (45, 45)):
            st.update({"spoolman_refresh_s": 0})
            self.assertEqual(st.update({"spoolman_refresh_s": value})["spoolman_refresh_s"], want, value)

    def test_bad_stored_value_falls_back(self):
        st = self.store()
        st._write({"spoolman_refresh_s": 5})
        self.assertEqual(st.effective()["spoolman_refresh_s"], 30)


class LinksSignal(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.now = NOW
        self.link = peers.SpoolerLink(self.root, "1.0", log=lambda *_: None, clock=lambda: self.now)

    def test_presence_carries_links_and_moves_on_change(self):
        self.assertEqual(self.link.presence.doc()["links"], 0)
        self.now += 1
        self.link.links_changed()
        self.assertEqual(self.link.presence.doc()["links"], int((NOW + 1) * 1000))

    def test_spoolers_links_are_read(self):
        os.makedirs(os.path.join(self.root, "spooler"))
        with open(os.path.join(self.root, "spooler", "presence.json"), "w") as f:
            json.dump(spooler_presence(ts=NOW, links=1234), f)
        self.assertEqual(self.link.spooler()["links"], 1234)

    def test_older_spooler_without_links(self):
        os.makedirs(os.path.join(self.root, "spooler"))
        with open(os.path.join(self.root, "spooler", "presence.json"), "w") as f:
            json.dump(spooler_presence(ts=NOW), f)
        self.assertEqual(self.link.spooler()["links"], 0)


class ServiceSync(unittest.TestCase):
    """Against the fake U1 and its fake Spoolman: Spoolman's locations are the only link store."""

    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host, name="Workshop U1", spoolman_url="http://" + self.fake.host))
        self.svc.cmd_connect()
        self.svc.peers = mock.Mock()

    def test_a_link_spooler_wrote_shows_on_the_next_read(self):
        self.svc.cmd_spools()
        self.assertNotIn(2, self.svc.bindings)
        self.fake.spools[0]["location"] = "Snapmaker U1 T3"   # Spooler's Assign, with the model name
        self.assertEqual(self.svc.cmd_spools()["bindings"].get("2"), self.fake.spools[0]["id"])

    def test_link_and_unlink_here_tell_spooler(self):
        sid = self.fake.spools[0]["id"]
        self.svc.cmd_bind_spool(1, sid)
        self.assertEqual(self.svc.peers.links_changed.call_count, 1)
        self.assertEqual(next(s for s in self.fake.spools if s["id"] == sid)["location"], "Workshop U1 T2")
        self.svc.cmd_unbind_spool(1)
        self.assertEqual(self.svc.peers.links_changed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
