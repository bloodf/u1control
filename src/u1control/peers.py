"""Finding the Spooler plugin running in this OrcaSlicer, and reading the stock list it publishes.

OrcaSlicer's plugin API has no call that lists the loaded plugins or passes messages between them,
and no way to hide a plugin's tab (see docs/spooler-contract.md, "Discovery"). The one channel the
host documents as shared is its data folder: every plugin may read and write there. So each plugin
writes a small presence file, refreshed every HEARTBEAT seconds while it is loaded:

    <data folder>/<plugin>/presence.json
    {"schema": "orca-plugin-presence", "version": 1, "plugin": "spooler", "plugin_version": "0.20.1",
     "session": "<random per load>", "pid": <process id>, "started": <unix s>, "ts": <unix s>,
     "state": "active" | "stopped", ...plugin fields}

A peer counts as running only when its file says "active", was refreshed within FRESH seconds and
names this process: a file left on disk by an uninstalled, disabled, crashed or other OrcaSlicer
never does. Spooler also writes <data folder>/spooler/stock.json (parse_stock).

Free of the `orca` module.
"""

import json
import os
import re
import secrets
import threading
import time
import urllib.parse

SCHEMA = "orca-plugin-presence"
VERSION = 1
STOCK_SCHEMA = "spooler-stock"
STOCK_VERSION = 1
SELF = "u1control"
SPOOLER = "spooler"
PRESENCE_FILE = "presence.json"
STOCK_FILE = "stock.json"
HEARTBEAT = 5.0       # seconds between presence refreshes
FRESH = 20.0          # a presence older than this is a peer that is gone
FUTURE_SLACK = 5.0    # a timestamp further ahead than this is not trusted
STOCK_STALE = 120.0   # a stock list older than this is shown as out of date
STOCK_WANT = 15.0     # seconds a stock request from the page keeps Spooler refreshing the list
STOCK_MAX = 2000      # rows read from stock.json
TEXT_MAX = 120
COLOUR_RE = re.compile(r"^#?([0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?$")

STATE_TEXT = {
    "active": "Spooler is running in this OrcaSlicer.",
    "absent": "Spooler isn't running in this OrcaSlicer.",
    "stopped": "Spooler was unloaded or disabled.",
    "stale": "Spooler stopped answering.",
    "other_process": "Spooler is running in another OrcaSlicer window, not this one.",
    "incompatible": "This Spooler version can't share its stock with U1 Control.",
}


def data_root(storage_path):
    """OrcaSlicer's data folder from this plugin's storage path ("" when no orca_plugins folder above it)."""
    cur = os.path.abspath(storage_path or "")
    while os.path.dirname(cur) != cur:
        if os.path.basename(cur) == "orca_plugins":
            return os.path.dirname(cur)
        cur = os.path.dirname(cur)
    return ""


def peer_file(root, plugin, name=PRESENCE_FILE):
    return os.path.join(root, plugin, name) if root else ""


def read_json(path):
    """(object, problem): the parsed JSON object, or None and why ("missing", "unreadable", "not an object")."""
    if not path:
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError):
        return None, "unreadable"
    return (data, "") if isinstance(data, dict) else (None, "not an object")


