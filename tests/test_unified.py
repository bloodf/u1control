"""Spooler's stock in the U1 Control tab (peers.py, stockview.py) and the print ledger kept across restarts
(usage.LedgerStore). Files go to temporary folders; printers and Spoolman are in-memory or tests/fakes.py."""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import peers  # noqa: E402
import service as service_mod  # noqa: E402
import usage  # noqa: E402
from service import Service, Target  # noqa: E402
from test_corrections import FakeSpoolman, mem_service, reply  # noqa: E402

NOW = 1_800_000_000.0


def spooler_presence(session="s1", ts=NOW, state="active", pid=None, **extra):
    return {"schema": peers.SCHEMA, "version": 1, "plugin": "spooler", "plugin_version": "0.21.0", "session": session,
            "pid": os.getpid() if pid is None else pid, "started": ts - 100, "ts": ts, "state": state,
            "provides": {"stock": 1}, "spoolman": {"origin": "http://box:7912", "source": "spoolman"}, **extra}


def stock_doc(session="s1", gen=3, ts=NOW, url="http://box:7912", spools=None, **extra):
    return {"schema": peers.STOCK_SCHEMA, "version": 1, "session": session, "seq": 1, "ts": ts,
            "origin": {"url": url, "gen": gen, "source": "spoolman"}, "low_stock_grams": 100,
            "spools": spools if spools is not None else [
                {"id": 7, "filament_id": 70, "name": "Matte Black", "vendor": "Generic", "material": "PLA",
                 "colour": "111111", "remaining": 500.0, "initial": 1000.0, "location": "Shelf A", "low": False},
                {"id": 11, "filament_id": 110, "name": "White", "vendor": "Generic", "material": "PETG",
                 "colour": "#FAFAFA", "remaining": 40.0, "location": "", "low": True, "use_first": True}], **extra}


class Root:
    """An OrcaSlicer data folder with Spooler's files in it."""

    def __init__(self, test):
        self.path = tempfile.mkdtemp(prefix="peers-")
        test.addCleanup(shutil.rmtree, self.path, ignore_errors=True)

    def write(self, name, doc, plugin="spooler"):
        folder = Path(self.path, plugin)
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")

    def read(self, plugin="u1control"):
        return json.loads(Path(self.path, plugin, peers.PRESENCE_FILE).read_text(encoding="utf-8"))


class PresenceStatusTests(unittest.TestCase):
    def test_only_a_fresh_active_file_of_this_process_counts(self):
        cases = [
            (None, "absent"),
            ({**spooler_presence(), "schema": "x"}, "incompatible"),
            ({**spooler_presence(), "version": 2}, "incompatible"),
            ({**spooler_presence(), "plugin": "u1control"}, "incompatible"),
            ({**spooler_presence(), "session": ""}, "incompatible"),
            ({**spooler_presence(), "ts": "now"}, "incompatible"),
            (spooler_presence(pid=os.getpid() + 1), "other_process"),
            (spooler_presence(state="stopped"), "stopped"),
            (spooler_presence(ts=NOW - peers.FRESH - 1), "stale"),
            (spooler_presence(ts=NOW + 60), "stale"),
            (spooler_presence(), "active"),
        ]
        for doc, want in cases:
            self.assertEqual(peers.peer_status(doc, NOW)[0], want, doc)

    def test_origins_are_compared_without_credentials_case_or_default_port(self):
        self.assertEqual(peers.normalize_origin("HTTP://User:pw@Box:7912/"), "http://box:7912")
        self.assertEqual(peers.normalize_origin("box:80"), "http://box")
        self.assertEqual(peers.normalize_origin("https://box:443/spoolman/"), "https://box/spoolman")
        for bad in ("", None, "ftp://box", "http://", "http://box:99999"):
            self.assertEqual(peers.normalize_origin(bad), "", bad)


