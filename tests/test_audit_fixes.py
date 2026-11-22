"""Regression tests for the 2026-11 audit: malformed printer / Spoolman answers, the monitor thread, the
websocket error path of the emergency stop, download names and firmware detection in Check U1 connection."""

import base64
import hashlib
import io
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import fakes  # noqa: E402
import files  # noqa: E402
import moonraker  # noqa: E402
import service as service_mod  # noqa: E402
import spoolman as sm  # noqa: E402
import u1  # noqa: E402
import usage  # noqa: E402
import extended as ext  # noqa: E402
from moonraker import Moonraker, PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import wait_for  # noqa: E402


class _GarbageServer:
    """Answers every connection with bytes that are not HTTP (http.client raises BadStatusLine)."""

    def __init__(self, test):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        test.addCleanup(self.sock.close)
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def host(self):
        return "127.0.0.1:%d" % self.sock.getsockname()[1]

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.recv(4096)
                conn.sendall(b"garbage\r\n\r\n")


class MalformedHttpTests(unittest.TestCase):
    def test_non_http_answer_is_a_printer_error(self):
        client = Moonraker(_GarbageServer(self).host, timeout=2)
        with self.assertRaises(PrinterError):
            client.raw("GET", "/screen/snapshot")
        with self.assertRaises(PrinterError):
            client.request("GET", "/printer/info")


class SpoolNamesTests(unittest.TestCase):
    def test_names_of_linked_spools_for_the_followed_printer_only(self):
        svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(svc.close)
        self.assertEqual(svc.spool_names("10.0.0.5"), {})                      # no printer followed
        svc.set_target(Target("http://10.0.0.5/"))
        svc.spools = [{"id": 7, "vendor": "Acme", "name": "Cobalt", "colour": "#2850A8", "remaining": 250, "initial": 1000},
                      {"id": 8, "vendor": "", "name": "Basic"}]
        svc.bindings = {1: 7, 2: 8, 3: 99}                                       # 99: not in the list
        self.assertEqual(svc.spool_names("10.0.0.5"), {
            "1": {"name": "Acme Cobalt", "colour": "#2850A8", "colours": [], "remaining": 250, "initial": 1000, "pa": {}},
            "2": {"name": "Basic", "colour": None, "colours": [], "remaining": None, "initial": None, "pa": {}}})
        self.assertEqual(svc.spool_names("10.0.0.6"), {})                      # another U1


class MonitorTests(unittest.TestCase):
    def test_remote_screen_failure_never_stops_the_monitor(self):
        fake = fakes.FakePrinter(extended=True)
        self.addCleanup(fake.close)
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        real_raw = svc.client.raw

        def raw(method, path, *a, **k):
            if path.startswith(service_mod.EXT_SCREEN):
                raise RuntimeError("unexpected answer")
            return real_raw(method, path, *a, **k)
        svc.client.raw = raw
        svc.touch(screen=True)
        self.assertTrue(wait_for(lambda: any(m.get("type") == "screen_error" for m in pub)))
        self.assertTrue(svc.monitor.is_alive())
        seen = len([m for m in pub if m.get("type") == "status"])
        self.assertTrue(wait_for(lambda: (svc.touch() or True) and
                                 len([m for m in pub if m.get("type") == "status"]) > seen, timeout=6))


class SpoolmanAnswerTests(unittest.TestCase):
    @staticmethod
    def opener(body):
        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Opener:
            def open(self, req, timeout=None):
                return Resp(body)
        return Opener()

    def test_non_json_answer_is_a_spoolman_error(self):
        smc = sm.Spoolman("http://spoolman.invalid", opener=self.opener(b"<html>proxy login</html>"))
        with self.assertRaises(sm.SpoolmanError):
            smc.spools()

    def test_proxy_error_that_is_not_an_object(self):
        class Mr:
            def request(self, *a, **k):
                return {"error": "spoolman unreachable", "response": None}
        smc = sm.Spoolman("", Mr())
        smc.via_moonraker = True
        with self.assertRaises(sm.SpoolmanError) as cm:
            smc.spools()
        self.assertIn("spoolman unreachable", str(cm.exception))


