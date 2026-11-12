"""Regressions for the 2026-11 review (F01-F14): printer isolation, Spoolman usage and links, downloads,
camera errors, busy checks, Extended Firmware settings, Spooler files and the console. Races are driven
with events and barriers, not sleeps."""

import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import extended  # noqa: E402
import files  # noqa: E402
import fakes  # noqa: E402
import service as service_mod  # noqa: E402
import spooler_bridge as sb  # noqa: E402
import spoolman as sm  # noqa: E402
import usage  # noqa: E402
from moonraker import PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import SAMPLE, wait_for  # noqa: E402


class MemClient:
    """In-memory U1: records every effect; `block` holds a gcode call until released."""
    printers = {}

    def __init__(self, host, key=""):
        self.host, self.address, self.scripts, self.calls = host, host, [], []
        self.block = None
        self.status = {"print_stats": {"state": "standby", "filename": ""}}
        MemClient.printers[host] = self

    def gcode(self, script, timeout=30):
        if self.block:
            entered, release = self.block
            entered.set()
            assert release.wait(5)
        self.scripts.append(script)

    def emergency_stop(self):
        self.calls.append("emergency_stop")
        if self.block:
            entered, release = self.block
            entered.set()
            assert release.wait(5)

    def info(self):
        return {"software_version": "2.0.0", "state": "ready"}

    def query(self, objects):
        return self.status

    def raw(self, method, path, body=None, headers=None, timeout=None):
        raise PrinterError("no firmware config")

    def request(self, method, path, params=None, json_body=None, timeout=None):
        raise PrinterError("not here")


def mem_service(test):
    MemClient.printers = {}
    pub = []
    svc = Service(pub.append, log=lambda m: None, client_factory=MemClient)
    test.addCleanup(svc.close)
    return svc, pub


def reply(pub, rid, timeout=3):
    assert wait_for(lambda: any(m.get("id") == rid for m in pub), timeout)
    return next(m for m in pub if m.get("id") == rid)


# ---------------------------------------------------------------------- F01