class StockParseTests(unittest.TestCase):
    def test_rows_are_checked_and_keyed_to_the_running_spooler(self):
        bad_rows = [{"id": 0}, {"id": True}, {"id": "7"}, "x", {"id": 5, "colour": "red", "remaining": "lots", "name": 3}]
        parsed = peers.parse_stock(stock_doc(spools=bad_rows + stock_doc()["spools"]), {"session": "s1"}, NOW)
        self.assertEqual(parsed["state"], "ok")
        self.assertEqual(parsed["key"], "s1:3")
        self.assertEqual([r["id"] for r in parsed["rows"]], [5, 7, 11])
        self.assertEqual(parsed["rows"][0], {**parsed["rows"][0], "colour": None, "remaining": None, "name": ""})
        self.assertEqual(parsed["rows"][1]["colour"], "#111111")
        self.assertEqual(parsed["origin"], "http://box:7912")

    def test_old_run_other_source_errors_and_age(self):
        self.assertEqual(peers.parse_stock(stock_doc(session="old"), {"session": "s1"}, NOW)["state"], "mismatch")
        other = stock_doc()
        other["origin"]["source"] = "bambu"
        self.assertEqual(peers.parse_stock(other, {"session": "s1"}, NOW)["state"], "error")
        self.assertIn("couldn't read", peers.parse_stock(stock_doc(error="HTTP 500"), {"session": "s1"}, NOW)["text"])
        self.assertEqual(peers.parse_stock({**stock_doc(), "version": 9}, {"session": "s1"}, NOW)["state"], "error")
        stale = peers.parse_stock(stock_doc(ts=NOW - peers.STOCK_STALE - 1), {"session": "s1"}, NOW)
        self.assertEqual((stale["state"], len(stale["rows"])), ("stale", 2))   # still shown, marked

    def test_every_stock_state_carries_a_reason_code_for_the_page(self):
        other = stock_doc()
        other["origin"]["source"] = "bambu"
        cases = [(None, "waiting"), ({**stock_doc(), "version": 9}, "format"), (stock_doc(session="old"), "earlier_run"),
                 (other, "not_spoolman"), (stock_doc(error="HTTP 500"), "spoolman_error"),
                 ({**stock_doc(), "spools": "x"}, "no_list"), (stock_doc(ts=NOW - peers.STOCK_STALE - 1), "stale"),
                 (stock_doc(), "ok")]
        for doc, code in cases:
            with self.subTest(code=code):
                self.assertEqual(peers.parse_stock(doc, {"session": "s1"}, NOW)["code"], code)
        self.assertEqual(peers.parse_stock(stock_doc(error="HTTP 500"), {"session": "s1"}, NOW)["detail"], "HTTP 500")


class PresenceFileTests(unittest.TestCase):
    def test_start_publishes_wants_and_stop_says_stopped(self):
        root = Root(self)
        link = peers.SpoolerLink(root.path, "1.2.3", log=lambda m: None)
        link.presence.heartbeat = 0.05
        link.presence.start()
        first = root.read()
        self.assertEqual((first["state"], first["plugin"], first["pid"], first["plugin_version"]),
                         ("active", "u1control", os.getpid(), "1.2.3"))
        link.want_stock(refresh=True)
        deadline = time.time() + 3
        while time.time() < deadline and root.read()["wants"]["stock_request"] != 1:
            time.sleep(0.02)
        self.assertEqual(root.read()["wants"]["stock_request"], 1)
        self.assertGreater(root.read()["wants"]["stock_until"], time.time())
        link.presence.stop()
        last = root.read()
        self.assertEqual((last["state"], last["session"]), ("stopped", first["session"]))
        self.assertNotIn("wants", last)

    def test_a_new_load_is_a_new_session(self):
        root = Root(self)
        a = peers.SpoolerLink(root.path, log=lambda m: None)
        b = peers.SpoolerLink(root.path, log=lambda m: None)
        self.assertNotEqual(a.presence.session, b.presence.session)

    def test_unwritable_folder_is_logged_once_and_never_raises(self):
        logs = []
        presence = peers.Presence(os.path.join(Root(self).path, "file"), log=logs.append)
        Path(presence.root).write_text("not a folder")
        self.assertFalse(presence.write())
        self.assertFalse(presence.write())
        self.assertEqual(len(logs), 1)

    def test_data_root_from_storage(self):
        self.assertEqual(peers.data_root("/x/OrcaSlicer/orca_plugins/plugin_data/u1control"), "/x/OrcaSlicer")
        self.assertEqual(peers.data_root("/somewhere/else"), "")


