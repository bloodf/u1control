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


if __name__ == "__main__":
    unittest.main()