class TargetIsolationTests(unittest.TestCase):
    def test_queued_command_for_a_never_reaches_b(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        entered, release = threading.Event(), threading.Event()
        svc.cmd_hold = lambda: (entered.set(), release.wait(5)) and True
        svc.submit(1, "hold", {})
        self.assertTrue(entered.wait(3))
        svc.submit(2, "temperature", {"heater": "bed", "target": 60})   # confirmed while A was shown
        svc.set_target(Target("printer-B"))
        b = svc.client
        release.set()
        self.assertEqual(reply(pub, 2)["error"], service_mod.STALE)
        self.assertEqual((a.scripts, b.scripts), ([], []))

    def test_page_generation_from_before_a_switch_is_refused(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        old = svc.generation
        svc.set_target(Target("printer-B"))
        svc.submit(3, "temperature", {"heater": "bed", "target": 60}, gen=old)
        self.assertEqual(reply(pub, 3)["error"], service_mod.STALE)
        svc.submit(4, "temperature", {"heater": "bed", "target": 60}, gen=svc.generation)
        self.assertNotIn("error", reply(pub, 4))
        self.assertEqual((MemClient.printers["printer-A"].scripts, MemClient.printers["printer-B"].scripts), ([], ["M140 S60"]))

    def test_command_already_running_stops_before_its_next_effect(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        a.status = {"print_stats": {"state": "standby"}, "print_task_config": fakes.task_config()}
        entered, release = threading.Event(), threading.Event()
        original = svc._require_idle

        def idle_then_switch():
            view = original()
            entered.set()
            assert release.wait(5)
            return view
        svc._require_idle = idle_then_switch
        svc.submit(5, "load", {"head": 1})
        self.assertTrue(entered.wait(3))
        svc.set_target(Target("printer-B"))
        release.set()
        self.assertEqual(reply(pub, 5)["error"], service_mod.STALE)
        self.assertEqual((a.scripts, MemClient.printers["printer-B"].scripts), ([], []))

    def test_invalid_selection_disconnects_the_previous_printer(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        svc.clear_target()
        svc.submit(6, "temperature", {"heater": "bed", "target": 60})
        self.assertIn("no U1 selected", reply(pub, 6)["error"])
        self.assertEqual(MemClient.printers["printer-A"].scripts, [])

    def test_unreachable_new_target_drops_the_old_one(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))

        def broken(host, key=""):
            raise PrinterError("can't read printer address")
        svc.client_factory = broken
        with self.assertRaises(PrinterError):
            svc.set_target(Target("::bad::"))
        self.assertIsNone(svc.client)

    def test_plugin_hello_without_a_u1_clears_the_target(self):
        orca = fakes.install_orca(preset={"name": "Bambu X1C", "printer_model": "X1C"})
        ns = fakes.load_wheel(build_wheel())
        svc = ns["service"]()
        self.addCleanup(svc.close)
        svc.set_target(ns["Target"]("127.0.0.1:1"))
        page = ns["U1ControlPage"]()
        page.on_message({"type": "hello", "id": 1})
        self.assertIsNone(svc.client)
        reply1 = [m for m in page.posted if m.get("id") == 1][0]
        self.assertIn("Select a Snapmaker U1", reply1["error"])
        self.assertTrue(reply1["no_target"])   # the page tells "no printer" apart from "printer unreachable"
        self.assertIsNotNone(orca)

    def test_connect_reports_the_temperature_limits_the_plugin_applies(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        self.assertEqual(service_mod.HOTEND_MAX, 320)
        self.assertEqual(service_mod.BED_MAX, 110)
        sent = []
        svc._gcode = lambda script: sent.append(script) or True
        svc.cmd_temperature("0", 999)
        svc.cmd_temperature("bed", 999)
        self.assertEqual(sent, ["M104 T0 S320", "M140 S110"])
        svc.submit(41, "connect", {})
        self.assertEqual(reply(pub, 41)["result"]["limits"], {"hotend": 320, "bed": 110})

    def test_frame_and_screen_of_the_old_printer_are_dropped(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        svc.firmware = {"kind": "extended", "version": ""}
        a = svc.client

        def raw(method, path, body=None, headers=None, timeout=None):
            svc.set_target(Target("printer-B"))   # the user switched while the picture was on its way
            return (b"\xff\xd8jpeg" if "webcam" in path else b"\x89PNG\r\n\x1a\npng"), {}
        a.raw = raw
        gen = svc.generation
        with svc._bound(gen, a, svc.target):
            svc._push_frame()
        svc.set_target(Target("printer-A2"))
        svc.firmware = {"kind": "extended", "version": ""}
        svc.client.raw = raw
        with svc._bound(svc.generation, svc.client, svc.target):
            svc._push_screen()
        self.assertEqual([m["type"] for m in pub if m["type"] in ("frame", "screen")], [])

    def test_urgent_stop_goes_to_the_printer_it_was_pressed_for(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        hold, release = threading.Event(), threading.Event()
        svc.cmd_hold = lambda: hold.set() or release.wait(5)
        self.addCleanup(release.set)
        svc.submit(1, "hold", {})                 # the normal queue is busy
        self.assertTrue(hold.wait(3))
        entered, go = threading.Event(), threading.Event()
        a.block = (entered, go)
        svc.submit(7, "emergency_stop", {})
        self.assertTrue(entered.wait(3))          # running at once, beside the busy queue
        svc.set_target(Target("printer-B"))
        go.set()
        self.assertNotIn("error", reply(pub, 7))
        self.assertEqual((a.calls, MemClient.printers["printer-B"].calls), (["emergency_stop"], []))

    def test_m112_in_the_console_takes_the_urgent_path(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        svc.submit(8, "gcode", {"script": "  m112 "})
        self.assertNotIn("error", reply(pub, 8))
        self.assertEqual((svc.client.calls, svc.client.scripts), (["emergency_stop"], []))


_WHEEL = []


def build_wheel():
    if not _WHEEL:
        import build
        _WHEEL.append(str(build.build(out_dir=Path(tempfile.mkdtemp()))))
    return _WHEEL[0]


# ---------------------------------------------------------------------- F02

class FakeSpoolman:
    """Stands in for spoolman.Spoolman in _book: records use, can fail on chosen spools."""
    uses, fail_on, spools_list, via_moonraker = [], set(), [], False

    def __init__(self, url, client):
        self.via_moonraker = FakeSpoolman.via_moonraker

    def connect(self):
        return {}

    def spools(self):
        return FakeSpoolman.spools_list

    def use_weight(self, sid, grams):
        if sid in FakeSpoolman.fail_on:
            raise sm.SpoolmanError("timed out")
        FakeSpoolman.uses.append((sid, grams))


class UsageLedgerTests(unittest.TestCase):
    def setUp(self):
        FakeSpoolman.uses, FakeSpoolman.fail_on, FakeSpoolman.spools_list, FakeSpoolman.via_moonraker = [], set(), [], False
        patcher = mock.patch.object(service_mod.sm, "Spoolman", FakeSpoolman)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.svc, self.pub = mem_service(self)
        self.svc.set_target(Target("printer-A"))
        self.svc.firmware = {"kind": "stock", "version": ""}
        self.svc.bindings = {0: 7, 1: 9}

    def remember(self, name="part.gcode", heads=((0, 2.0), (1, 3.0)), **kw):
        return self.svc.remember_job(name, {i: t for i, (t, _) in enumerate(heads)},
                                     [{"index": i, "weight": g} for i, (_, g) in enumerate(heads)], **kw)

    def observe(self, host, *samples):
        for state, name in samples:
            for job, outcome in self.svc.ledger.observe(host, state, name):
                self.svc._settle(job, outcome)

    def notices(self):
        return [m["text"] for m in self.pub if m.get("type") == "notice"]

    def test_printed_then_complete_books_once_per_head(self):
        self.remember()
        host = self.svc.target.ident
        self.observe(host, ("complete", "part.gcode"), ("printing", "part.gcode"), ("complete", "part.gcode"),
                     ("complete", "part.gcode"))
        self.assertEqual(sorted(FakeSpoolman.uses), [(7, 2.0), (9, 3.0)])

    def test_finish_without_seeing_it_print_is_reported_not_booked(self):
        self.remember()
        self.observe(self.svc.target.ident, ("standby", ""), ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])
        self.assertEqual(len(self.svc.ledger.unconfirmed), 2)
        self.assertTrue(any("never saw it printing" in t for t in self.notices()))
        self.assertEqual(self.svc.ledger.pending(), [])

    def test_failed_call_is_not_repeated_and_untried_heads_wait(self):
        FakeSpoolman.fail_on = {7}
        job = self.remember()
        host = self.svc.target.ident
        self.observe(host, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])
        self.assertEqual(self.svc.ledger.unconfirmed[-1]["spool"], 7)
        self.assertTrue(any("won't repeat" in t for t in self.notices()))
        self.assertEqual(job.per_head, {1: 3.0})                 # T2 was never tried: still pending
        FakeSpoolman.fail_on = set()
        for ready in self.svc.ledger.due(now=time.time() + usage.RETRY_AFTER + 1):
            self.svc._settle(ready, "book")
        self.assertEqual(FakeSpoolman.uses, [(9, 3.0)])           # and spool 7 is not charged again
        self.assertEqual(self.svc.ledger.pending(), [])

    def test_spoolman_unreachable_before_any_write_keeps_the_job(self):
        job = self.remember()
        with mock.patch.object(FakeSpoolman, "connect", side_effect=sm.SpoolmanError("down")):
            self.observe(self.svc.target.ident, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(self.svc.ledger.pending(), [job])
        self.assertEqual(job.per_head, {0: 2.0, 1: 3.0})

    def test_jobs_belong_to_their_printer(self):
        self.remember()                      # sent to A with A's spools
        a = self.svc.target.ident
        self.svc.set_target(Target("printer-C"))
        self.svc.firmware = {"kind": "stock", "version": ""}
        self.svc.bindings = {0: 99}
        self.observe(self.svc.target.ident, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])                   # C printing a file of the same name
        self.observe(a, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(sorted(FakeSpoolman.uses), [(7, 2.0), (9, 3.0)])

    def test_same_name_in_another_folder_is_not_this_job(self):
        self.remember("jobs/part.gcode")
        self.observe(self.svc.target.ident, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])

    def test_spools_linked_when_sent_are_charged(self):
        self.remember()
        self.svc.bindings = {0: 50, 1: 51}   # relinked during the print
        self.observe(self.svc.target.ident, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(sorted(FakeSpoolman.uses), [(7, 2.0), (9, 3.0)])

    def test_extended_and_moonraker_accounting_are_not_charged_again(self):
        self.svc.firmware = {"kind": "extended", "version": ""}
        self.assertIsNone(self.remember())
        self.svc.firmware = {"kind": "stock", "version": ""}
        FakeSpoolman.via_moonraker = True
        self.remember()
        self.observe(self.svc.target.ident, ("printing", "part.gcode"), ("complete", "part.gcode"))
        self.assertEqual(FakeSpoolman.uses, [])

    def test_two_observers_book_a_job_once(self):
        self.remember()
        host = self.svc.target.ident
        self.svc.ledger.observe(host, "printing", "part.gcode")
        barrier, results = threading.Barrier(2), []

        def look():
            barrier.wait(3)
            results.extend(self.svc.ledger.observe(host, "complete", "part.gcode"))
        threads = [threading.Thread(target=look) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(3)
        self.assertEqual([o for _, o in results], ["book"])


class UsageWithoutPageTests(unittest.TestCase):
    def test_job_is_followed_and_booked_without_the_page(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.spools[0]["location"] = "Bench U1 T2"
        with mock.patch.object(usage, "JOB_POLL", 0.1):
            pub = []
            svc = Service(pub.append, log=lambda m: None)
            self.addCleanup(svc.close)
            svc.remember_job("a.gcode", {0: 1}, [{"index": 0, "weight": 4.0}], host=fake.host,
                             options={"printer_name": "Bench U1", "spoolman_url": "http://" + fake.host})
            self.assertIsNone(svc.client)      # the page never opened
            fake.state = "printing"
            self.assertTrue(wait_for(lambda: svc.ledger.pending()[0].armed, 5))
            fake.state = "complete"
            self.assertTrue(wait_for(lambda: fake.uses, 5))
        self.assertEqual(fake.uses, [(7, {"use_weight": 4.0})])

    def test_tracker_skips_extended_firmware(self):
        fake = fakes.FakePrinter(extended=True, version="2.0.0.205-paxx12")
        self.addCleanup(fake.close)
        fake.spools[0]["location"] = "Snapmaker U1 T1"
        with mock.patch.object(usage, "JOB_POLL", 0.1):
            svc = Service(lambda m: None, log=lambda m: None)
            self.addCleanup(svc.close)
            svc.remember_job("a.gcode", {0: 0}, [{"index": 0, "weight": 4.0}], host=fake.host,
                             options={"spoolman_url": "http://" + fake.host})
            fake.state = "printing"
            self.assertTrue(wait_for(lambda: svc.ledger.pending()[0].armed, 5))
            fake.state = "complete"
            self.assertTrue(wait_for(lambda: not svc.ledger.pending(), 5))
        self.assertEqual(fake.uses, [])


# ---------------------------------------------------------------------- F03

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.pub = []
        self.svc = Service(self.pub.append, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host, spoolman_url="http://" + self.fake.host))
        self.svc.cmd_connect()
        self.svc.cmd_bind_spool(1, 7)
        self.assertEqual(self.svc.bindings, {1: 7})

    def locations(self):
        return {s["id"]: s["location"] for s in self.fake.spools}

    def test_rejected_head_write_changes_nothing(self):
        self.svc.client.gcode = mock.Mock(side_effect=PrinterError("printer said: refused"))
        with self.assertRaises(PrinterError):
            self.svc.cmd_bind_spool(1, 11)
        self.assertEqual(self.svc.bindings, {1: 7})
        self.assertEqual(self.locations()[7], "Snapmaker U1 T2")
        self.assertEqual(self.locations()[11], "")

    def test_spoolman_failure_after_the_head_write_is_reported_and_reloaded(self):
        real = sm.Spoolman.set_location

        def fail_new(smc, sid, loc):
            if sid == 11:
                raise sm.SpoolmanError("Spoolman said HTTP 500")
            return real(smc, sid, loc)
        with mock.patch.object(sm.Spoolman, "set_location", fail_new):
            with self.assertRaises(sm.SpoolmanError) as e:
                self.svc.cmd_bind_spool(1, 11)
        self.assertIn("T2 now shows that filament", str(e.exception))
        self.assertEqual(self.svc.bindings, {1: 7})            # what Spoolman says, not what was intended

    def test_old_location_left_behind_is_named(self):
        real = sm.Spoolman.set_location

        def fail_clear(smc, sid, loc):
            if sid == 7 and loc == "":
                raise sm.SpoolmanError("Spoolman said HTTP 500")
            return real(smc, sid, loc)
        with mock.patch.object(sm.Spoolman, "set_location", fail_clear):
            with self.assertRaises(sm.SpoolmanError) as e:
                self.svc.cmd_bind_spool(1, 11)
        self.assertIn("spool #7 still lists T2", str(e.exception))

    def test_empty_inventory_clears_links_and_a_failed_read_keeps_them(self):
        with mock.patch.object(sm.Spoolman, "spools", side_effect=sm.SpoolmanError("down")):
            with self.assertRaises(sm.SpoolmanError):
                self.svc.cmd_spools()
        self.assertEqual(self.svc.bindings, {1: 7})
        self.fake.spools = []
        self.assertEqual(self.svc.cmd_spools()["bindings"], {})

    def test_unbind_keeps_the_link_when_spoolman_refuses(self):
        with mock.patch.object(sm.Spoolman, "set_location", side_effect=sm.SpoolmanError("down")):
            with self.assertRaises(sm.SpoolmanError):
                self.svc.cmd_unbind_spool(1)
        self.assertEqual(self.svc.bindings, {1: 7})
        self.assertEqual(self.svc.cmd_unbind_spool(1)["bindings"], {})


# ---------------------------------------------------------------------- F04

class DownloadPublishTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        patcher = mock.patch.object(files.os.path, "expanduser", lambda p: self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = os.path.join(self.home, "Downloads", "u1control")

    def service(self, payload):
        with mock.patch.object(threading.Thread, "start", lambda self: None):
            svc = Service(lambda m: None, log=lambda m: None)

        class Client:
            def download_to(self, path, open_out):
                with open_out() as f:
                    f.write(payload())
        svc._client = lambda: Client()
        return svc

    def test_two_downloads_of_one_name_both_survive(self):
        barrier, results = threading.Barrier(2), []
        real = files._publish

        def together(src, folder, name):
            barrier.wait(3)      # both are about to pick the final name at the same moment
            return real(src, folder, name)
        svc = self.service(lambda: threading.current_thread().name.encode())
        with mock.patch.object(files, "_publish", together):
            threads = [threading.Thread(target=lambda: results.append(svc.cmd_download("camera/same.mp4")), name=n)
                       for n in ("download-A", "download-B")]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
        self.assertEqual(len(set(results)), 2)
        self.assertEqual(sorted(Path(p).read_text() for p in results), ["download-A", "download-B"])
        self.assertEqual(sorted(os.listdir(self.folder)), ["same (1).mp4", "same.mp4"])

    def test_a_file_another_program_creates_meanwhile_is_not_replaced(self):
        real_link = os.link

        def racing_link(src, dst):
            if dst.endswith("clip.mp4") and not os.path.exists(dst):
                Path(dst).write_text("someone else")
            return real_link(src, dst)
        svc = self.service(lambda: b"ours")
        with mock.patch.object(files.os, "link", racing_link):
            saved = svc.cmd_download("camera/clip.mp4")
        self.assertEqual(Path(self.folder, "clip.mp4").read_text(), "someone else")
        self.assertEqual((os.path.basename(saved), Path(saved).read_text()), ("clip (1).mp4", "ours"))

    def test_without_hard_links_the_name_is_reserved_first(self):
        Path(self.folder).mkdir(parents=True)
        Path(self.folder, "v.mp4").write_text("old")
        svc = self.service(lambda: b"new")
        with mock.patch.object(files.os, "link", side_effect=PermissionError("no hard links")):
            saved = svc.cmd_download("camera/v.mp4")
        self.assertEqual(Path(self.folder, "v.mp4").read_text(), "old")
        self.assertEqual(Path(saved).read_text(), "new")
        self.assertFalse([n for n in os.listdir(self.folder) if n.endswith(".part")])


# ---------------------------------------------------------------------- F05

class CameraErrorTests(unittest.TestCase):
    def test_camera_failures_do_not_hold_up_status(self):
        with mock.patch.object(threading.Thread, "start", lambda self: None):
            svc = Service(lambda m: out.append(m), log=lambda m: None, client_factory=MemClient)
        out, clock, counts = [], [0.0], {"status": 0, "frame": 0}
        svc.set_target(Target("printer-A"))
        svc.lease_until, svc.camera_on = 1e9, True
        svc._frame_due = lambda: True
        svc._push_status = lambda: counts.__setitem__("status", counts["status"] + 1)

        def frame():
            counts["frame"] += 1
            raise PrinterError("camera unavailable")
        svc._push_frame = frame

        def sleep(n):
            clock[0] += n
            if clock[0] >= 10:
                svc.closed = True
        with mock.patch.object(service_mod.time, "monotonic", lambda: clock[0]), \
                mock.patch.object(service_mod.time, "sleep", sleep):
            svc._watch()
        self.assertGreaterEqual(counts["status"], 5)                 # every STATUS_EVERY, as without a camera
        self.assertLessEqual(counts["frame"], 10 / service_mod.CAMERA_RETRY + 1)
        self.assertEqual({m["type"] for m in out}, {"camera_error"})  # never "offline"


# ---------------------------------------------------------------------- F06 / F12

def with_machine(fake, state="IDLE"):
    base = fake.status
    fake.status = lambda: {**base(), "machine_state_manager": {"main_state": state}}


class BusyAndTagTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host, spoolman_url="http://" + self.fake.host))
        self.svc.cmd_connect()

    def test_guided_commands_refuse_a_busy_machine(self):
        with_machine(self.fake, "BED_LEVELING")
        for cmd, args in (("cmd_load", (1,)), ("cmd_unload", (1,)), ("cmd_preferences", ({"bed_level": True},)),
                          ("cmd_set_filament", (1, "Generic", "PLA", "#FFFFFF")), ("cmd_bind_spool", (1, 7))):
            with self.assertRaises(PrinterError, msg=cmd):
                getattr(self.svc, cmd)(*args)
        self.assertEqual(self.fake.scripts, [])
        self.svc.cmd_temperature(0, 200)      # adjustments stay allowed
        self.assertEqual(self.fake.scripts, ["M104 T0 S200"])

    def test_tag_needs_confirmation_and_is_checked_right_before_writing(self):
        self.fake.tags[1] = {"VENDOR": "Polymaker", "MAIN_TYPE": "PLA", "RGB_1": 0x112233, "COLOR_NUMS": 1}
        with self.assertRaises(PrinterError):
            self.svc.cmd_set_filament(1, "Generic", "PLA", "#FFFFFF")
        with self.assertRaises(PrinterError):
            self.svc.cmd_bind_spool(1, 7)     # confirmed as untagged, but a tag arrived since
        self.assertEqual(self.fake.scripts, [])
        self.svc.cmd_set_filament(1, "Generic", "PLA", "#FFFFFF", force=True)
        self.assertTrue(self.fake.scripts[-1].endswith("FORCE=1"))

    def test_unload_when_done_says_where_to_set_it(self):
        with self.assertRaises(ValueError) as e:
            self.svc.cmd_preferences({"unload_when_done": True})
        self.assertIn("print setup pop-up", str(e.exception))


class PrintSetupRecheckTests(unittest.TestCase):
    def run_setup(self, during_dialog):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        with_machine(fake)
        orca = fakes.install_orca(answer={"map": {}, "prefs": {}, "purifier": "auto"})
        ns = fakes.load_wheel(build_wheel())
        self.addCleanup(lambda: ns["service"]().close())
        create = orca.host.ui.create_window

        def window(*a, **kw):
            during_dialog(fake)
            return create(*a, **kw)
        orca.host.ui.create_window = window
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        Path(path).write_text(SAMPLE)
        before = Path(path).read_text()
        ctx = types.SimpleNamespace(step="post", gcode_path=path, host="OctoPrint", output_name="part.gcode",
                                    config_value=lambda k: {"print_host": fake.host}.get(k, ""))
        result = ns["U1PrintSetup"]().execute(ctx)
        return result, fake, before == Path(path).read_text()

    def test_machine_busy_after_the_dialog_sends_nothing(self):
        result, fake, untouched = self.run_setup(lambda f: with_machine(f, "BED_LEVELING"))
        self.assertEqual(result.status, "failure")
        self.assertIn("became busy", result.message)
        self.assertEqual(fake.scripts, [])
        self.assertTrue(untouched)

    def test_toolhead_changed_after_the_dialog_sends_nothing(self):
        def swap(f):
            f.task["filament_type"] = ["PETG", "PETG", "NONE", "PLA"]
        result, fake, _ = self.run_setup(swap)
        self.assertEqual(result.status, "failure")
        self.assertIn("T1 changed", result.message)
        self.assertEqual(fake.scripts, [])

    def test_unchanged_printer_still_sends_and_registers_the_job(self):
        result, fake, _ = self.run_setup(lambda f: None)
        self.assertEqual(result.status, "success", result.message)
        self.assertEqual(len(fake.scripts), 1)


# ---------------------------------------------------------------------- F07 / F08

class ExtendedContractTests(unittest.TestCase):
    def test_release_settings_are_normalized(self):
        groups = extended.normalize_settings(fakes.ext_settings())
        self.assertEqual([g["id"] for g in groups], ["web", "remote_access", "snapmaker_components"])
        spoolman = groups[2]["items"][0]
        self.assertEqual([o["value"] for o in spoolman["options"]], ["enabled", "disabled", "legacy"])
        self.assertEqual(spoolman["options"][0]["inputs"][0]["name"], "SPOOLMAN_URL")
        self.assertTrue(spoolman["options"][0]["confirm"].startswith("Enable Spoolman"))
        self.assertTrue(spoolman["options"][2]["hidden"])
        self.assertTrue(groups[2]["items"][1]["hidden"])

    def test_other_shapes_are_refused(self):
        for bad in ([{"id": "ssh", "options": ["true"]}], {"web": {"items": [{"id": "ssh", "options": ["a"]}]}},
                    {"web": {"items": "x"}}, {"web": {"items": [{"id": "BAD ID", "options": {}}]}}):
            with self.assertRaises(PrinterError):
                extended.normalize_settings(bad)

    def test_only_a_success_marker_means_applied(self):
        self.assertTrue(extended._outcome(b"Applying\n\nSUCCESS: Setting updated successfully\n")["ok"])
        for log in (b"Applying changes...\n", b"", b"=== Updating SSH ===\nSetting: Enabled"):
            self.assertIsNone(extended._outcome(log)["ok"], log)
        for log in (b"x\nERROR: Command completed with exit code 1\n", b"x\n\nError: boom\n"):
            with self.assertRaises(PrinterError):
                extended._outcome(log)

    def test_inputs_are_checked_before_sending(self):
        sent = []
        e = extended.Extended(types.SimpleNamespace(raw=lambda *a, **k: sent.append(a) or (b"SUCCESS: ok\n", {})))
        for bad in ({"spoolman_url": "x"}, {"SPOOLMAN_URL": 5}, {"SPOOLMAN_URL": "x" * 600}, ["SPOOLMAN_URL"]):
            with self.assertRaises(PrinterError):
                e.set("spoolman", "enabled", bad)
        self.assertEqual(sent, [])
        self.assertTrue(e.set("spoolman", "enabled", {"SPOOLMAN_URL": "http://h:7912"})["ok"])


# ---------------------------------------------------------------------- F09

class ThumbnailQueueTests(unittest.TestCase):
    def test_thumbnails_never_hold_up_commands(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def slow_thumb(rel):
            entered.set()
            assert release.wait(5)
            return b"png"
        a.thumbnail = slow_thumb
        svc.submit(1, "thumbnail", {"path": "gcodes/a.gcode", "thumb": ".thumbs/a.png"})
        self.assertTrue(entered.wait(3))
        for rid in range(2, 2 + service_mod.THUMB_QUEUE):
            svc.submit(rid, "thumbnail", {"path": "gcodes/a.gcode", "thumb": ".thumbs/a.png"})
        svc.submit(99, "thumbnail", {"path": "gcodes/a.gcode", "thumb": ".thumbs/a.png"})
        self.assertIn("too many", reply(pub, 99)["error"])        # bounded, not 500 tasks
        svc.submit(100, "temperature", {"heater": "bed", "target": 50})
        self.assertNotIn("error", reply(pub, 100, 2))             # while the thumbnail is still stuck
        self.assertEqual(a.scripts, ["M140 S50"])

    def test_listing_thumb_is_used_and_checked(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        a.thumbnail = lambda rel: rel.encode()
        a.metadata = mock.Mock()
        self.assertTrue(svc.cmd_thumbnail("gcodes/sub/a.gcode", ".thumbs/a-300x300.png").startswith("data:image/png"))
        a.metadata.assert_not_called()
        for bad in ("../x.png", "/etc/x.png", ".thumbs/a.gcode"):
            with self.assertRaises(ValueError):
                svc.cmd_thumbnail("gcodes/a.gcode", bad)


# ---------------------------------------------------------------------- F13

class SpoolerContractTests(unittest.TestCase):
    def test_profiles_of_another_shape_fall_back(self):
        for bad in ({"version": 1, "filaments": [42]}, {"version": 2, "filaments": {"42": {"Snapmaker U1": "p"}}},
                    {"filaments": {"42": {"Snapmaker U1": "p"}}}, {"version": 1, "filaments": {"42": ["p"]}},
                    {"version": 1, "filaments": {"42": {"Snapmaker U1": 7}}}, {"version": True, "filaments": {}}):
            self.assertIsNone(sb.profile_lookup(bad, 42, "Snapmaker U1"), bad)
        self.assertIn("version", sb.profiles_problem({"version": 2, "filaments": {}}))
        presets = [{"name": "Elegoo PLA Red @U1", "vendor": "Elegoo", "colour": "#FF0000", "bundle_id": "spooler"}]
        spool = {"filament_id": 42, "vendor": "Elegoo", "material": "PLA", "colour": "#FF0000"}
        self.assertEqual(sb.preset_for_spool(presets, spool, {"version": 1, "filaments": [42]}, "Snapmaker U1"),
                         "Elegoo PLA Red @U1")

    def test_keep_slots_marker_shapes(self):
        now = 1000
        self.assertTrue(sb.keep_slots_active({"active": True, "printer": "Snapmaker U1", "ts": now}, now, ["Snapmaker U1"]))
        self.assertFalse(sb.keep_slots_active({"active": True, "printer": "Other", "ts": now}, now, ["Snapmaker U1"]))
        # no printer named: unknown target, so the automatic sync pauses (documented, conservative)
        self.assertTrue(sb.keep_slots_active({"active": True, "ts": now}, now, ["Snapmaker U1"]))
        for bad in ({"active": "yes", "ts": now}, {"active": True, "ts": "1000"}, {"active": True, "ts": True},
                    {"active": True, "ts": now - 31}, [1], None):
            self.assertFalse(sb.keep_slots_active(bad, now, ["Snapmaker U1"]), bad)


# ---------------------------------------------------------------------- F14

class ConsoleTests(unittest.TestCase):
    def test_replies_since_the_command_are_returned_and_bounded(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        a = svc.client
        store = [{"message": "old", "time": 10.0, "type": "response"}]

        def request(method, path, params=None, json_body=None, timeout=None):
            self.assertEqual(path, "/server/gcode_store")
            return {"gcode_store": store[-params["count"]:]}

        def gcode(script, timeout=30):
            store.extend([{"message": script, "time": 11.0, "type": "command"},
                          {"message": "ok T0:21.0 /0.0", "time": 11.1, "type": "response"}]
                         + [{"message": "x" * 100, "time": 12.0, "type": "response"}] * 60)
        a.request, a.gcode = request, gcode
        result = svc.cmd_gcode("M105")
        self.assertEqual(result["output"][0], "ok T0:21.0 /0.0")
        self.assertNotIn("old", result["output"])
        self.assertLessEqual(sum(len(x) for x in result["output"]), service_mod.CONSOLE_MAX_CHARS + 60)
        self.assertTrue(result["output"][-1].startswith("…"))

    def test_without_the_reply_log_the_limit_is_said(self):
        svc, pub = mem_service(self)
        svc.set_target(Target("printer-A"))
        result = svc.cmd_gcode("M105")
        self.assertEqual(svc.client.scripts, ["M105"])
        self.assertEqual(result["output"], [])
        self.assertIn("unavailable", result["note"])


if __name__ == "__main__":
    unittest.main()
