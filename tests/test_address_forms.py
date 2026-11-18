"""Printer addresses as users type them: a bare IP or hostname, or a reverse proxy URL (https on 443, another port,
a path prefix). Every request (HTTP, uploads, camera, websocket) keeps the scheme, port and prefix; the network
permission is asked for the printer's scheme://host once (GitHub #48)."""

import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import moonraker  # noqa: E402
from moonraker import Moonraker, PrinterError, normalize_host, permission_origin  # noqa: E402


class Answer(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    """Records every URL and header; answers like Moonraker."""

    def __init__(self):
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        return Answer(b'{"result": {"state": "ready"}}')


class AddressFormTests(unittest.TestCase):
    def test_forms(self):
        cases = {
            "192.168.1.5": "http://192.168.1.5",
            "u1.lan": "http://u1.lan",
            "http://u1.lan:80/": "http://u1.lan:80",
            "HTTPS://u1.example.com": "https://u1.example.com",
            "https://u1.example.com:8443/": "https://u1.example.com:8443",
            "https://u1.example.com/u1/": "https://u1.example.com/u1",
            "https://u1.example.com/a/b?x=1#y": "https://u1.example.com/a/b",
            "http://[fd00::5]:7125": "http://[fd00::5]:7125",
        }
        for given, want in cases.items():
            self.assertEqual(normalize_host(given), want, given)

    def test_bad_addresses_say_what_was_wrong(self):
        for bad in ("", "ftp://u1.lan", "http://u1.lan:port", "https://"):
            with self.assertRaises(PrinterError) as ctx:
                normalize_host(bad)
            self.assertTrue("address" in str(ctx.exception), str(ctx.exception))

    def test_moonraker_port_fallback_only_for_plain_http_roots(self):
        self.assertEqual(Moonraker("192.168.1.5").candidates, ["http://192.168.1.5", "http://192.168.1.5:7125"])
        self.assertEqual(Moonraker("u1.lan").candidates, ["http://u1.lan", "http://u1.lan:7125"])
        self.assertEqual(Moonraker("https://u1.example.com").candidates, ["https://u1.example.com"])
        self.assertEqual(Moonraker("https://u1.example.com/u1").candidates, ["https://u1.example.com/u1"])
        self.assertEqual(Moonraker("http://u1.example.com/u1").candidates, ["http://u1.example.com/u1"])
        self.assertEqual(Moonraker("http://[fd00::5]").candidates, ["http://[fd00::5]", "http://[fd00::5]:7125"])

    def test_requests_keep_the_prefix(self):
        opener = Opener()
        mr = Moonraker("https://u1.example.com/u1/", opener=opener)
        mr.info()
        mr.thumbnail("a b.png")
        mr.raw("GET", "/webcam/snapshot.jpg")
        self.assertEqual([r.full_url for r in opener.requests],
                         ["https://u1.example.com/u1/printer/info", "https://u1.example.com/u1/server/files/gcodes/a%20b.png",
                          "https://u1.example.com/u1/webcam/snapshot.jpg"])
        self.assertEqual(mr.address, "u1.example.com/u1")

    def test_upload_goes_through_the_prefix(self):
        opener = Opener()
        mr = Moonraker("https://u1.example.com:8443/u1", opener=opener)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fakes.py")
        mr.upload(path, "part.gcode")
        self.assertEqual(opener.requests[-1].full_url, "https://u1.example.com:8443/u1/server/files/upload")

    def ws_request(self, address):
        sent = []
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.sendall.side_effect = sent.append
        sock.recv.return_value = b""   # no answer: the handshake fails after the request went out
        with mock.patch.object(moonraker.socket, "create_connection", return_value=sock) as connect, \
                mock.patch.object(moonraker.ssl, "create_default_context") as tls:
            tls.return_value.wrap_socket.return_value = sock
            with self.assertRaises(PrinterError):
                Moonraker(address).ws_call("printer.info")
        return connect.call_args[0][0], tls, sent[0].decode()

    def test_websocket_over_tls_with_the_prefix(self):
        target, tls, request = self.ws_request("https://u1.example.com/u1")
        self.assertEqual(target, ("u1.example.com", 443))
        tls.return_value.wrap_socket.assert_called_once()
        self.assertEqual(tls.return_value.wrap_socket.call_args[1]["server_hostname"], "u1.example.com")
        self.assertTrue(request.startswith("GET /u1/websocket HTTP/1.1\r\nHost: u1.example.com\r\n"), request)

    def test_websocket_plain_http_as_before(self):
        target, tls, request = self.ws_request("192.168.1.5")
        self.assertEqual(target, ("192.168.1.5", 80))
        tls.assert_not_called()
        self.assertTrue(request.startswith("GET /websocket HTTP/1.1\r\nHost: 192.168.1.5\r\n"), request)
        target, _, request = self.ws_request("https://u1.example.com:8443")
        self.assertEqual(target, ("u1.example.com", 8443))
        self.assertIn("Host: u1.example.com:8443\r\n", request)

    def test_permission_origin_is_scheme_and_host(self):
        self.assertEqual(permission_origin("192.168.1.5"), "http://192.168.1.5")
        self.assertEqual(permission_origin("HTTPS://U1.Example.com:8443/u1/"), "https://u1.example.com")
        self.assertEqual(permission_origin("http://[fd00::5]:7125"), "http://[fd00::5]")
        self.assertEqual(permission_origin(""), "")
        self.assertEqual(permission_origin("ftp://x"), "")


if __name__ == "__main__":
    unittest.main()