def write_json(path, value):
    """Whole-file replace: a reader sees the old file or the new one, never half of one."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, ".%s.%d.%d.tmp" % (os.path.basename(path), os.getpid(), threading.get_ident()))
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, separators=(",", ":"))
        os.replace(tmp, path)   # no fsync: a presence is rewritten every few seconds and only lives that long
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value \
        and abs(value) != float("inf") else None


def _text(value):
    return value[:TEXT_MAX] if isinstance(value, str) else ""


def peer_status(doc, now=None, pid=None, plugin=SPOOLER):
    """(state, detail) of a presence file's content; state is one of STATE_TEXT's keys."""
    now = time.time() if now is None else now
    pid = os.getpid() if pid is None else pid
    if doc is None:
        return "absent", ""
    if doc.get("schema") != SCHEMA or doc.get("plugin") != plugin:
        return "incompatible", "not a presence file"
    if doc.get("version") != VERSION:
        return "incompatible", "presence version %r" % (doc.get("version"),)
    ts, session = _num(doc.get("ts")), doc.get("session")
    if ts is None or not isinstance(session, str) or not session:
        return "incompatible", "presence without ts or session"
    if doc.get("pid") != pid:
        return "other_process", ""
    if doc.get("state") == "stopped":
        return "stopped", ""
    if doc.get("state") != "active":
        return "incompatible", "state %r" % (doc.get("state"),)
    if ts > now + FUTURE_SLACK or now - ts > FRESH:
        return "stale", "last seen %d s ago" % max(0, int(now - ts))
    return "active", ""


def normalize_origin(url):
    """One spelling per Spoolman address, without credentials: 'HTTP://Box:7912/' -> 'http://box:7912'.
    "" for none or an unusable value."""
    text = str(url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urllib.parse.urlsplit(text)
        host, port = parts.hostname, parts.port
    except ValueError:
        return ""
    if not host or parts.scheme.lower() not in ("http", "https"):
        return ""
    scheme = parts.scheme.lower()
    default = {"http": 80, "https": 443}[scheme]
    netloc = ("[%s]" % host if ":" in host else host) + ("" if port in (None, default) else ":%d" % port)
    return "%s://%s%s" % (scheme, netloc, parts.path.rstrip("/"))


def _row(raw):
    """A stock row as u1control shows it, or None when it isn't one."""
    if not isinstance(raw, dict):
        return None
    sid = raw.get("id")
    if not isinstance(sid, int) or isinstance(sid, bool) or sid <= 0:
        return None
    fid = raw.get("filament_id")
    colour = COLOUR_RE.match(raw.get("colour") or "") if isinstance(raw.get("colour"), str) else None
    colours = [m.group(1) for m in (COLOUR_RE.match(c) for c in raw.get("colours") or [] if isinstance(c, str)) if m]
    return {
        "id": sid,
        "filament_id": fid if isinstance(fid, int) and not isinstance(fid, bool) else None,
        "name": _text(raw.get("name")), "vendor": _text(raw.get("vendor")) or "Generic",
        "material": _text(raw.get("material")), "location": _text(raw.get("location")),
        "colour": "#" + colour.group(1).upper() if colour else None,
        "colours": ["#" + c.upper() for c in colours[:8]],
        "remaining": _num(raw.get("remaining")), "initial": _num(raw.get("initial")),
        "low": raw.get("low") is True, "use_first": raw.get("use_first") is True,
        "u1_bound": raw.get("u1_bound") is True,
    }


def parse_stock(doc, presence, now=None):
    """The stock list Spooler published, checked against its running presence.

    {"state": "ok" | "stale" | "missing" | "error" | "mismatch", "code", "text", "rows", "key", "ts", "origin", ...}
    "code" names the reason (the page shows its own text for it, in the page's language); "text" stays English.
    "key" names the Spooler run and Spoolman source the rows come from; an assignment made from a list
    with another key is refused. "mismatch": the file is from an earlier Spooler run or source.
    """
    now = time.time() if now is None else now
    out = {"state": "missing", "code": "waiting", "text": "Waiting for Spooler's stock list…", "rows": [], "key": "",
           "ts": None, "origin": "", "source": "", "low_stock_grams": None}
    if doc is None:
        return out
    if doc.get("schema") != STOCK_SCHEMA or doc.get("version") != STOCK_VERSION:
        return {**out, "state": "error", "code": "format", "text": "Spooler's stock list has a format U1 Control doesn't read."}
    origin = doc.get("origin") if isinstance(doc.get("origin"), dict) else {}
    gen, session = origin.get("gen"), doc.get("session")
    if not isinstance(gen, int) or isinstance(gen, bool) or not isinstance(session, str) or not session:
        return {**out, "state": "error", "code": "no_origin", "text": "Spooler's stock list doesn't say where it came from."}
    out.update(origin=normalize_origin(origin.get("url")), source=_text(origin.get("source")),
               ts=_num(doc.get("ts")), low_stock_grams=_num(doc.get("low_stock_grams")))
    if (presence or {}).get("session") != session:
        return {**out, "state": "mismatch", "code": "earlier_run", "text": "Spooler's stock list is from an earlier run; waiting for a new one."}
    out["key"] = "%s:%d" % (session, gen)
    if out["source"] != "spoolman":
        return {**out, "key": "", "state": "error", "code": "not_spoolman", "text": "Spooler's spool source isn't Spoolman, so it has no stock to share."}
    if doc.get("error"):
        return {**out, "state": "error", "code": "spoolman_error", "detail": _text(doc.get("error")),
                "text": "Spooler couldn't read Spoolman: %s" % _text(doc.get("error"))}
    spools = doc.get("spools")
    if not isinstance(spools, list):
        return {**out, "key": "", "state": "error", "code": "no_list", "text": "Spooler's stock list holds no spools list."}
    rows = [r for r in (_row(s) for s in spools[:STOCK_MAX]) if r]
    out["rows"] = rows
    age = None if out["ts"] is None else now - out["ts"]
    if age is None or age > STOCK_STALE or age < -FUTURE_SLACK:
        out.update(state="stale", code="stale", text="Spooler's stock list may be out of date.")
    else:
        out.update(state="ok", code="ok", text="")
    return out


