"""Moonraker client for the Snapmaker U1 (stdlib only).

Stock and extended U1 firmware both serve Moonraker behind nginx on port 80 and
directly on 7125. The client tries the address as given, then :7125.
"""

import base64
import hashlib
import http.client
import json
import os
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

# Load hostname codecs up front so the first request on a worker thread does not import them lazily.
import encodings.idna  # noqa: F401
from i18n import tr

MOONRAKER_PORT = 7125
MAX_BODY = 64 * 1024 * 1024
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
FALLBACK_STATUSES = (404, 502, 503)   # "not Moonraker here": try the next candidate port


class PrinterError(RuntimeError):
    """A printer request failed; the message is safe to show the user."""
    status = None   # HTTP status when the printer answered with one


class UploadCancelled(Exception):
    """The caller's cancelled() said stop while an upload was running."""


def normalize_host(host):
    """'192.168.1.5' / 'http://u1.lan:80/' -> 'http://192.168.1.5'. Raises PrinterError."""
    host = (host or "").strip().strip('"').rstrip("/")
    if not host:
        raise PrinterError(tr("no printer address configured"))
    if "://" not in host:
        host = "http://" + host
    parts = urllib.parse.urlsplit(host)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PrinterError(tr("can't read printer address %r") % host)
    return "%s://%s" % (parts.scheme, parts.netloc)


