"""Regression tests for the code-review fixes (urgent commands, RFID safety, races, websocket, build)."""

import http.server
import json
import os
import runpy
import socket
import struct
import subprocess
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

import fakes  # noqa: E402
import gcode  # noqa: E402
import moonraker  # noqa: E402
import service as service_mod  # noqa: E402
import u1  # noqa: E402
from moonraker import Moonraker, PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import SAMPLE, wait_for  # noqa: E402


def make_service(test, fake, **target):
    pub = []
    svc = Service(pub.append, log=lambda m: None)
    test.addCleanup(svc.close)
    svc.set_target(Target(fake.host, **target))
    return svc, pub


def call(test, svc, pub, cmd, **args):
    rid = len(pub) + 5000
    svc.submit(rid, cmd, args)
    test.assertTrue(wait_for(lambda: any(m.get("id") == rid for m in pub)))
    return next(m for m in pub if m.get("id") == rid)


class UrgentTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)

    def test_estop_not_queued_behind_slow_command(self):
        svc, pub = make_service(self, self.fake)
        release = threading.Event()
        svc.cmd_slow = lambda: release.wait(10)
        self.addCleanup(release.set)
        svc.submit(1, "slow", {})
        time.sleep(0.2)
        calls = []
        svc.client.ws_call = lambda method, params=None, timeout=None: calls.append(method) or {"result": "ok"}
        started = time.monotonic()
        svc.submit(2, "emergency_stop", {})
        self.assertTrue(wait_for(lambda: any(m.get("id") == 2 for m in pub), 2))
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(calls, ["printer.emergency_stop"])
        self.assertEqual(self.fake.scripts, [])   # websocket worked: no M112 needed
        self.assertFalse(any(m.get("id") == 1 for m in pub))   # the slow job still holds the worker

    def test_estop_falls_back_to_m112(self):
        svc, pub = make_service(self, self.fake)
        svc.client.ws_call = mock.Mock(side_effect=PrinterError("no websocket"))
        self.assertNotIn("error", call(self, svc, pub, "emergency_stop"))
        self.assertEqual(self.fake.scripts, ["M112"])

    def test_pause_and_cancel_are_urgent(self):
        self.assertTrue({"pause", "cancel", "emergency_stop"} <= set(service_mod.URGENT))


class SpoolSafetyTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)

    def test_auto_follow_skips_official_and_tagged_heads(self):
        svc, pub = make_service(self, self.fake, spoolman_url="http://" + self.fake.host)
        svc.touch()
        self.assertTrue(wait_for(lambda: svc.last_view is not None))
        writes, patches = len(self.fake.scripts), len(self.fake.patches)
        self.fake.task["filament_color_rgba"][0] = "EE1111FF"   # head 0 is an official spool
        self.fake.task["filament_color_rgba"][3] = "EE1111FF"   # head 3 carries a third-party tag
        self.fake.tags[3] = {"VENDOR": "Polymaker", "MAIN_TYPE": "PLA", "RGB_1": 0xEE1111, "COLOR_NUMS": 1}
        end = time.time() + 5
        while time.time() < end:
            svc.touch()
            time.sleep(0.3)
        self.assertEqual((len(self.fake.scripts), len(self.fake.patches)), (writes, patches))
        self.assertEqual(svc.bindings, {})

    def test_force_only_when_asked(self):
        svc, pub = make_service(self, self.fake, spoolman_url="http://" + self.fake.host)
        call(self, svc, pub, "connect")
        call(self, svc, pub, "bind_spool", head=0, spool_id=9)
        self.assertNotIn("FORCE", self.fake.scripts[-1])
        call(self, svc, pub, "bind_spool", head=0, spool_id=9, force=True)
        self.assertTrue(self.fake.scripts[-1].endswith("FORCE=1"))

    def test_head_range(self):
        svc, pub = make_service(self, self.fake, spoolman_url="http://" + self.fake.host)
        for cmd, args in (("bind_spool", {"head": 4, "spool_id": 7}), ("unbind_spool", {"head": -1}),
                          ("load", {"head": 9}), ("unload", {"head": 4}), ("reread_rfid", {"head": 7})):
            self.assertIn("bad toolhead", call(self, svc, pub, cmd, **args).get("error", ""), cmd)
        self.assertEqual(self.fake.scripts, [])

    def test_default_target_name(self):
        self.assertEqual(Target("h").name, "Snapmaker U1")


