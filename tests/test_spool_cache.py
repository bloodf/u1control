"""The Spoolman list is kept (memory + the plugin's storage) so a fresh tab or restart shows it at once, and a
bind reads Spoolman's list only when the spool isn't in it."""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import spoolman as sm  # noqa: E402
from service import Service, Target  # noqa: E402


class SpoolCache(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.path = os.path.join(tempfile.mkdtemp(), "spool_cache.json")
        self.svc = self.start()

    def start(self, host=None, url=None):
        svc = Service(lambda m: None, log=lambda m: None, spool_cache_path=self.path)
        self.addCleanup(svc.close)
        svc.set_target(Target(host or self.fake.host, name="Workshop U1", spoolman_url=url or "http://" + self.fake.host))
        svc.cmd_connect()
        return svc

    def reads(self):
        """Patch Spoolman's list read; the returned list counts the reads."""
        calls, real = [], sm.Spoolman.spools
        patcher = mock.patch.object(sm.Spoolman, "spools", lambda smc: calls.append(1) or real(smc))
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_nothing_saved_nothing_shown(self):
        self.assertEqual(self.svc.cached_spools()["spools"], [])

    def test_restart_shows_the_saved_list_marked_stale_until_spoolman_answers(self):
        self.svc.cmd_spools()
        self.svc.cmd_bind_spool(1, 7)
        again = self.start()
        shown = again.cached_spools()
        self.assertEqual([s["id"] for s in shown["spools"]], [7, 9, 11])
        self.assertEqual(shown["bindings"], {"1": 7})
        self.assertTrue(shown["stale"])
        again.cmd_spools()
        self.assertFalse(again.cached_spools()["stale"])

    def test_bind_after_restart_does_not_read_the_list(self):
        self.svc.cmd_spools()
        again = self.start()
        calls = self.reads()
        again.cmd_bind_spool(2, 9)
        self.assertEqual(calls, [])
        self.assertEqual(again.bindings, {2: 9})

    def test_bind_of_a_spool_not_in_the_list_reads_it_once(self):
        calls = self.reads()
        self.svc.cmd_bind_spool(1, 7)    # no list held yet
        self.assertEqual(len(calls), 1)
        self.svc.cmd_bind_spool(2, 9)    # held now
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            self.svc.cmd_bind_spool(2, 999)
        self.assertEqual(len(calls), 2)

    def test_link_changes_are_saved(self):
        self.svc.cmd_spools()
        self.svc.cmd_bind_spool(1, 7)
        self.svc.cmd_bind_spool(2, 9)
        self.svc.cmd_unbind_spool(2)
        self.assertEqual(self.start().cached_spools()["bindings"], {"1": 7})

    def test_another_printer_or_spoolman_does_not_use_it(self):
        self.svc.cmd_spools()
        other = fakes.FakePrinter()
        self.addCleanup(other.close)
        self.assertEqual(self.start(host=other.host, url="http://" + other.host).cached_spools()["spools"], [])
        self.assertEqual(self.start(url="http://elsewhere:7912").cached_spools()["spools"], [])

    def test_unreadable_file_is_ignored(self):
        with open(self.path, "w") as f:
            f.write("{nope")
        self.assertEqual(self.start().cached_spools()["spools"], [])


if __name__ == "__main__":
    unittest.main()