class StockServiceTests(unittest.TestCase):
    """cmd_stock / cmd_stock_assign against a fake U1 + Spoolman and Spooler files in a temporary data folder."""

    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        for spool in self.fake.spools:   # filament ids, as a real Spoolman has them
            spool["filament"]["id"] = spool["id"] * 10
        self.fil = {s["id"]: s["filament"]["id"] for s in self.fake.spools}
        self.root = Root(self)
        self.link = peers.SpoolerLink(self.root.path, log=lambda m: None)
        self.pub = []
        self.svc = Service(self.pub.append, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.peers = self.link
        self.url = "http://" + self.fake.host
        self.svc.set_target(Target(self.fake.host, spoolman_url=self.url))
        self.svc.cmd_connect()

    def publish(self, session="s1", url=None, spools=None, **kw):
        now = time.time()
        self.root.write(peers.PRESENCE_FILE, {**spooler_presence(session, now), "spoolman": {"origin": url or self.url}})
        rows = spools if spools is not None else [
            {"id": sid, "filament_id": fid, "name": "x", "vendor": "v", "material": "PLA"} for sid, fid in self.fil.items()]
        self.root.write(peers.STOCK_FILE, stock_doc(session, ts=now, url=url or self.url, spools=rows, **kw))

    def test_without_spooler_the_view_says_so_and_nothing_can_be_assigned(self):
        view = self.svc.cmd_stock()
        self.assertEqual((view["spooler"]["state"], view["stock"]["state"], view["stock"]["rows"]), ("absent", "unavailable", []))
        with self.assertRaises(ValueError):
            self.svc.cmd_stock_assign(1, 7, "s1:3")
        self.assertEqual(self.fake.scripts, [])

    def test_a_presence_left_on_disk_is_not_a_running_spooler(self):
        self.publish()
        doc = json.loads(Path(self.root.path, "spooler", peers.PRESENCE_FILE).read_text())
        for stale in ({**doc, "ts": time.time() - 3600}, {**doc, "state": "stopped"}, {**doc, "pid": os.getpid() + 7}):
            self.root.write(peers.PRESENCE_FILE, stale)
            view = self.svc.cmd_stock()
            self.assertNotEqual(view["spooler"]["state"], "active", stale)
            self.assertEqual(view["stock"]["rows"], [])

    def test_view_lists_spooler_stock_with_same_spoolman_and_who_books_use(self):
        self.publish()
        view = self.svc.cmd_stock(refresh=True)
        self.assertEqual(view["spooler"]["state"], "active")
        self.assertEqual(sorted(r["id"] for r in view["stock"]["rows"]), sorted(self.fil))
        self.assertTrue(view["same_spoolman"])
        self.assertEqual(view["usage"], "u1control")
        self.assertEqual(self.link.stock_request, 1)            # refresh asks Spooler for a new list
        self.assertNotIn("session", view["spooler"])

    def test_assign_links_through_u1controls_own_bind(self):
        self.publish()
        key = self.svc.cmd_stock()["stock"]["key"]
        result = self.svc.cmd_stock_assign(1, 7, key)
        self.assertEqual(result["bindings"], {"1": 7})
        self.assertTrue(any(s.startswith("SET_PRINT_FILAMENT_CONFIG CONFIG_EXTRUDER=1") for s in self.fake.scripts))
        self.assertEqual({s["id"]: s["location"] for s in self.fake.spools}[7], "Snapmaker U1 T2")

    def test_assign_refuses_a_list_from_before_a_spooler_restart_or_source_change(self):
        self.publish(session="s1")
        key = self.svc.cmd_stock()["stock"]["key"]
        self.publish(session="s2")                       # Spooler reloaded meanwhile
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_stock_assign(1, 7, key)
        self.assertIn("changed", str(e.exception))
        self.assertEqual(self.fake.scripts, [])

    def test_assign_refuses_another_spoolman(self):
        self.publish(url="http://other-box:7912")
        key = self.svc.cmd_stock()["stock"]["key"]
        self.assertFalse(self.svc.cmd_stock()["same_spoolman"])
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_stock_assign(1, 7, key)
        self.assertIn("isn't the one Spooler uses", str(e.exception))
        self.assertEqual(self.fake.scripts, [])

    def test_assign_checks_the_spool_in_u1controls_spoolman(self):
        self.publish(spools=[{"id": 7, "filament_id": 999, "name": "x", "material": "PLA"},
                             {"id": 4242, "filament_id": 1, "name": "y", "material": "PLA"}])
        key = self.svc.cmd_stock()["stock"]["key"]
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_stock_assign(1, 7, key)
        self.assertIn("another filament", str(e.exception))
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_stock_assign(1, 4242, key)
        self.assertIn("isn't in the Spoolman", str(e.exception))
        self.assertEqual(self.fake.scripts, [])

    def test_assign_for_a_printer_no_longer_selected_is_refused_before_anything(self):
        self.publish()
        key = self.svc.cmd_stock()["stock"]["key"]
        gen = self.svc.generation
        other = fakes.FakePrinter()
        self.addCleanup(other.close)
        self.svc.set_target(Target(other.host, spoolman_url=self.url))
        self.svc.submit(5, "stock_assign", {"head": 1, "spool_id": 7, "key": key}, gen)
        self.assertEqual(reply(self.pub, 5)["error"], service_mod.STALE)
        self.assertEqual((self.fake.scripts, other.scripts), ([], []))

    def test_assign_keeps_the_busy_check(self):
        self.publish()
        key = self.svc.cmd_stock()["stock"]["key"]
        base = self.fake.status
        self.fake.status = lambda: {**base(), "machine_state_manager": {"main_state": "BED_LEVELING"}}
        with self.assertRaises(service_mod.PrinterError):
            self.svc.cmd_stock_assign(1, 7, key)
        self.assertEqual(self.fake.scripts, [])

    def test_through_the_printer_the_origin_is_unknown_and_identity_decides(self):
        self.publish()
        with mock.patch.object(self.svc, "_origin_check", return_value=None):
            key = self.svc.cmd_stock()["stock"]["key"]
            self.assertEqual(self.svc.cmd_stock_assign(2, 11, key)["bindings"], {"2": 11})

    def test_bad_arguments(self):
        for args in ((1, 0, "k"), (1, True, "k"), (1, "7", "k"), (1, 7, ""), (1, 7, None)):
            with self.assertRaises(ValueError, msg=args):
                self.svc.cmd_stock_assign(*args)

    def test_lease_with_stock_keeps_spooler_refreshing(self):
        self.svc.touch(stock=True)
        self.assertGreater(self.link.stock_until, time.time())
        self.assertEqual(self.link.stock_request, 0)


class LedgerFileTests(unittest.TestCase):
    """The ledger survives a restart (a new Service on the same file) without booking anything twice."""

    def setUp(self):
        FakeSpoolman.uses, FakeSpoolman.fail_on, FakeSpoolman.spools_list, FakeSpoolman.via_moonraker = [], set(), [], False
        patcher = mock.patch.object(service_mod.sm, "Spoolman", FakeSpoolman)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = tempfile.mkdtemp(prefix="ledger-")
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.path = os.path.join(self.folder, "usage_ledger.json")

    def start(self):
        """A new OrcaSlicer session: a Service reading the same ledger file."""
        with mock.patch.object(threading.Thread, "start", lambda t: None):   # no tracker thread; driven by hand
            svc = Service(self.pub.append, log=self.logs.append, client_factory=__import__("test_corrections").MemClient,
                          ledger_path=self.path)
        svc.set_target(Target("printer-A", "key-A", spoolman_url="http://box:7912"))
        svc.firmware = {"kind": "stock", "version": ""}
        svc.bindings = {0: 7, 1: 9}
        return svc

    def setUpSession(self):
        self.pub, self.logs = [], []

    def remember(self, svc):
        return svc.remember_job("part.gcode", {0: 0, 1: 1}, [{"index": 0, "weight": 2.0}, {"index": 1, "weight": 3.0}])

    def observe(self, svc, *samples):
        for state, name in samples:
            for job, outcome in svc.ledger.observe(svc.target.ident, state, name):
                svc._settle(job, outcome)

    def saved(self):
        return json.loads(Path(self.path).read_text(encoding="utf-8"))

    def test_job_is_on_disk_without_the_api_key_and_identifies_printer_spoolman_and_file(self):
        self.setUpSession()
        svc = self.start()
        job = self.remember(svc)
        saved = self.saved()["jobs"][0]
        self.assertEqual((saved["id"], saved["host"], saved["path"], saved["spoolman_url"]),
                         (job.id, svc.target.ident, "part.gcode", "http://box:7912"))
        self.assertNotIn("key-A", Path(self.path).read_text())

    def test_printing_through_a_restart_is_booked_once(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        self.setUpSession()
        svc = self.start()                                   # OrcaSlicer restarted mid-print
        self.assertEqual(svc.ledger.pending()[0].api_key, "key-A")   # key comes from the settings, not the file
        self.observe(svc, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(sorted(FakeSpoolman.uses), [(7, 2.0), (9, 3.0)])
        self.assertEqual(self.saved()["jobs"], [])
        self.setUpSession()
        svc = self.start()
        self.observe(svc, ("complete", "part.gcode"))
        self.assertEqual(len(FakeSpoolman.uses), 2)          # nothing booked again after another restart

    def test_finished_while_closed_is_unconfirmed_not_booked(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        self.setUpSession()
        svc = self.start()
        self.observe(svc, ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])
        self.assertEqual([u["error"] for u in svc.ledger.unconfirmed],
                         ["printing before OrcaSlicer closed; how it ended wasn't seen"] * 2)
        self.assertTrue(any("before OrcaSlicer closed" in m["text"] for m in self.pub if m.get("type") == "notice"))
        self.assertEqual(self.saved()["unconfirmed"][0]["job"], svc.ledger.unconfirmed[0]["job"])

    def test_acknowledging_an_unconfirmed_use_is_local_audited_and_survives_a_restart(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        self.setUpSession()
        svc = self.start()
        self.observe(svc, ("complete", "part.gcode"))
        view = svc.cmd_usage()
        self.assertEqual(len(view["unconfirmed"]), 2)
        first = view["unconfirmed"][0]
        for field in ("id", "at", "head", "grams", "file", "printer", "spool", "job"):
            self.assertIn(field, first)                       # identity the page shows for checking in Spoolman
        uses_before = list(FakeSpoolman.uses)
        after = svc.cmd_usage_ack(first["id"])
        self.assertEqual(FakeSpoolman.uses, uses_before)      # acknowledging never calls Spoolman
        self.assertEqual([u["id"] for u in after["unconfirmed"]], [view["unconfirmed"][1]["id"]])
        self.assertEqual(after["acknowledged"][-1]["id"], first["id"])
        self.assertIn("acknowledged_at", after["acknowledged"][-1])
        self.assertEqual(self.saved()["acknowledged"][-1]["id"], first["id"])   # kept in the file for audit
        with self.assertRaises(ValueError):
            svc.cmd_usage_ack(first["id"])                    # twice: refused, nothing changes
        self.setUpSession()
        svc = self.start()
        self.assertEqual([u["id"] for u in svc.ledger.unconfirmed], [view["unconfirmed"][1]["id"]])
        self.assertEqual(svc.ledger.acknowledged[-1]["id"], first["id"])

    def test_acknowledge_that_cannot_be_saved_changes_nothing(self):
        self.setUpSession()
        svc = self.start()
        svc.ledger.unconfirmed_use({"id": "u1", "at": 1.0, "spool": 7, "grams": 2.0, "head": 0, "file": "a.gcode"})
        with mock.patch.object(usage.LedgerStore, "save", side_effect=OSError("disk full")):
            with self.assertRaises(ValueError):
                svc.cmd_usage_ack("u1")
        self.assertEqual([u["id"] for u in svc.ledger.unconfirmed], ["u1"])
        self.assertEqual(svc.ledger.acknowledged, [])

    def test_a_call_in_flight_at_a_crash_is_never_sent_again(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))

        def crash(sid, grams):
            raise SystemExit("OrcaSlicer died during the Spoolman call")
        with mock.patch.object(FakeSpoolman, "use_weight", side_effect=crash):
            with self.assertRaises(SystemExit):
                for job, _outcome in svc.ledger.observe(svc.target.ident, "complete", "part.gcode"):
                    svc._book(job)
        on_disk = self.saved()["jobs"][0]
        self.assertEqual(on_disk["sending"], {"0": 2.0})
        self.setUpSession()
        svc = self.start()
        self.assertEqual([(u["spool"], u["grams"], u["error"]) for u in svc.ledger.unconfirmed],
                         [(7, 2.0, "OrcaSlicer closed while this was being recorded")])
        self.observe(svc, ("complete", "part.gcode"))         # T2 never sent; the end wasn't seen after restart
        self.assertEqual(FakeSpoolman.uses, [])
        self.assertEqual(len(svc.ledger.unconfirmed), 2)

    def test_timeout_is_unconfirmed_and_survives_a_restart(self):
        self.setUpSession()
        svc = self.start()
        FakeSpoolman.fail_on = {7}
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"), ("complete", "part.gcode"))
        FakeSpoolman.fail_on = set()
        self.setUpSession()
        svc = self.start()
        self.assertEqual(svc.ledger.unconfirmed[0]["spool"], 7)
        for job in svc.ledger.due(now=time.time() + usage.RETRY_AFTER + 1):   # T2 was never tried
            svc._settle(job, "book")
        self.assertEqual(FakeSpoolman.uses, [(9, 3.0)])                       # 7 is not retried

    def test_intent_not_saved_means_nothing_sent(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        with mock.patch.object(usage.LedgerStore, "save", side_effect=OSError("disk full")):
            self.observe(svc, ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])
        self.assertEqual(len(svc.ledger.pending()), 1)        # waits for a retry
        self.assertTrue(any("disk full" in m["text"] for m in self.pub if m.get("type") == "notice"))
        for job in svc.ledger.due(now=time.time() + usage.RETRY_AFTER + 1):
            svc._settle(job, "book")
        self.assertEqual(sorted(FakeSpoolman.uses), [(7, 2.0), (9, 3.0)])

    def test_unreadable_ledger_is_set_aside_not_overwritten(self):
        Path(self.path).write_text("{broken", encoding="utf-8")
        self.setUpSession()
        svc = self.start()
        self.assertTrue(any("kept as" in m for m in self.logs))
        aside = [n for n in os.listdir(self.folder) if n.startswith("usage_ledger.json.bad-")]
        self.assertEqual(len(aside), 1)
        self.assertEqual(Path(self.folder, aside[0]).read_text(), "{broken")
        self.assertEqual(svc.ledger.pending(), [])

    def test_malformed_entries_are_skipped(self):
        Path(self.path).write_text(json.dumps({"version": 1, "jobs": [{"host": "x"}, "bad"], "unconfirmed": ["x", {"spool": 1}]}))
        self.setUpSession()
        svc = self.start()
        self.assertEqual(svc.ledger.pending(), [])
        self.assertEqual(svc.ledger.unconfirmed, [{"spool": 1, "id": "legacy:None", "at": None}])   # stable id, time unknown
        self.assertIn("skipped", svc.ledger.restore_notice)
        self.assertIn("1 unreadable unconfirmed entry", svc.ledger.restore_notice)   # the bad one is reported, not silent

    def test_cancel_after_restart_books_nothing(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        self.setUpSession()
        svc = self.start()
        self.observe(svc, ("cancelled", "part.gcode"))
        self.assertEqual((FakeSpoolman.uses, svc.ledger.unconfirmed, svc.ledger.pending()), ([], [], []))

    def test_unchanged_samples_do_not_rewrite_the_file(self):
        self.setUpSession()
        svc = self.start()
        self.remember(svc)
        self.observe(svc, ("printing", "part.gcode"))
        with mock.patch.object(usage.LedgerStore, "save") as save:
            for _ in range(5):
                svc.ledger.observe(svc.target.ident, "printing", "part.gcode")
                svc.ledger.observe("another-printer", "standby", "")
        save.assert_not_called()


class StockWithMemClientTests(unittest.TestCase):
    def test_usage_owner_follows_firmware_and_settings(self):
        svc, _ = mem_service(self)
        self.assertEqual(svc._usage_owner(None), "unknown")
        svc.set_target(Target("printer-A", spoolman_report_usage=False))
        self.assertEqual(svc._usage_owner(svc.target), "off")
        svc.firmware = {"kind": "extended", "version": ""}
        self.assertEqual(svc._usage_owner(svc.target), "printer")

    def test_stock_view_never_waits_behind_a_long_command(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        svc.client.block = (entered, release)
        svc.submit(1, "gcode", {"script": "G28"})
        self.assertTrue(entered.wait(3))
        svc.submit(2, "stock", {})
        self.assertEqual(reply(pub, 2)["result"]["spooler"]["state"], "absent")


if __name__ == "__main__":
    unittest.main()