class Moonraker:
    def __init__(self, host, api_key="", timeout=5.0, opener=None):
        base = normalize_host(host)
        parts = urllib.parse.urlsplit(base)
        self.candidates = [base] if parts.port else [base, "%s://%s:%d" % (parts.scheme, parts.hostname, MOONRAKER_PORT)]
        self.hostname = parts.hostname
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.base = None
        self._open = (opener or _NO_PROXY).open

    # ---------------------------------------------------------------- transport

    def _headers(self, extra=None):
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        headers.update(extra or {})
        return headers

    def raw(self, method, path, body=None, headers=None, timeout=None, base=None, limit=MAX_BODY):
        """One HTTP request against one base URL. Returns (bytes, response headers); an answer of more than
        `limit` bytes is refused."""
        req = urllib.request.Request((base or self.base or self.candidates[0]) + path, data=body,
                                     method=method, headers=self._headers(headers))
        try:
            with self._open(req, timeout=timeout or self.timeout) as resp:
                data = resp.read(limit + 1)
                if len(data) > limit:
                    raise PrinterError(tr("printer response too large"))
                return data, resp.headers
        except urllib.error.HTTPError as e:
            raise _http_error(e)
        except http.client.HTTPException as e:   # not an OSError: a broken answer must not escape as one
            raise PrinterError(tr("the printer sent a broken answer (%s)") % (type(e).__name__,)) from e

    def download_to(self, path, open_out, timeout=30):
        """Stream /server/files/<path> into the binary file returned by open_out(), which is only
        called once the printer has answered, so a missing file creates nothing. Returns the byte count."""
        req = urllib.request.Request((self.base or self.candidates[0]) + "/server/files/" + urllib.parse.quote(path),
                                     headers=self._headers())
        total = 0
        try:
            with self._open(req, timeout=timeout) as resp, open_out() as out:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        return total
                    out.write(chunk)
                    total += len(chunk)
        except urllib.error.HTTPError as e:
            raise _http_error(e)
        except (OSError, http.client.HTTPException) as e:
            raise PrinterError(tr("download failed (%s)") % getattr(e, "reason", e))

    def request(self, method, path, params=None, json_body=None, timeout=None):
        """JSON request; returns Moonraker's "result". Picks the working port on first use."""
        if params:
            path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params, doseq=True)
        body, headers = None, None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        bases = [self.base] if self.base else self.candidates
        errors = []
        for base in bases:
            try:
                data, _ = self.raw(method, path, body, headers, timeout, base)
                payload = json.loads(data.decode("utf-8") or "{}")
            except PrinterError as e:
                if self.base or e.status not in FALLBACK_STATUSES or base == bases[-1]:
                    raise
                errors.append("%s (HTTP %d)" % (base, e.status))
                continue
            except (OSError, ValueError) as e:  # unreachable, or not Moonraker on this port
                errors.append("%s (%s)" % (base, getattr(e, "reason", e)))
                if isinstance(getattr(e, "reason", e), (TimeoutError, socket.timeout)):
                    break  # host is down: the other port won't answer either
                continue
            self.base = base
            return payload.get("result") if isinstance(payload, dict) else payload
        raise PrinterError(tr("can't reach the U1 at %s") % "; ".join(errors))

    @property
    def address(self):
        return (self.base or self.candidates[0]).split("://", 1)[1]

    # ---------------------------------------------------------------- printer

    def info(self):
        return self.request("GET", "/printer/info")

    def query(self, objects):
        """objects: {"print_stats": None | ["state", ...]} -> status dict."""
        params = {name: ",".join(fields) if fields else "" for name, fields in objects.items()}
        query = "&".join(urllib.parse.quote(k, safe="") + ("=" + urllib.parse.quote(v, safe=",") if v else "")
                         for k, v in params.items())
        return (self.request("GET", "/printer/objects/query?" + query) or {}).get("status", {})

    def gcode_commands(self):
        """The G-code commands this printer's Klipper registers (read-only GET /printer/gcode/help), upper case."""
        result = self.request("GET", "/printer/gcode/help")
        return frozenset(str(k).upper() for k in result) if isinstance(result, dict) else frozenset()

    def gcode(self, script, timeout=30):
        return self.request("POST", "/printer/gcode/script", json_body={"script": script}, timeout=timeout)

    def print_start(self, filename):
        return self.request("POST", "/printer/print/start", json_body={"filename": filename})

    def upload(self, local_path, name, progress=None, cancelled=None, timeout=300):
        """POST /server/files/upload (root gcodes) as multipart, streamed from disk. progress(sent, total) after
        each chunk; cancelled() -> True stops the upload (raises UploadCancelled)."""
        boundary = "u1control" + os.urandom(12).hex()
        quoted = name.replace("\\", "_").replace('"', "_")
        head = ('--%s\r\nContent-Disposition: form-data; name="root"\r\n\r\ngcodes\r\n'
                '--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n' % (boundary, boundary, quoted)).encode("utf-8")
        tail = ("\r\n--%s--\r\n" % boundary).encode("ascii")
        size = os.path.getsize(local_path)

        def body():
            yield head
            sent = 0
            with open(local_path, "rb") as f:
                while True:
                    if cancelled and cancelled():
                        raise UploadCancelled()
                    chunk = f.read(256 * 1024)
                    if not chunk:
                        break
                    sent += len(chunk)
                    yield chunk
                    if progress:
                        progress(sent, size)
            yield tail

        if cancelled and cancelled():
            raise UploadCancelled()
        if not self.base:
            self.info()   # pick the working port first: a streamed body can't be replayed on the next one
        headers = {"Content-Type": "multipart/form-data; boundary=" + boundary,
                   "Content-Length": str(len(head) + size + len(tail))}
        try:
            data, _ = self.raw("POST", "/server/files/upload", body(), headers, timeout)
        except OSError as e:
            raise PrinterError(tr("upload failed (%s)") % getattr(e, "reason", e))
        try:
            return json.loads(data.decode("utf-8") or "{}")
        except ValueError:
            return {}

    def pause(self):
        return self.request("POST", "/printer/print/pause")

    def resume(self):
        return self.request("POST", "/printer/print/resume")

    def cancel(self):
        return self.request("POST", "/printer/print/cancel")

    def emergency_stop(self):
        # U1 Moonraker registers printer.emergency_stop for websocket/MQTT only. It bypasses the gcode
        # queue, so it is tried first; M112 is the fallback when the websocket is unavailable.
        try:
            return self.ws_call("printer.emergency_stop", timeout=3)
        except (PrinterError, OSError, ValueError):
            return self.gcode("M112", timeout=5)

    # ---------------------------------------------------------------- files

    def directory(self, path="gcodes", extended=True):
        return self.request("GET", "/server/files/directory",
                            {"path": path, "extended": "true" if extended else "false"}) or {}

    def metadata(self, filename):
        return self.request("GET", "/server/files/metadata", {"filename": filename}) or {}

    def thumbnail(self, relative_path):
        """Thumbnail bytes for a path relative to the gcodes root."""
        data, _ = self.raw("GET", "/server/files/gcodes/" + urllib.parse.quote(relative_path))
        return data

    def roots(self):
        """Moonraker's file roots: [{"name", "path", "permissions"}]."""
        return self.request("GET", "/server/files/roots") or []

    def file_list(self, root):
        """Every file under a root, as a flat list: [{"path" (relative to the root), "size", "modified"}]."""
        return self.request("GET", "/server/files/list", {"root": root}) or []

    def file_bytes(self, path, limit):
        """A small file's bytes; path includes the root. A file of more than `limit` bytes is refused."""
        data, _ = self.raw("GET", "/server/files/" + urllib.parse.quote(path), limit=limit)
        return data

    def delete_file(self, path):
        """path includes the root, e.g. 'gcodes/sub/part.gcode'."""
        return self.request("DELETE", "/server/files/" + urllib.parse.quote(path))

    def create_directory(self, path):
        return self.request("POST", "/server/files/directory", json_body={"path": path})

    def move(self, source, dest):
        """Move or rename a file or folder; both paths include the root."""
        return self.request("POST", "/server/files/move", json_body={"source": source, "dest": dest})

    def delete_directory(self, path, force=False):
        return self.request("DELETE", "/server/files/directory", {"path": path, "force": str(bool(force)).lower()})

    # ---------------------------------------------------------------- websocket rpc

    def ws_call(self, method, params=None, timeout=None):
        """One JSON-RPC call over Moonraker's websocket. Some U1 methods (camera.*, printer.emergency_stop)
        are registered for websocket/MQTT only, not HTTP."""
        base = self.base or self.candidates[0]
        parts = urllib.parse.urlsplit(base)
        if parts.scheme != "http":
            raise PrinterError(tr("websocket calls need plain http"))
        port = parts.port or 80
        with socket.create_connection((parts.hostname, port), timeout=timeout or self.timeout) as sock:
            key = base64.b64encode(os.urandom(16)).decode()
            extra = "X-Api-Key: %s\r\n" % self.api_key if self.api_key else ""
            sock.sendall(("GET /websocket HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
                          "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n%s\r\n"
                          % (parts.hostname, port, key, extra)).encode())
            head, buf = _read_handshake(sock)
            lines = head.split(b"\r\n")
            if b" 101 " not in lines[0]:
                raise PrinterError(tr("printer refused the websocket"))
            accept = base64.b64encode(hashlib.sha1(key.encode() + WS_GUID).digest())
            got = next((l.split(b":", 1)[1].strip() for l in lines[1:] if l.lower().startswith(b"sec-websocket-accept:")), b"")
            if got != accept:
                raise PrinterError(tr("bad websocket handshake"))
            reader = _Reader(sock, buf)
            req_id = int(time.time() * 1000) & 0x7FFFFFFF
            _ws_send(sock, json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}))
            deadline = time.monotonic() + (timeout or self.timeout)
            while time.monotonic() < deadline:
                msg = json.loads(_ws_recv(reader))
                if isinstance(msg, dict) and msg.get("id") == req_id:
                    if "error" in msg:
                        err = msg["error"]
                        raise PrinterError(tr("printer said: %s") % (err.get("message", err) if isinstance(err, dict) else err))
                    return msg.get("result")
            raise PrinterError(tr("printer didn't answer %s") % method)