class UsageTests(unittest.TestCase):
    def run_print(self, remember):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        svc, pub = make_service(self, fake, spoolman_url="http://" + fake.host)
        call(self, svc, pub, "connect")
        call(self, svc, pub, "bind_spool", head=3, spool_id=7)
        if remember:
            svc.remember_job("Some/Dir/A.GCODE", {1: 3}, [{"index": 1, "weight": 2.0}])
        fake.state = "printing"
        svc.touch()
        self.assertTrue(wait_for(lambda: svc.last_state == "printing", 6))
        fake.state = "complete"
        svc.touch()
        self.assertTrue(wait_for(lambda: svc.last_state == "complete", 6))
        time.sleep(0.5)
        return fake, pub

    def test_basename_match_and_notice(self):
        fake, pub = self.run_print(True)
        self.assertEqual(fake.uses, [(7, {"use_weight": 2.0})])
        self.assertTrue(any("Spoolman updated" in m.get("text", "") for m in pub))

    def test_no_guessing_without_a_known_job(self):
        fake, pub = self.run_print(False)
        self.assertEqual(fake.uses, [])   # metadata weights are no longer trusted
        self.assertFalse(any("Spoolman updated" in m.get("text", "") for m in pub))

    def test_job_key(self):
        self.assertEqual(service_mod.job_key("Dir\\Sub/Part.GCode"), "part.gcode")