class RfidParseTests(unittest.TestCase):
    def test_malformed_tag_fields_do_not_break_the_status(self):
        info = [{"MAIN_TYPE": "PLA", "COLOR_NUMS": "x", "RGB_1": 0xFF0000, "CARD_UID": ["a", None]},
                {"MAIN_TYPE": "PETG", "COLOR_NUMS": None, "CARD_UID": [1, 2, 3, 4]}]
        tags = u1.rfid_tags({"info": info})
        self.assertEqual(tags[0]["type"], "PLA")
        self.assertEqual(tags[0]["colours"], ["#FF0000"])
        self.assertEqual(tags[1]["uid"], "01020304")
        u1.summarize({"filament_detect": {"info": info}})   # must not raise


class _WsServer:
    """One websocket answer over a socketpair: reads the client's handshake and request, replies with `reply(id)`."""

    def __init__(self, test, reply):
        self.client, self.server = socket.socketpair()
        test.addCleanup(self.client.close)
        test.addCleanup(self.server.close)
        self.reply = reply
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        head, rest = moonraker._read_handshake(self.server)
        key = next(l.split(b":", 1)[1].strip() for l in head.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key:"))
        accept = base64.b64encode(hashlib.sha1(key + moonraker.WS_GUID).digest())
        self.server.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                            b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
        req = json.loads(moonraker._ws_recv(moonraker._Reader(self.server, rest)))
        payload = json.dumps(self.reply(req["id"])).encode()
        self.server.sendall(struct.pack("!BB", 0x81, len(payload)) + payload)


class EmergencyStopTests(unittest.TestCase):
    def test_websocket_error_that_is_not_an_object_falls_back_to_m112(self):
        ws = _WsServer(self, lambda rid: {"jsonrpc": "2.0", "id": rid, "error": "Klippy not ready"})
        client = Moonraker("127.0.0.1:1", timeout=2)
        sent = []
        client.gcode = lambda script, timeout=30: sent.append(script) or "ok"
        with mock.patch.object(moonraker.socket, "create_connection", lambda *a, **k: ws.client):
            client.emergency_stop()
        self.assertEqual(sent, ["M112"])


class DownloadNameTests(unittest.TestCase):
    def test_printer_file_names_stay_inside_the_download_folder(self):
        for given, want in (("camera/D:evil.mp4", "D_evil.mp4"), ("camera/a\\..\\..\\x.mp4", "a_.._.._x.mp4"),
                            ("camera/t.mp4", "t.mp4"), ("camera/..", "download"), ("camera/a\x01b.mp4", "a_b.mp4")):
            with self.subTest(given=given):
                self.assertEqual(files._local_name(given), want)

    def test_download_uses_the_safe_name(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.files["camera/D:t.mp4"] = b"data"
        home = tempfile.mkdtemp()
        pub = []
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
            svc = Service(pub.append, log=lambda m: None)
            self.addCleanup(svc.close)
            svc.set_target(Target(fake.host))
            svc.submit(1, "download", {"path": "camera/D:t.mp4"})
            self.assertTrue(wait_for(lambda: any(m.get("id") == 1 for m in pub)))
        saved = next(m for m in pub if m.get("id") == 1)["result"]
        self.assertEqual(saved, os.path.join(home, "Downloads", "u1control", "D_t.mp4"))


class ExtendedActionTests(unittest.TestCase):
    def run_action(self, state, action):
        fake = fakes.FakePrinter(extended=True, state=state)
        self.addCleanup(fake.close)
        pub, posted = [], []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        svc.firmware = {"kind": "extended", "version": ""}
        real_raw = svc.client.raw
        svc.client.raw = lambda method, path, *a, **k: (posted.append(path) if method == "POST" else None) or \
            real_raw(method, path, *a, **k)
        svc.submit(1, "ext_action", {"action_id": action})
        self.assertTrue(wait_for(lambda: any(m.get("id") == 1 for m in pub)))
        return next(m for m in pub if m.get("id") == 1), posted

    def test_restart_and_reboot_refused_while_printing(self):
        for action in ("restart-klipper", "reboot-system"):
            with self.subTest(action=action):
                reply, posted = self.run_action("printing", action)
                self.assertIn("busy", reply.get("error", ""))
                self.assertEqual(posted, [])

    def test_moonraker_restart_and_idle_actions_still_go_through(self):
        for state, action in (("printing", "restart-moonraker"), ("standby", "restart-klipper")):
            with self.subTest(state=state, action=action):
                _, posted = self.run_action(state, action)
                self.assertEqual(posted, ["/firmware-config/api/action/" + action])


class FirmwareRedetectTests(unittest.TestCase):
    """The retry is made due by setting firmware_retry_at, never by sleeping: on a slow runner two status reads
    can take longer than a short FIRMWARE_RETRY, and time.monotonic() ticks every ~15.6 ms on Windows."""

    def service(self, fake):
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        return svc, pub

    @staticmethod
    def shown(pub):
        return [m["data"]["firmware"]["kind"] for m in pub if m.get("type") == "status"][-1]

    def test_slow_firmware_config_api_on_first_connect_is_corrected(self):
        fake = fakes.FakePrinter(version="1.2.0", extended=True)   # Extended, but not in the version text
        self.addCleanup(fake.close)
        fake.ext_error = 503   # the API didn't answer properly yet
        svc, pub = self.service(fake)
        svc._push_status()
        self.assertEqual((svc.firmware["kind"], self.shown(pub)), ("stock", "stock"))
        fake.ext_error = None
        svc._push_status()   # too soon (FIRMWARE_RETRY is 30 s): not asked again yet
        self.assertEqual(svc.firmware["kind"], "stock")
        svc.firmware_retry_at = 0.0   # the retry is due
        svc._push_status()
        self.assertEqual((svc.firmware["kind"], self.shown(pub)), ("extended", "extended"))
        probes = fake.ext_probes
        svc.firmware_retry_at = 0.0
        svc._push_status()
        self.assertEqual(fake.ext_probes, probes)   # sure now: no more probes

    def test_a_sure_stock_answer_is_not_asked_again(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        svc, pub = self.service(fake)
        svc._push_status()
        probes = fake.ext_probes
        svc.firmware_retry_at = 0.0
        svc._push_status()
        self.assertEqual(fake.ext_probes, probes)
        self.assertEqual(self.shown(pub), "stock")

    def test_no_answer_never_turns_extended_back_into_stock(self):
        fake = fakes.FakePrinter(version="1.2.0", extended=True)
        self.addCleanup(fake.close)
        svc, pub = self.service(fake)
        svc._push_status()
        self.assertEqual(svc.firmware["kind"], "extended")
        fake.ext_error = 503
        svc.cmd_connect()   # the page reconnects while the API is down
        self.assertEqual(svc.firmware["kind"], "extended")
        svc._status_failed(svc.generation)   # the printer went offline and came back
        svc._push_status()
        self.assertEqual((svc.firmware["kind"], self.shown(pub)), ("extended", "extended"))

    def test_reconnect_after_offline_detects_a_reflashed_printer(self):
        fake = fakes.FakePrinter(version="1.2.0", extended=True)
        self.addCleanup(fake.close)
        svc, pub = self.service(fake)
        svc._push_status()
        fake.extended = False   # flashed back to the official firmware while it was off
        svc._push_status()
        self.assertEqual(svc.firmware["kind"], "extended")   # sure, and nothing happened since
        svc._status_failed(svc.generation)
        svc._push_status()
        self.assertEqual((svc.firmware["kind"], self.shown(pub)), ("stock", "stock"))

    def test_usage_booking_waits_while_the_firmware_is_unknown(self):
        fake = fakes.FakePrinter(version="1.2.0", extended=True)
        self.addCleanup(fake.close)
        fake.ext_error = 503
        svc = Service(lambda m: None, log=lambda m: None)
        self.addCleanup(svc.close)
        job = usage.Job(usage.printer_ident(fake.host), "", "a.gcode", {0: 1.0})
        with self.assertRaises(PrinterError):   # booking it now could book it twice (SpoolLink books too)
            svc._job_on_extended(job, Moonraker(fake.host))
        fake.ext_error = None
        self.assertTrue(svc._job_on_extended(job, Moonraker(fake.host)))


class ExtendedSettingTests(unittest.TestCase):
    def run_set(self, state, setting_id, value="true"):
        fake = fakes.FakePrinter(extended=True, state=state)
        self.addCleanup(fake.close)
        pub, posted = [], []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        svc.firmware = {"kind": "extended", "version": ""}
        real_raw = svc.client.raw
        svc.client.raw = lambda method, path, *a, **k: (posted.append(path) if method == "POST" else None) or \
            real_raw(method, path, *a, **k)
        svc.submit(1, "ext_set", {"setting_id": setting_id, "value": value})
        self.assertTrue(wait_for(lambda: any(m.get("id") == 1 for m in pub)))
        return next(m for m in pub if m.get("id") == 1), posted

    def test_settings_that_restart_klipper_or_reboot_wait_for_the_print(self):
        for state in ("printing", "paused"):
            for setting_id in ("spoolman", "camera-internal", "rfid", "a-setting-of-a-newer-release"):
                with self.subTest(state=state, setting_id=setting_id):
                    reply, posted = self.run_set(state, setting_id)
                    self.assertIn("would end the print", reply.get("error", ""))
                    self.assertEqual(posted, [])

    def test_settings_that_leave_klipper_alone_apply_while_printing(self):
        for setting_id in ("remote-screen", "ssh", "camera-usb"):
            with self.subTest(setting_id=setting_id):
                reply, posted = self.run_set("printing", setting_id)
                self.assertTrue(reply["result"]["ok"], reply)
                self.assertEqual(posted, ["/firmware-config/api/settings/%s/true" % setting_id])

    def test_any_setting_applies_when_idle(self):
        reply, posted = self.run_set("standby", "spoolman", "disabled")
        self.assertEqual(posted, ["/firmware-config/api/settings/spoolman/disabled"])

    def test_settings_say_whether_they_can_change_during_a_print(self):
        items = {i["id"]: i for g in ext.normalize_settings(fakes.ext_settings()) for i in g["items"]}
        self.assertTrue(items["remote-screen"]["print_safe"])
        self.assertTrue(items["ssh"]["print_safe"])
        self.assertFalse(items["spoolman"]["print_safe"])
        self.assertFalse(items["debug-only"]["print_safe"])   # unknown: treated as one that restarts Klipper


class FileListingTests(unittest.TestCase):
    def service(self, fake):
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        return svc, pub

    def test_malformed_entries_are_skipped(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.listing = {"dirs": [{"dirname": None}, {"dirname": "ok"}, {}, "x"],
                        "files": [{"filename": 5}, {"filename": "a.gcode", "modified": "x"}, {"filename": "b.gcode", "modified": 3}, None]}
        svc, _ = self.service(fake)
        listing = svc.cmd_files("gcodes")
        self.assertEqual([d["name"] for d in listing["dirs"]], ["ok"])
        self.assertEqual([f["name"] for f in listing["files"]], ["b.gcode", "a.gcode"])

    def test_move_never_replaces_a_file_of_the_same_name(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.listing = {"dirs": [{"dirname": "sub"}], "files": [{"filename": "a.gcode"}]}
        svc, _ = self.service(fake)
        with self.assertRaises(ValueError):
            svc.cmd_move("gcodes/sub/a.gcode", "gcodes")
        self.assertEqual(fake.moved, [])
        self.assertEqual(svc.cmd_move("gcodes/sub/c.gcode", "gcodes"), {"path": "gcodes/c.gcode"})


class PrintSetupAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=__import__("pathlib").Path(tempfile.mkdtemp())))

    def test_true_is_not_toolhead_t2(self):
        import test_u1control
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        with open(path, "w") as f:
            f.write(test_u1control.SAMPLE)
        fakes.install_orca(answer={"map": {"0": True}, "prefs": {}, "purifier": "auto"})
        ns = fakes.load_wheel(self.artifact)
        ctx = type("Ctx", (), {"step": "post", "gcode_path": path, "host": "OctoPrint", "output_name": "part.gcode",
                               "config_value": staticmethod(lambda k: {"print_host": fake.host}.get(k, ""))})()
        result = ns["U1PrintSetup"]().execute(ctx)
        self.assertEqual(result.status, "success", result.message)
        self.assertIn("CONFIG_EXTRUDER=0 MAP_EXTRUDER=0", fake.scripts[-1])


class CheckConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=__import__("pathlib").Path(tempfile.mkdtemp())))

    def test_extended_firmware_without_paxx12_in_the_version(self):
        fake = fakes.FakePrinter(version="1.2.0", extended=True)   # found through the Firmware Config API only
        self.addCleanup(fake.close)
        fakes.install_orca(preset={"print_host": fake.host})
        ns = fakes.load_wheel(self.artifact)
        result = ns["CheckConnection"]().execute()
        self.assertEqual(result.status, "success", result.message)
        self.assertIn("Extended Firmware", result.message)


if __name__ == "__main__":
    unittest.main()