class Presence:
    """This plugin's presence file, refreshed on a daemon thread from start() until stop().
    wants(): the plugin fields to publish, called on every refresh."""

    def __init__(self, root, plugin=SELF, version="", wants=None, log=print, heartbeat=HEARTBEAT, clock=time.time):
        self.root, self.plugin, self.version = root, plugin, version
        self.path = peer_file(root, plugin)
        self.session = secrets.token_hex(8)
        self.wants = wants or (lambda: {})
        self.log, self.heartbeat, self.clock = log, heartbeat, clock
        self.started = clock()
        self._stop = threading.Event()
        self._poke = threading.Event()
        self._thread = None
        self._failed = False

    def doc(self, state="active"):
        return {"schema": SCHEMA, "version": VERSION, "plugin": self.plugin, "plugin_version": self.version,
                "session": self.session, "pid": os.getpid(), "started": int(self.started), "ts": self.clock(),
                "state": state, **({"wants": self.wants()} if state == "active" else {})}

    def write(self, state="active"):
        if not self.path:
            return False
        try:
            write_json(self.path, self.doc(state))
        except OSError as e:
            if not self._failed:
                self.log("u1control: can't write %s (%s); Spooler won't see U1 Control" % (self.path, e))
            self._failed = True
            return False
        self._failed = False
        return True

    def start(self):
        if self._thread is not None or not self.path:
            return
        self.write()
        self._thread = threading.Thread(target=self._loop, name="u1control-presence", daemon=True)
        self._thread.start()

    def poke(self):
        """Publish now (a new stock request) instead of at the next heartbeat."""
        self._poke.set()

    def _loop(self):
        while not self._stop.is_set():
            self._poke.wait(self.heartbeat)
            self._poke.clear()
            if not self._stop.is_set():
                self.write()

    def stop(self):
        """Say "stopped" so Spooler stops refreshing for us at once, rather than after FRESH seconds."""
        self._stop.set()
        self._poke.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2.0)
        self._thread = None
        self.write("stopped")


class SpoolerLink:
    """What u1control knows about Spooler: its presence and stock list, and what to ask of it."""

    def __init__(self, root, version="", log=print, clock=time.time):
        self.root, self.clock = root, clock
        self.lock = threading.Lock()
        self.stock_until = 0.0
        self.stock_request = 0
        self.presence = Presence(root, SELF, version, wants=self._wants, log=log, clock=clock)

    def _wants(self):
        with self.lock:
            return {"stock_until": self.stock_until, "stock_request": self.stock_request}

    def want_stock(self, refresh=False):
        with self.lock:
            self.stock_until = self.clock() + STOCK_WANT
            if refresh:
                self.stock_request += 1
        self.presence.poke()

    def spooler(self):
        """{"state", "text", "detail", "version", "session", "origin"} of the Spooler plugin."""
        doc, _ = read_json(peer_file(self.root, SPOOLER))
        state, detail = peer_status(doc, self.clock())
        spoolman = (doc or {}).get("spoolman") if isinstance((doc or {}).get("spoolman"), dict) else {}
        provides = (doc or {}).get("provides") if isinstance((doc or {}).get("provides"), dict) else {}
        if state == "active" and provides.get("stock") != STOCK_VERSION:
            state, detail = "incompatible", "stock list version %r" % (provides.get("stock"),)
        return {"state": state, "text": STATE_TEXT[state], "detail": detail,
                "version": _text((doc or {}).get("plugin_version")),
                "session": (doc or {}).get("session") if state == "active" else "",
                "origin": normalize_origin(spoolman.get("origin")) if state == "active" else ""}

    def stock(self):
        """(spooler, stock): the peer and, while it runs, its stock list."""
        peer = self.spooler()
        if peer["state"] != "active":
            return peer, {**parse_stock(None, None), "state": "unavailable", "code": "unavailable", "text": peer["text"]}
        doc, problem = read_json(peer_file(self.root, SPOOLER, STOCK_FILE))
        if doc is None and problem != "missing":
            return peer, {**parse_stock(None, None), "state": "error", "code": "unreadable", "text": "Spooler's stock list is unreadable."}
        return peer, parse_stock(doc, peer, self.clock())