class GenerationTests(unittest.TestCase):
    def test_stale_status_dropped(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        other = fakes.FakePrinter()
        self.addCleanup(other.close)
        pub = []
        svc = Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.set_target(Target(fake.host))
        gen = svc.generation
        real_query = svc.client.query

        def slow_query(objects):
            result = real_query(objects)
            svc.set_target(Target(other.host))   # the user switched printers while we were asking
            return result
        svc.client.query = slow_query
        svc.firmware = {"kind": "stock", "version": ""}
        svc._push_status()
        self.assertEqual(svc.generation, gen + 1)
        self.assertIsNone(svc.last_view)
        self.assertEqual([m for m in pub if m.get("type") == "status"], [])

    def test_frame_pacing(self):
        svc, _ = make_service(self, _Dummy())
        svc.last_frame_at = time.monotonic()
        svc.frame_ack.clear()
        self.assertFalse(svc._frame_due())               # too soon, and not acked
        svc.last_frame_at = time.monotonic() - 0.5
        self.assertFalse(svc._frame_due())               # old enough but the page hasn't acked
        svc.ack_frame()
        self.assertTrue(svc._frame_due())
        svc.frame_ack.clear()
        svc.last_frame_at = time.monotonic() - 2.5
        self.assertTrue(svc._frame_due())                # 2 s without an ack: carry on


class _Dummy:
    host = "127.0.0.1:1"


class DownloadTests(unittest.TestCase):
    def test_streams_without_overwriting(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fake.files["camera/t.mp4"] = b"x" * (3 * 1024 * 1024)
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOME": home}):
            svc, pub = make_service(self, fake)
            first = call(self, svc, pub, "download", path="camera/t.mp4")["result"]
            second = call(self, svc, pub, "download", path="camera/t.mp4")["result"]
        self.assertEqual(os.path.basename(first), "t.mp4")
        self.assertEqual(os.path.basename(second), "t (1).mp4")
        self.assertEqual(os.path.getsize(second), 3 * 1024 * 1024)

    def test_failed_download_leaves_nothing(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOME": home}):
            svc, pub = make_service(self, fake)
            self.assertIn("error", call(self, svc, pub, "download", path="camera/missing.mp4"))
        self.assertEqual(os.listdir(os.path.join(home, "Downloads", "u1control")), [])


class WebsocketTests(unittest.TestCase):
    @staticmethod
    def frame(opcode, payload, fin=True):
        return struct.pack("!BB", (0x80 if fin else 0) | opcode, len(payload)) + payload

    def test_leftover_bytes_ping_and_binary(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        text = json.dumps({"id": 1, "result": "ok"}).encode()
        # frames that arrived together with the handshake headers are the start of the stream
        reader = moonraker._Reader(a, self.frame(0x9, b"hi") + self.frame(0x2, b"\x00\x01") + self.frame(0x1, text))
        self.assertEqual(json.loads(moonraker._ws_recv(reader)), {"id": 1, "result": "ok"})
        b.settimeout(1)
        pong = b.recv(64)
        self.assertEqual(pong[0], 0x8A)   # masked pong echoing the ping payload
        mask = pong[2:6]
        self.assertEqual(bytes(c ^ mask[i % 4] for i, c in enumerate(pong[6:])), b"hi")

    def test_handshake_split(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        b.sendall(b"HTTP/1.1 101 Switching\r\nUpgrade: websocket\r\n\r\n" + self.frame(0x1, b"{}"))
        head, rest = moonraker._read_handshake(a)
        self.assertTrue(head.startswith(b"HTTP/1.1 101"))
        self.assertEqual(rest, self.frame(0x1, b"{}"))


class _NotFound(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(self.server.code)
        self.send_header("Content-Length", "0")
        self.end_headers()


class PortFallbackTests(unittest.TestCase):
    def serve(self, code):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NotFound)
        server.code = code
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:%d" % server.server_address[1]

    def test_next_candidate_on_404_502_503(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        for code in (404, 502, 503):
            mr = Moonraker(fake.host)
            mr.candidates = [self.serve(code), "http://" + fake.host]
            self.assertEqual(mr.info()["hostname"], "u1")
            self.assertEqual(mr.base, "http://" + fake.host)

    def test_other_errors_and_chosen_base_still_raise(self):
        mr = Moonraker("127.0.0.1:1")
        mr.candidates = [self.serve(500), self.serve(200)]
        with self.assertRaises(PrinterError):
            mr.info()
        mr = Moonraker("127.0.0.1:1")
        mr.base = self.serve(404)
        mr.candidates = [mr.base, self.serve(200)]
        with self.assertRaises(PrinterError):
            mr.info()


class GcodeFixTests(unittest.TestCase):
    def test_purifier_replaces_profile_line_before_first_layer(self):
        lines = ["PRINT_START", "SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45", ";LAYER_CHANGE", "G1 X1",
                 "SET_PURIFIER_MODE MODE=0"]
        once = gcode.ensure_purifier(lines, "strong")
        self.assertEqual(once[:4], ["PRINT_START", "; u1control: purifier strong (was: SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45)",
                                    u1.PURIFIER["strong"], ";LAYER_CHANGE"])
        self.assertEqual(once[-1], "SET_PURIFIER_MODE MODE=0")   # the end G-code line is left alone
        self.assertEqual(gcode.ensure_purifier(once, "strong"), once)             # idempotent
        self.assertEqual(gcode.ensure_purifier(once, "off"), lines)               # "off" = as sliced
        self.assertIn(u1.PURIFIER["weak"], gcode.ensure_purifier(once, "weak"))   # re-run with another mode

    def test_purifier_reported_mode(self):
        lines = ["; filament_type = PLA", "G1 X1"]   # no PRINT_START: nothing was written
        _, mode = gcode.process(lines, gcode.settings(lines), {"purifier": "weak"})
        self.assertEqual(mode, "off")

    def test_lift_only_right_after_tool_change_block(self):
        lines = ["; print_sequence = by object", "; max_print_height = 270", "T0", "; Change Tool0 -> Tool1", "; note",
                 "G91", "G1 Z2.4 F600", "G90", "T1", "G1 X5", "G91", "G1 Z2.4 F600", "G90"]
        out = gcode.by_object_toolchange_lift(lines)
        self.assertEqual(out[5:8], ["; u1control: absolute tool-change lift (Snapmaker Orca #958)", "G90", "G1 Z2.4 F600"])
        self.assertEqual(out[-3:], ["G91", "G1 Z2.4 F600", "G90"])   # later unrelated relative lift untouched
        far = ["; print_sequence = by object", "; Change Tool0 -> Tool1", "G1 X5", "G91", "G1 Z2.4 F600", "G90"]
        self.assertEqual(gcode.by_object_toolchange_lift(far), far)  # not directly after the block

    def test_total_layers_by_layer_only(self):
        body = ["SET_PRINT_STATS_INFO TOTAL_LAYER=99", ";LAYER_CHANGE", ";LAYER_CHANGE"]
        self.assertIn("SET_PRINT_STATS_INFO TOTAL_LAYER=2", gcode.real_total_layers(["; print_sequence = by layer"] + body))
        self.assertEqual(gcode.real_total_layers(["; print_sequence = by object"] + body)[1], body[0])

    def test_split_list_commas_only_for_numbers(self):
        self.assertEqual(gcode.split_list("PLA,Matte;PETG"), ["PLA,Matte", "PETG"])
        self.assertEqual(gcode.split_list("Generic PLA, Silk"), ["Generic PLA, Silk"])
        self.assertEqual(gcode.split_list("45,70", numeric=True), ["45", "70"])
        self.assertEqual(gcode.split_list("45;70", numeric=True), ["45", "70"])


class PluginFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.artifact = str(build.build(out_dir=Path(tempfile.mkdtemp())))

    def load(self, **kw):
        orca = fakes.install_orca(**kw)
        return orca, runpy.run_path(self.artifact)

    def test_no_unprefixed_modules_in_sys_modules(self):
        code = ("import sys, json; sys.path.insert(0, %r); import fakes, runpy, build\n"
                "fakes.install_orca(); runpy.run_path(%r)\n"
                "print(json.dumps([m for m in build.MODULES if m in sys.modules]),"
                " '|', json.dumps(sorted(m for m in sys.modules if m.startswith('u1control_'))), sep='')"
                % (os.path.join(ROOT, "tests"), self.artifact))
        env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "scripts")}
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.mkdtemp(),
                             env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        bare, prefixed = (json.loads(part) for part in out.stdout.strip().splitlines()[-1].split("|"))
        self.assertEqual(bare, [])
        self.assertEqual(len(prefixed), 8)

    def test_prefix_imports(self):
        import build
        src = "import u1\nimport extended as ext\nfrom moonraker import X\n    import settings\nimport json\n"
        self.assertEqual(build.prefix_imports(src), "import u1control_u1 as u1\nimport u1control_extended as ext\n"
                         "from u1control_moonraker import X\n    import u1control_settings as settings\nimport json\n")

    def test_json_for_html(self):
        _, ns = self.load()
        text = ns["json_for_html"]({"a": "</script><!-- & <b>"})
        for ch in "<>&":
            self.assertNotIn(ch, text)
        self.assertEqual(json.loads(text), {"a": "</script><!-- & <b>"})

    def test_get_icon_rewrites_and_tolerates_missing_storage(self):
        orca, ns = self.load()
        page = ns["U1ControlPage"]()
        path = page.get_icon()
        with open(path, "w") as f:
            f.write("old")
        self.assertEqual(page.get_icon(), path)
        self.assertIn("<svg", open(path).read())
        orca.host.plugin.storage = mock.Mock(side_effect=RuntimeError("no storage"))
        fallback = page.get_icon()
        self.assertTrue(os.path.exists(fallback))

    def test_send_requires_print_host(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        with open(path, "w") as f:
            f.write(SAMPLE)
        _, ns = self.load()
        ctx = types.SimpleNamespace(step="post", gcode_path=path, host=fake.host, output_name="p.gcode",
                                    config_value=lambda k: "")
        result = ns["U1PrintSetup"]().execute(ctx)
        self.assertEqual(result.status, "failure")
        self.assertIn("no U1 address set", result.message)
        self.assertEqual(fake.scripts, [])

    def _hanging_ctx(self, fake, **extra):
        fd, path = tempfile.mkstemp(suffix=".gcode")
        os.close(fd)
        with open(path, "w") as f:
            f.write(SAMPLE)
        return types.SimpleNamespace(step="post", gcode_path=path, host="OctoPrint", output_name="p.gcode",
                                     config_value=lambda k: {"print_host": fake.host}.get(k, ""), **extra)

    def _hanging_window(self, orca):
        windows = []

        class Window:
            def __init__(self, html, on_message=None, **kw):
                self.on_message, self.open, self.posted = on_message, True, []
                windows.append(self)
                on_message({"ready": True})

            def is_open(self):
                return self.open

            def close(self):
                self.open = False

            def post(self, data):
                self.posted.append(data)

        orca.host.ui.create_window = lambda html, **kw: Window(html, **kw)
        return windows

    def test_setup_window_cancelled_with_slicing(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        orca, ns = self.load()
        windows = self._hanging_window(orca)
        flag = threading.Event()
        threading.Timer(0.6, flag.set).start()
        result = ns["U1PrintSetup"]().execute(self._hanging_ctx(fake, cancelled=flag.is_set))
        self.assertEqual(result.status, "failure")
        self.assertIn("cancelled", result.message)
        self.assertFalse(windows[0].open)
        self.assertEqual(fake.scripts, [])

    def test_setup_window_times_out_and_refreshes_with_one_thread(self):
        fake = fakes.FakePrinter()
        self.addCleanup(fake.close)
        orca, ns = self.load()
        windows = self._hanging_window(orca)
        execute = ns["U1PrintSetup"].execute
        execute.__globals__["SETUP_TIMEOUT"] = 1.5
        self.addCleanup(execute.__globals__.__setitem__, "SETUP_TIMEOUT", 15 * 60)
        threading.Timer(0.4, lambda: [windows[0].on_message({"refresh": True}) for _ in range(5)]).start()
        result = ns["U1PrintSetup"]().execute(self._hanging_ctx(fake))
        self.assertEqual(result.status, "failure")
        self.assertIn("print setup timed out; nothing was sent", result.message)
        self.assertTrue(windows[0].posted)
        self.assertFalse(windows[0].open)
        self.assertEqual(fake.scripts, [])
        self.assertTrue(wait_for(lambda: not [t for t in threading.enumerate() if t.name == "u1control-refresh"], 3))

    def test_preset_updates_run_off_the_calling_thread(self):
        orca, ns = self.load(preset={"name": "Snapmaker U1 (0.4 nozzle)", "printer_model": "Snapmaker U1",
                                     "slicing_pipeline_plugin": ""})
        callers = []
        original = orca.host.preset.process.begin_update
        orca.host.preset.process.begin_update = lambda n: callers.append(threading.current_thread()) or original(n)
        page = ns["U1ControlPage"]()
        page.on_lifecycle_event(orca.LifecycleEvent.ProjectOpened, type("C", (), {"msg": ""})())
        self.assertTrue(wait_for(lambda: callers))
        self.assertIsNot(callers[0], threading.current_thread())
        self.assertEqual(callers[0].name, "u1control-presets")


if __name__ == "__main__":
    unittest.main()