def _http_error(e):
    try:
        msg = json.loads(e.read(65536).decode("utf-8"))["error"]["message"]
    except Exception:
        msg = "HTTP %d" % e.code
    finally:
        e.close()
    if e.code in (401, 403):
        msg = tr("access denied (%s); set the API key in the printer connection settings") % msg
    err = PrinterError(tr("printer said: %s") % msg)
    err.status = e.code
    return err


def _read_handshake(sock, limit=16384):
    """(header bytes, bytes already received after the headers: the start of the frame stream)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk or len(buf) > limit:
            raise PrinterError(tr("bad websocket handshake"))
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    return head, rest


class _Reader:
    def __init__(self, sock, buf=b""):
        self.sock, self.buf = sock, buf

    def exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self.buf)))
            if not chunk:
                raise PrinterError(tr("websocket closed"))
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out


def _ws_send(sock, text, opcode=0x1):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    mask = os.urandom(4)
    n = len(data)
    if n < 126:
        header = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
    elif n < 65536:
        header = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
    else:
        header = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
    sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _ws_recv(reader, limit=4 * 1024 * 1024):
    """Next text message (fragments joined; pings answered, binary frames ignored)."""
    parts, binary = [], False
    while True:
        b1, b2 = reader.exact(2)
        opcode, n = b1 & 0x0F, b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", reader.exact(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", reader.exact(8))[0]
        if n > limit:
            raise PrinterError(tr("websocket message too large"))
        mask = reader.exact(4) if b2 & 0x80 else None
        payload = reader.exact(n)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:
            raise PrinterError(tr("websocket closed"))
        if opcode == 0x9:
            _ws_send(reader.sock, payload, 0xA)
            continue
        if opcode == 0xA:
            continue
        if opcode == 0x2:
            binary = True
        elif opcode == 0x1:
            binary = False
            parts = []
        if not binary:
            parts.append(payload)
        if b1 & 0x80:
            if binary:
                binary = False
                continue
            return b"".join(parts).decode("utf-8")
