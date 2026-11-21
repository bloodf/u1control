"""Requirements u1control can't install: OrcaSlicer's printer agents preference, the U1 Extended Firmware and
Spoolman. Each is found, missing or unknown; nothing is checked at import or while the plugin registers, and
what needs a missing one stays off without retrying. Fakes only; nothing here talks to a real U1."""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "u1control")
sys.path[:0] = [SRC, os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import requirements as req  # noqa: E402
import service as service_mod  # noqa: E402
import spoolman as sm  # noqa: E402
import u1  # noqa: E402
from moonraker import PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402


def fresh_plugin(selected_printer=None):
    """plugin.py loaded anew (its session flags start clean) against a fake orca; selected_printer: the host call."""
    orca = fakes.install_orca()
    if selected_printer is not None:
        orca.host.selected_printer = selected_printer
    spec = importlib.util.spec_from_file_location("u1control_plugin_req", os.path.join(SRC, "plugin.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return orca, module


def status(items, rid):
    return next(i for i in items if i["id"] == rid)


class CheckTests(unittest.TestCase):
    def test_printer_agents(self):
        self.assertEqual(req.printer_agents(True)["status"], "ok")
        self.assertEqual(req.printer_agents(False)["status"], "unknown")   # can't read the preference: never "missing"

    def test_extended_firmware(self):
        self.assertEqual(req.extended_firmware({"kind": "extended", "version": "v1.2-paxx12"}),
                         {"id": req.EXTENDED, "status": "ok", "details": {"version": "v1.2-paxx12"}})
        self.assertEqual(req.extended_firmware({"kind": "stock", "version": "1.0"})["status"], "missing")
        self.assertEqual(req.extended_firmware({"kind": "unknown", "version": ""})["status"], "unknown")
        self.assertEqual(req.extended_firmware(None)["status"], "unknown")

    def test_spoolman(self):
        self.assertEqual(req.spoolman("http://box:7912", ""), {"id": req.SPOOLMAN, "status": "ok",
                                                               "details": {"url": "http://box:7912", "via": "direct"}})
        self.assertEqual(req.spoolman("", "moonraker"), {"id": req.SPOOLMAN, "status": "ok", "details": {"via": "printer"}})
        self.assertEqual(req.spoolman("", "none")["status"], "missing")
        self.assertEqual(req.spoolman("", "")["status"], "unknown")   # not tried yet: no probe of its own

    def test_spooler(self):
        self.assertEqual(req.spooler({"installed": True, "url": "https://x"}), {"id": req.SPOOLER, "status": "ok", "details": {"url": "https://x"}})
        self.assertEqual(req.spooler({"installed": False})["status"], "missing")
        self.assertEqual(req.spooler(None)["status"], "missing")

    def test_check_lists_all_four(self):
        self.assertEqual([i["id"] for i in req.check(False, None, "", "")], [req.PRINTER_AGENTS, req.EXTENDED, req.SPOOLMAN, req.SPOOLER])


class PrinterAgentDetectionTests(unittest.TestCase):
    def test_selected_printer_with_our_agent(self):
        for answer in ({"agent": "u1control", "connection": "lan"}, types.SimpleNamespace(agent="u1control"),
                       {"agent": {"id": "u1control"}}):
            _, plugin = fresh_plugin(lambda a=answer: a)
            self.assertTrue(plugin.printer_agents_on(), answer)

    def test_not_detected(self):
        def boom():
            raise RuntimeError("not allowed here")
        for call in (lambda: None, lambda: {"agent": "moonraker"}, boom):
            _, plugin = fresh_plugin(call)
            self.assertFalse(plugin.printer_agents_on())

    def test_answer_is_cached_until_check_again(self):
        calls = []
        _, plugin = fresh_plugin(lambda: calls.append(1) or None)
        plugin.printer_agents_on()
        plugin.printer_agents_on()
        self.assertEqual(len(calls), 1)
        plugin.printer_agents_on(recheck=True)
        self.assertEqual(len(calls), 2)

    def test_orcaslicer_connecting_through_the_agent_counts(self):
        orca, plugin = fresh_plugin(lambda: None)
        self.assertFalse(plugin.printer_agents_on())
        agent = plugin.U1Agent()
        with mock.patch.object(plugin.threading, "Thread"):   # no status thread: nothing to reach
            agent.connect_printer(orca.printer_agent.PrinterConnectionParams(dev_id="u1", host="127.0.0.1:1"))
        self.assertTrue(plugin.printer_agents_on())


class NoCheckAtLoadTests(unittest.TestCase):
    def test_import_and_register_ask_nothing(self):
        def forbidden():
            raise AssertionError("selected_printer() called at import/register")
        orca, plugin = fresh_plugin(forbidden)
        with mock.patch.object(req, "check", side_effect=AssertionError("checked at register")):
            plugin.U1Control().register_capabilities()
        self.assertIn(plugin.U1Agent, orca.registered)
        self.assertIsNone(plugin._agent_selected)


class PageMessageTests(unittest.TestCase):
    def test_page_asks_and_check_again_rechecks(self):
        calls = []
        _, plugin = fresh_plugin(lambda: calls.append(1) or {"agent": "u1control"})
        page = plugin.U1ControlPage()
        self.addCleanup(page.on_unload)
        page.on_message({"type": "requirements"})
        items = page.posted[-1]["items"]
        self.assertEqual(page.posted[-1]["type"], "requirements")
        self.assertEqual(status(items, req.PRINTER_AGENTS)["status"], "ok")
        self.assertEqual(status(items, req.EXTENDED)["status"], "unknown")   # no printer connected
        self.assertEqual(status(items, req.SPOOLMAN)["status"], "unknown")
        page.on_message({"type": "requirements"})
        self.assertEqual(len(calls), 1)
        page.on_message({"type": "requirements", "recheck": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(page.posted[-1]["type"], "config")   # a recheck also refreshes the Spooler hints
        self.assertEqual(status(page.posted[-2]["items"], req.SPOOLER)["status"], "missing")
        self.assertFalse(any(m.get("type") == "config" for m in page.posted[:-1]))   # a plain ask posts no config

    def test_spoolman_url_in_settings_is_enough(self):
        _, plugin = fresh_plugin(lambda: None)
        page = plugin.U1ControlPage()
        self.addCleanup(page.on_unload)
        page._settings().update({"spoolman_url": "http://box:7912"})
        page.on_message({"type": "requirements"})
        self.assertEqual(status(page.posted[-1]["items"], req.SPOOLMAN)["details"]["url"], "http://box:7912")


class ServiceTests(unittest.TestCase):
    def make(self, fake, **target):
        svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host, **target))
        return svc

    def printer(self, **kw):
        fake = fakes.FakePrinter(**kw)
        self.addCleanup(fake.close)
        return fake

    def test_no_spoolman_anywhere_is_missing_and_spool_commands_say_why(self):
        svc = self.make(self.printer(spoolman=False))
        with self.assertRaises(sm.SpoolmanError):
            svc.cmd_spools()
        self.assertEqual(svc.spoolman_link, "none")
        self.assertEqual(req.spoolman("", svc.spoolman_link)["status"], "missing")

    def test_spoolman_through_the_printer_is_found(self):
        fake = self.printer(spoolman=True)
        svc = self.make(fake)
        svc._spoolman()   # the connect alone: the fake has no proxy, only /server/spoolman/status
        self.assertEqual(svc.spoolman_link, "moonraker")
        self.assertEqual(req.spoolman("", svc.spoolman_link)["details"], {"via": "printer"})

    def test_new_printer_forgets_the_link(self):
        svc = self.make(self.printer(spoolman=False))
        with self.assertRaises(sm.SpoolmanError):
            svc.cmd_spools()
        svc.set_target(Target(self.printer().host))
        self.assertEqual(svc.spoolman_link, "")

    def test_no_printer_answer_leaves_the_link_unknown(self):
        svc = self.make(self.printer(spoolman=False))
        with mock.patch.object(svc.client, "request", side_effect=PrinterError("can't reach the U1")):
            with self.assertRaises(sm.SpoolmanError):
                svc._spoolman()
        self.assertEqual(svc.spoolman_link, "")   # offline is not "no Spoolman"
        self.assertEqual(req.spoolman("", svc.spoolman_link)["status"], "unknown")

    def test_clear_printer_answers(self):
        def gone(*a, **k):
            e = PrinterError("printer said: not found")
            e.status = 404
            raise e
        for answer, want in ((lambda *a, **k: {"spoolman_connected": False}, False), (gone, False),
                             (lambda *a, **k: {"spoolman_connected": True}, True)):
            mr = mock.Mock()
            mr.request.side_effect = answer
            smc = sm.Spoolman("", mr)
            try:
                smc.connect()
            except sm.SpoolmanError:
                pass
            self.assertIs(smc.printer_spoolman, want)
        mr = mock.Mock()
        mr.request.side_effect = PrinterError("timed out")
        smc = sm.Spoolman("", mr)
        with self.assertRaises(sm.SpoolmanError):
            smc.connect()
        self.assertIsNone(smc.printer_spoolman)

    def test_follow_waits_while_the_u1_is_busy(self):
        """Automatic follow never writes a head mid-print or mid-load; the change goes once the U1 is idle."""
        fake = self.printer()
        svc = self.make(fake, spoolman_url="http://127.0.0.1:1")
        with svc.lock:
            svc.firmware = {"kind": "stock", "version": "1.0"}
        view = u1.summarize(fake.status())
        changed = dict(view, heads=[dict(h, type="PETG", colour="#000000", official=False) for h in view["heads"]],
                       rfid=[None] * u1.TOOLHEADS)
        svc._spoolman_follow(view, svc.generation)
        with mock.patch.object(svc, "cmd_spools", side_effect=sm.SpoolmanError("x")) as spools:
            svc._spoolman_follow(dict(changed, state="printing"), svc.generation)
            svc._spoolman_follow(dict(changed, machine_state="AUTO_LOAD"), svc.generation)
            self.assertEqual(spools.call_count, 0)
            svc._spoolman_follow(changed, svc.generation)   # idle again: the pending change goes
            self.assertEqual(spools.call_count, 1)

    def test_follow_backs_off_and_retries(self):
        fake = self.printer()
        svc = self.make(fake, spoolman_url="http://127.0.0.1:1")
        with svc.lock:
            svc.firmware = {"kind": "stock", "version": "1.0"}
        notices = []
        svc._notice = lambda text, gen=None: notices.append(text)
        view = u1.summarize(fake.status())
        changed = dict(view, heads=[dict(h, type="PETG", colour="#000000") for h in view["heads"]],
                       rfid=[None] * u1.TOOLHEADS)
        for h in changed["heads"]:
            h["official"] = False
        svc._spoolman_follow(view, svc.generation)    # first view: nothing to compare yet
        now = [1000.0]
        calls = []

        def spools():
            calls.append(now[0])
            raise sm.SpoolmanError("can't reach Spoolman")
        with mock.patch.object(service_mod.time, "monotonic", lambda: now[0]), \
                mock.patch.object(svc, "cmd_spools", side_effect=spools):
            svc._spoolman_follow(changed, svc.generation)
            self.assertEqual((len(calls), svc.follow_wait), (1, 30.0))
            svc._spoolman_follow(changed, svc.generation)   # inside the back-off: no retry
            self.assertEqual(len(calls), 1)
            now[0] += 31
            svc._spoolman_follow(changed, svc.generation)   # the pending change is retried
            self.assertEqual((len(calls), svc.follow_wait), (2, 60.0))
            for _ in range(6):
                now[0] += 301
                svc._spoolman_follow(changed, svc.generation)
            self.assertEqual(svc.follow_wait, 300.0)   # capped at 5 min
        self.assertEqual(len(notices), 1)   # said once, not on every retry
        now[0] += 301
        with mock.patch.object(service_mod.time, "monotonic", lambda: now[0]), \
                mock.patch.object(svc, "cmd_spools", return_value=None):
            svc._spoolman_follow(changed, svc.generation)
        self.assertEqual((svc.follow_wait, svc.follow_retry_at), (0.0, 0.0))   # works again: back-off reset

    def test_extended_only_commands_refuse_on_stock(self):
        svc = self.make(self.printer())
        with svc.lock:
            svc.firmware = {"kind": "stock", "version": "1.0"}
        for call in (svc.cmd_ext_settings, lambda: svc.cmd_ext_set("x", "y"), lambda: svc.cmd_ext_action("x")):
            with self.assertRaisesRegex(PrinterError, "Extended Firmware"):
                call()

    def test_stock_firmware_starts_no_screen_work(self):
        published = []
        svc = Service(published.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(self.printer().host))
        with svc.lock:
            svc.firmware = {"kind": "stock", "version": "1.0"}
            svc.client = mock.Mock()
        svc._push_screen()
        svc.client.raw.assert_not_called()
        self.assertEqual(published, [])   # no screen_error either


if __name__ == "__main__":
    unittest.main()
