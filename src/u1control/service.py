"""Printer-side work for the U1 Control tab, kept free of the `orca` module so it is testable.

Threads: one command worker (requests run in order), one thumbnail worker, one monitor (status,
camera frames, Spoolman sync) that only runs while the page holds a lease, and one job tracker that
follows the prints u1control sent whether the page is open or not. They are the plugin's own threads,
so network I/O never blocks OrcaSlicer's UI or slicing threads.

Every request is tied to the printer that was selected when it arrived (generation + client). A
queued request whose printer is no longer selected is dropped before it does anything; so are
results and frames about a printer that is no longer selected. E-stop, pause and cancel run at once
on their own thread, against the printer they were pressed for.
"""

import base64
import contextlib
import hashlib
import queue
import re
import threading
import time
import traceback

import extended as ext
import settings
import spoolman as sm
import u1
import usage
from files import GCODE_ROOT, FilesMixin, _safe_path  # noqa: F401  (_safe_path: used by tests and callers)
from moonraker import Moonraker, PrinterError
from stockview import StockMixin
from usage import job_key, printer_ident  # noqa: F401  (job_key: used by tests)

LEASE_SECONDS = 6.0
STATUS_EVERY = 2.0
STATUS_RETRY = 3.0
CAMERA_RETRY = 2.0
CAMERA_KEEPALIVE = 50.0
FRAME_MIN_INTERVAL = 0.2    # ~5 fps cap
FRAME_ACK_TIMEOUT = 2.0     # fetch the next frame without an ack after this long
URGENT = ("emergency_stop", "pause", "cancel")   # never wait behind the command worker
DEDICATED = URGENT + ("download", "screen_touch", "stock", "usage", "usage_ack")  # own short-lived thread
# ("stock" only reads files; "usage"/"usage_ack" only read or write the local ledger, never Spoolman)
THUMB_QUEUE = 8             # thumbnails waiting at most; the page asks for a few at a time
STOCK_CAMERA = "/server/files/camera/monitor.jpg"
EXT_CAMERA = "/webcam/snapshot.jpg"
EXT_SCREEN = "/screen/snapshot"    # Extended Firmware remote screen (touchscreen mirror), PNG
EXT_TOUCH = "/screen/touch"
SCREEN_INTERVAL = 0.5             # remote screen refresh, as its own viewer (~2 Hz)
SCREEN_RETRY = 5.0
M112_RE = re.compile(r"(^|\n)\s*M112\b", re.I)
GCODE_STORE_COUNT = 100           # console: printer replies read back at most
CONSOLE_MAX_CHARS = 4000
STALE = "the selected printer changed; nothing was sent to it"
HOTEND_MAX = 320                  # °C: what cmd_temperature clamps to (the page shows and validates the same)
BED_MAX = 110
NO_U1 = "no U1 selected: choose a Snapmaker U1 printer with an address"


class Target:
    """Where to connect, resolved by the plugin on the UI thread."""

    def __init__(self, host, api_key="", name=settings.CONNECTION["printer_name"], spoolman_url="",
                 spoolman_auto=True, spoolman_report_usage=True, spoolman_write_printer=True):
        self.host, self.api_key, self.name = host, api_key, name or settings.CONNECTION["printer_name"]
        self.spoolman_url = spoolman_url
        self.spoolman_auto = spoolman_auto
        self.spoolman_report_usage = spoolman_report_usage
        self.spoolman_write_printer = spoolman_write_printer

    def key(self):
        return (self.host, self.api_key, self.spoolman_url)

    @property
    def ident(self):
        return printer_ident(self.host)


class Service(FilesMixin, usage.UsageMixin, StockMixin):
    def __init__(self, publish, log=print, client_factory=Moonraker, ledger_path=None):
        self.publish = publish
        self.log = log
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self._op = threading.local()   # (generation, client, target, pinned) of the request this thread runs
        self.target = None
        self.client = None
        self.generation = 0         # bumps when the target changes; work for an older one is dropped
        self.closed = False
        self._closing = threading.Event()
        self.lease_until = 0.0
        self.camera_on = False
        self.screen_on = False
        self.frame_ack = threading.Event()
        self.frame_ack.set()
        # Prints u1control sent, until their filament use is booked; kept in ledger_path across restarts.
        self.ledger = usage.Ledger(usage.LedgerStore(ledger_path, log) if ledger_path else None)
        if self.ledger.restore_notice:
            self.log("u1control: " + self.ledger.restore_notice)
        self.last_state = None
        self._reset_printer_state()
        self.jobs = queue.Queue()
        self.thumbs = queue.Queue(THUMB_QUEUE)
        self.worker = self._thread(self._work, self.jobs, "worker")
        self.thumb_worker = self._thread(self._work, self.thumbs, "thumbs")
        self.monitor = self._thread(self._watch, None, "monitor")
        self.tracker = self._thread(self._track, None, "jobs")

    @staticmethod
    def _thread(fn, arg, name):
        t = threading.Thread(target=fn, args=(arg,) if arg is not None else (), name="u1control-" + name, daemon=True)
        t.start()
        return t

    def _reset_printer_state(self):   # caller holds self.lock (or is __init__)
        self.firmware = {"kind": "unknown", "version": ""}
        self.spoolman, self.spoolman_gen = None, None
        self.spools, self.bindings, self.written = [], {}, {}
        self.last_heads, self.last_view, self.last_rfid = None, None, None
        self.last_frame_at = 0.0
        self.camera_keepalive_at = 0.0
        self.camera_retry_at = 0.0
        self.screen_at = 0.0
        self.screen_digest = None

    # ------------------------------------------------------------------ plumbing

    def set_target(self, target):
        client = None
        with self.lock:
            changed = self.target is None or self.target.key() != target.key()
        if changed:
            try:
                client = self.client_factory(target.host, target.api_key)
            except Exception:
                self.clear_target()   # never keep controlling the previous printer
                raise
        with self.lock:
            if changed:
                self.generation += 1
                self.client = client
                self._reset_printer_state()
            self.target = target
        self.ledger.fill_api_key(target.ident, target.api_key)   # jobs restored from disk keep no key

    def clear_target(self):
        """The selection is not a usable U1: stop controlling the previous printer."""
        with self.lock:
            if self.target is None and self.client is None:
                return
            self.generation += 1
            self.target, self.client = None, None
            self._reset_printer_state()

    def touch(self, camera=None, screen=None, stock=None):
        if stock:
            self.want_stock()
        with self.lock:
            self.lease_until = time.monotonic() + LEASE_SECONDS
            if screen is not None:
                if screen and not self.screen_on:
                    self.screen_digest = None   # send the first frame even when unchanged
                self.screen_on = bool(screen)
            if camera is not None:
                self.camera_on = bool(camera)
                if not camera:
                    self.camera_keepalive_at = 0.0

    def ack_frame(self):
        self.frame_ack.set()

    def submit(self, request_id, command, args, gen=None):
        """gen: the generation the page last saw (from "connect"); a different one means the page asked
        about a printer that is no longer selected."""
        args = args or {}
        if command == "gcode" and M112_RE.search(str(args.get("script") or "")):
            command, args = "emergency_stop", {}   # M112 typed in the console takes the urgent path
        with self.lock:
            current, client, target = self.generation, self.client, self.target
        if gen is not None and gen != current:
            self.publish({"type": "reply", "id": request_id, "error": STALE})
            return
        job = (request_id, command, args, (current, client, target))
        if command in DEDICATED:   # E-stop, pause, cancel and downloads must not queue behind a slow command
            threading.Thread(target=self._run, args=job, name="u1control-" + str(command), daemon=True).start()
        elif command == "thumbnail":
            try:
                self.thumbs.put_nowait(job)
            except queue.Full:
                self.publish({"type": "reply", "id": request_id, "error": "too many thumbnails waiting"})
        else:
            self.jobs.put(job)

    def close(self):
        self.closed = True
        self._closing.set()
        self.jobs.put(None)
        try:
            self.thumbs.put_nowait(None)
        except queue.Full:
            pass
        for t in (self.worker, self.monitor, self.thumb_worker, self.tracker):
            if t is not threading.current_thread():
                t.join(1.0)

    def _work(self, jobs):
        while not self.closed:
            job = jobs.get()
            if job is None:
                return
            self._run(*job)

    def _run(self, request_id, command, args, ctx=None):
        handler = getattr(self, "cmd_" + str(command), None)
        if handler is None:
            self.publish({"type": "reply", "id": request_id, "error": "unknown command %s" % command})
            return
        if ctx is None:
            ctx = self._snapshot()
        gen, client, target = ctx
        pinned = command in URGENT
        if not pinned and not self._current(gen):
            self.publish({"type": "reply", "id": request_id, "error": STALE})
            return
        try:
            with self._bound(gen, client, target, pinned):
                result = handler(**args)
            self.publish({"type": "reply", "id": request_id, "result": result})
        except (PrinterError, sm.SpoolmanError, ValueError) as e:
            self.publish({"type": "reply", "id": request_id, "error": str(e)})
        except Exception as e:  # never kill the worker; keep details in the log only
            self.log("u1control: %s failed: %s\n%s" % (command, e, traceback.format_exc()))
            self.publish({"type": "reply", "id": request_id, "error": "%s failed: %s" % (command, e)})

    def _snapshot(self):
        with self.lock:
            return self.generation, self.client, self.target

    @contextlib.contextmanager
    def _bound(self, gen, client, target, pinned=False):
        """Run the block for one printer: _client()/_ctx() hand out that printer and refuse once it is stale."""
        previous = getattr(self._op, "ctx", None)
        self._op.ctx = (gen, client, target, pinned)
        try:
            yield
        finally:
            self._op.ctx = previous

    def _ctx(self):
        """(generation, client, target) this thread works for; raises when that printer is no longer selected."""
        ctx = getattr(self._op, "ctx", None)
        if ctx is None:
            gen, client, target = self._snapshot()
        else:
            gen, client, target, pinned = ctx
            if not pinned and not self._current(gen):
                raise PrinterError(STALE)
        if client is None:
            raise PrinterError(NO_U1)
        return gen, client, target

    def _client(self):
        return self._ctx()[1]

    def _current(self, gen):
        with self.lock:
            return gen == self.generation

    def _notice(self, text, gen=None):
        if gen is None or self._current(gen):
            self.publish({"type": "notice", "text": text})

    # ------------------------------------------------------------------ monitor

    def _watch(self):
        next_status = 0.0
        while not self.closed:
            now = time.monotonic()
            with self.lock:
                active = now < self.lease_until and self.client is not None
                camera = active and self.camera_on
                screen = active and self.screen_on
                gen, client, target = self.generation, self.client, self.target
            if not active:
                time.sleep(0.25)
                continue
            if now >= next_status:
                next_status = now + STATUS_EVERY
                try:
                    self._push_status()
                except Exception as e:
                    next_status = time.monotonic() + STATUS_RETRY
                    if self._current(gen):
                        self.publish({"type": "offline", "error": str(e)})
            if screen and now >= self.screen_at:
                with self._bound(gen, client, target):
                    self._push_screen()
            if camera and now >= self.camera_retry_at and self._frame_due():
                try:
                    with self._bound(gen, client, target):
                        self._push_frame()
                except Exception as e:   # the camera has its own error and retry: status keeps going
                    self.camera_retry_at = time.monotonic() + CAMERA_RETRY
                    if self._current(gen):
                        self.publish({"type": "camera_error", "error": str(e)})
            else:
                time.sleep(0.05 if camera else 0.2)

    def _push_status(self):
        gen, client, target = self._snapshot()
        if client is None:
            raise PrinterError(NO_U1)
        with self._bound(gen, client, target):
            if self.firmware["kind"] == "unknown":
                self.cmd_connect()
            status = client.query(u1.STATUS_OBJECTS)
            if not self._current(gen):
                return   # the target changed while we were asking: this answer is about the old printer
            view = u1.summarize(status)
            view["busy"] = u1.machine_busy(view)
            view["spool_ids"] = (status.get("print_task_config") or {}).get("filament_spool_id")
            self._spoolman_follow(view, gen)
            for job, outcome in self.ledger.observe(target.ident, view["state"], view["filename"]):
                self._settle(job, outcome)
            with self.lock:
                if gen != self.generation:
                    return
                view["bindings"] = {str(k): v for k, v in self.bindings.items()}
                self.last_view, self.last_state = view, view["state"]
            self._rfid_follow(view, gen)
            if self._current(gen):
                self.publish({"type": "status", "data": view})

    def _rfid_follow(self, view, gen):
        """Publish once when a toolhead reads a different tag than before (not on the first status)."""
        tags = view["rfid"]
        with self.lock:
            if gen != self.generation:
                return
            previous, self.last_rfid = self.last_rfid, [u1.rfid_signature(t) for t in tags]
        if previous is None:
            return
        changed = [t for t, sig in enumerate(self.last_rfid) if sig != previous[t] and tags[t]]
        if changed:
            self.publish({"type": "rfid", "heads": changed, "tags": tags})

    def _frame_due(self):
        """~5 fps, and the page must have shown the previous frame (ack) unless FRAME_ACK_TIMEOUT passed."""
        waited = time.monotonic() - self.last_frame_at
        return waited >= FRAME_MIN_INTERVAL and (self.frame_ack.is_set() or waited >= FRAME_ACK_TIMEOUT)

    def _push_frame(self):
        gen, client, _ = self._ctx()
        extended = self.firmware["kind"] == "extended"
        if not extended and time.monotonic() >= self.camera_keepalive_at:
            try:
                client.ws_call("camera.start_monitor", {"domain": "lan", "interval": 0}, timeout=4)
            except (PrinterError, OSError, ValueError) as e:
                self.log("u1control: camera.start_monitor: %s" % e)
            self.camera_keepalive_at = time.monotonic() + CAMERA_KEEPALIVE
        path = EXT_CAMERA if extended else STOCK_CAMERA
        data, _ = client.raw("GET", path + "?t=%d" % int(time.time() * 1000), timeout=4)
        if data[:2] != b"\xff\xd8":
            raise PrinterError("camera returned no image")
        if not self._current(gen):
            return   # a picture of the printer that is no longer selected
        self.frame_ack.clear()
        self.last_frame_at = time.monotonic()
        self.publish({"type": "frame", "image": "data:image/jpeg;base64," + base64.b64encode(data).decode()})

    def _push_screen(self):
        """Extended Firmware remote screen: publish the touchscreen PNG when it changed."""
        self.screen_at = time.monotonic() + SCREEN_INTERVAL
        if self.firmware["kind"] != "extended":
            return
        try:
            gen, client, _ = self._ctx()
            data, _ = client.raw("GET", EXT_SCREEN + "?t=%d" % int(time.time() * 1000), timeout=4)
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                raise PrinterError("remote screen is off: turn on Remote Screen in Settings > Firmware")
        except (PrinterError, OSError) as e:
            self.screen_at = time.monotonic() + SCREEN_RETRY
            self.screen_digest = None
            self.publish({"type": "screen_error", "error": str(e)})
            return
        digest = hashlib.sha1(data).digest()
        if digest == self.screen_digest or not self._current(gen):
            return
        self.screen_digest = digest
        self.publish({"type": "screen", "image": "data:image/png;base64," + base64.b64encode(data).decode()})

    # ------------------------------------------------------------------ spoolman

    def _spoolman(self):
        gen, client, target = self._ctx()
        with self.lock:
            if self.spoolman is not None and self.spoolman_gen == gen:
                return self.spoolman
        smc = sm.Spoolman(target.spoolman_url, client)
        smc.connect()
        with self.lock:
            if gen == self.generation:
                self.spoolman, self.spoolman_gen = smc, gen
        return smc

    def _spoolman_follow(self, view, gen):
        """Keep toolhead bindings in sync when a head's filament changes on the printer."""
        heads = view["heads"]
        with self.lock:
            if gen != self.generation:
                return
            previous, self.last_heads = self.last_heads, heads
            target, kind = self.target, self.firmware["kind"]
            if not target or (not target.spoolman_url and kind != "extended"):
                return
            if kind == "extended" and isinstance(view.get("spool_ids"), list):
                self.bindings = {t: sid for t, sid in enumerate(view["spool_ids"]) if sid}
                return  # SpoolLink owns the binding on extended firmware
            if previous is None or not target.spoolman_auto:
                return
            changed = [t for t in range(u1.TOOLHEADS) if sm.head_changed(previous[t], heads[t])
                       and not self._is_own_write(t, heads[t])]
        # Never overwrite a head that carries an RFID tag or is an official spool: that would destroy the
        # tag's data and the head's flow calibration. Automatic writes never use FORCE=1.
        changed = [t for t in changed if not heads[t]["official"] and not view["rfid"][t]]
        if not changed:
            return
        try:
            self.cmd_spools()
            for t in changed:
                with self.lock:
                    bound = next((s for s in self.spools if s["id"] == self.bindings.get(t)), None)
                    taken = set(self.bindings.values())
                    spools = list(self.spools)
                if not heads[t]["loaded"]:
                    continue  # removed: keep the binding until a new spool shows up
                if bound and sm.match_score(heads[t], bound) is not None and sm.match_score(heads[t], bound) < 60:
                    continue  # still the same spool
                pick = sm.best_spool(heads[t], spools, exclude=taken)
                if pick:
                    self._bind(t, pick)
                    self._notice("T%d now uses Spoolman spool #%d (%s %s)" % (t + 1, pick["id"], pick["vendor"], pick["name"]), gen)
        except (PrinterError, sm.SpoolmanError) as e:
            self._notice("Spoolman: %s" % e, gen)

    def _is_own_write(self, head, state):   # caller holds self.lock
        """True once (and clears the mark) when the head now shows what _bind just wrote to it."""
        expected = self.written.pop(head, None)
        return expected is not None and expected == self._signature(state)

    @staticmethod
    def _signature(state):
        return (u1._gcode_word(state.get("vendor")).lower(), u1._gcode_word(state.get("type")).upper(),
                u1.norm_colour(state.get("colour")))

    def _bind(self, head, spool, force=False):
        """Link `spool` to `head`. Order: the printer's head first (the step it may refuse), then the new spool's
        Spoolman location, then the old spool's. bindings change only once Spoolman has the new location; a
        failure after the first step reloads the links from Spoolman and says what is left half done."""
        smc = self._spoolman()
        gen, _, target = self._ctx()
        with self.lock:
            extended = self.firmware["kind"] == "extended"
            previous = self.bindings.get(head)
        if extended:
            self._client().gcode(sm.filament_command_for(head, spool, True, force))
            self._set_binding(gen, head, spool["id"])
            return
        wrote = False
        if target.spoolman_write_printer:
            self._client().gcode(sm.filament_command_for(head, spool, False, force))
            wrote = True
            with self.lock:   # the next status shows this write; the change detector must not rebind on it
                self.written[head] = self._signature({"vendor": spool["vendor"], "type": spool["material"],
                                                      "colour": spool["colour"] or "#FFFFFF"})
        try:
            self._ctx()
            smc.set_location(spool["id"], sm.LOCATION_FMT % (target.name, head + 1))
        except (PrinterError, sm.SpoolmanError) as e:
            self._reconcile()
            raise sm.SpoolmanError("%sSpoolman did not record spool #%d on T%d (%s); links reloaded from Spoolman"
                                   % ("T%d now shows that filament, but " % (head + 1) if wrote else "",
                                      spool["id"], head + 1, e)) from e
        self._set_binding(gen, head, spool["id"])
        if previous and previous != spool["id"]:
            try:
                self._ctx()
                smc.set_location(previous, "")
            except (PrinterError, sm.SpoolmanError) as e:
                self._reconcile()
                raise sm.SpoolmanError("spool #%d is linked to T%d, but spool #%d still lists T%d in Spoolman (%s); "
                                       "clear its location there" % (spool["id"], head + 1, previous, head + 1, e)) from e

    def _set_binding(self, gen, head, spool_id):
        with self.lock:
            if gen == self.generation:
                self.bindings = {h: s for h, s in self.bindings.items() if s != spool_id and h != head}
                self.bindings[head] = spool_id

    def _reconcile(self):
        try:
            self.cmd_spools()
        except (PrinterError, sm.SpoolmanError) as e:
            self.log("u1control: re-reading Spoolman failed: %s" % e)

    # ------------------------------------------------------------------ commands

    def cmd_connect(self):
        gen, client, target = self._ctx()
        info = client.info()
        firmware = u1.detect_firmware(info, ext.Extended(client).status())
        with self.lock:
            if gen != self.generation:
                raise PrinterError(STALE)
            self.firmware = firmware
        return {"address": client.address, "firmware": firmware, "hostname": info.get("hostname"),
                "klipper_state": info.get("state"), "printer": target.name, "generation": gen,
                "limits": {"hotend": HOTEND_MAX, "bed": BED_MAX}}

    def _gcode(self, script):
        self._client().gcode(script, timeout=600)
        return True

    def cmd_gcode(self, script):
        """Console: send, then read back the printer's replies logged since (Moonraker's gcode store)."""
        script = str(script or "").strip()
        if not script:
            raise ValueError("empty command")
        client = self._client()
        try:
            since = (self._gcode_store(client, 1) or [{}])[-1].get("time", 0.0)
        except (PrinterError, OSError, ValueError, AttributeError) as e:
            since, why = None, str(e)
        client.gcode(script, timeout=600)
        if since is None:
            return {"ok": True, "output": [], "note": "printer replies unavailable (%s)" % why}
        try:
            entries = self._gcode_store(client, GCODE_STORE_COUNT)
        except (PrinterError, OSError, ValueError) as e:
            return {"ok": True, "output": [], "note": "printer replies unavailable (%s)" % e}
        return {"ok": True, "output": _console_lines(entries, since),
                "note": "replies the printer logged since this command; other clients' messages can show up too"}

    @staticmethod
    def _gcode_store(client, count):
        result = client.request("GET", "/server/gcode_store", {"count": count}) or {}
        entries = result.get("gcode_store") if isinstance(result, dict) else None
        if not isinstance(entries, list):
            raise ValueError("unexpected gcode store answer")
        return [e for e in entries if isinstance(e, dict)]

    def cmd_pause(self):
        return self._client().pause()

    def cmd_resume(self):
        return self._client().resume()

    def cmd_cancel(self):
        return self._client().cancel()

    def cmd_emergency_stop(self):
        return self._client().emergency_stop()

    def cmd_light(self, on):
        return self._gcode("SET_LED LED=cavity_led WHITE=%d SYNC=0" % (1 if on else 0))

    def cmd_temperature(self, heater, target):
        target = max(0, min(int(target), HOTEND_MAX))
        if heater == "bed":
            return self._gcode("M140 S%d" % min(target, BED_MAX))
        return self._gcode("M104 T%d S%d" % (_head(heater), target))

    def cmd_speed(self, percent):
        return self._gcode("M220 S%d" % max(10, min(int(percent), 300)))

    def cmd_purifier(self, mode):
        if mode == "idle":
            return self._gcode("SET_PURIFIER_MODE MODE=0")
        if mode not in u1.PURIFIER:
            raise ValueError("bad purifier mode")
        return self._gcode(u1.PURIFIER[mode])

    def cmd_preferences(self, prefs):
        """Toggle the printer's print preferences outside a print (as the touchscreen does)."""
        prefs = prefs or {}
        if "unload_when_done" in prefs:
            raise ValueError("Unload when done is chosen for each print, per toolhead, in the U1 print setup pop-up")
        clean = {k: bool(v) for k, v in prefs.items() if k in u1.PREF_KEYS}
        params = ["%s=%d" % (param, 1 if clean[key] else 0) for key, param, _, _, _ in u1.PREFERENCES if key in clean]
        if not params:
            raise ValueError("nothing to change")
        self._require_idle()
        return self._gcode("SET_PRINT_PREFERENCES " + " ".join(params))

    # toolheads -----------------------------------------------------------

    def cmd_set_filament(self, head, vendor, type, colour, sub_type="Basic", force=False):
        """force=True (FORCE=1) only after the page confirmed overwriting an official or RFID-tagged head."""
        head = _head(head)
        _check_tag(self._require_idle(), head, force)
        return self._gcode(u1.filament_config_command(head, vendor, type, sub_type, colour, force=bool(force)))

    def cmd_load(self, head):
        head = _head(head)
        self._require_idle()
        return self._gcode(u1.load_command(head))

    def cmd_unload(self, head):
        head = _head(head)
        self._require_idle()
        return self._gcode(u1.unload_command(head))

    def cmd_reread_rfid(self, head):
        return self._gcode("FILAMENT_DT_UPDATE CHANNEL=%d" % _head(head))

    def cmd_screen_touch(self, x, y):
        """Tap the printer's touchscreen at framebuffer pixel (x, y) through the remote screen."""
        x, y = int(x), int(y)
        if not (0 <= x < 4096 and 0 <= y < 4096):
            raise ValueError("touch outside the screen")
        self._client().raw("POST", "%s?a=tap&x=%d&y=%d" % (EXT_TOUCH, x, y), b"", timeout=4)
        with self.lock:
            self.screen_at = 0.0   # show the result of the tap right away
        return True

    def cmd_print_file(self, path):
        path = _safe_path(path, (GCODE_ROOT,))
        self._require_idle()
        return self._client().print_start(path[len(GCODE_ROOT) + 1:])

    def _require_idle(self):
        view = u1.summarize(self._client().query(u1.STATUS_OBJECTS))
        if u1.machine_busy(view):
            raise PrinterError("the U1 is busy (%s)" % (view["machine_state"] or view["state"]).lower())
        return view

    # maintenance -------------------------------------------------------------

    def cmd_calibrate(self, kind):
        if kind not in u1.CALIBRATIONS:
            raise ValueError("unknown calibration")
        self._require_idle()
        return self._gcode(u1.CALIBRATIONS[kind])

    def cmd_power_loss(self, action):
        """Resume or discard a print interrupted by a power cut."""
        if action == "resume":
            self._require_idle()
            return self._gcode("SDCARD_PRINT_PL_RESTORE")
        if action == "discard":
            return self._gcode("SDCARD_PRINT_PL_CLEAR_ENV")
        raise ValueError("bad action")

    # spoolman --------------------------------------------------------------

    def cmd_spools(self):
        """Spools and links from Spoolman. An empty answer clears stock-firmware links; a failed read keeps
        the last ones (and raises)."""
        gen, _, target = self._ctx()
        smc = self._spoolman()
        spools = [sm.spool_view(s) for s in smc.spools()]
        with self.lock:
            if gen != self.generation:
                raise PrinterError(STALE)
            self.spools = spools
            if self.firmware["kind"] != "extended":
                self.bindings = sm.bindings_from_locations(spools, target.name)
            bindings = {str(k): v for k, v in self.bindings.items()}
        return {"spools": spools, "bindings": bindings, "via": "moonraker" if smc.via_moonraker else "direct"}

    def cmd_bind_spool(self, head, spool_id, force=False):
        """force=True sends FORCE=1 (overrides an official/RFID head); only the page's confirmed manual bind sets it."""
        head = _head(head)
        if not self.spools:
            self.cmd_spools()
        with self.lock:
            spool = next((s for s in self.spools if s["id"] == int(spool_id)), None)
            stock = self.firmware["kind"] != "extended"
        if spool is None:
            raise ValueError("spool #%s not found" % spool_id)
        if stock and self._ctx()[2].spoolman_write_printer:
            _check_tag(self._require_idle(), head, force)   # re-read right before writing the head
        self._bind(head, spool, bool(force))
        with self.lock:
            return {"bindings": {str(k): v for k, v in self.bindings.items()}}

    def cmd_unbind_spool(self, head):
        """The link goes away only after the printer (Extended) or Spoolman (stock) accepted the change."""
        head = _head(head)
        gen = self._ctx()[0]
        with self.lock:
            sid, extended = self.bindings.get(head), self.firmware["kind"] == "extended"
        if extended:
            self._client().gcode("SET_SPOOL_ID CHANNEL=%d SPOOL_ID=0" % head)
        elif sid:
            self._spoolman().set_location(sid, "")
        with self.lock:
            if gen == self.generation and self.bindings.get(head) == sid:
                self.bindings.pop(head, None)
            return {"bindings": {str(k): v for k, v in self.bindings.items()}}

    # extended firmware -----------------------------------------------------

    def _extended(self):
        if self.firmware["kind"] != "extended":
            raise PrinterError("this needs the U1 Extended Firmware (with Advanced Mode on)")
        return ext.Extended(self._client())

    def cmd_ext_settings(self):
        e = self._extended()
        return {"status": e.status(), "settings": e.settings()}

    def cmd_ext_set(self, setting_id, value, inputs=None):
        return self._extended().set(setting_id, value, inputs)

    def cmd_ext_action(self, action_id):
        return self._extended().action(action_id)




def _check_tag(view, head, force):
    """A manual write over a head's RFID data needs the user's confirmation (force). Official spools are also
    refused by the firmware without FORCE=1; third-party tags are not, so this is the only guard for them."""
    if view["rfid"][head] and not view["heads"][head].get("official") and not force:
        raise PrinterError("T%d holds an RFID-tagged spool; confirm overwriting its tag data first" % (head + 1))


def _console_lines(entries, since):
    lines, size = [], 0
    for e in entries:
        if e.get("type") != "response" or not isinstance(e.get("time"), (int, float)) or e["time"] <= since:
            continue
        text = str(e.get("message") or "")
        size += len(text)
        if size > CONSOLE_MAX_CHARS:
            lines.append("… (more in the printer's console)")
            break
        lines.append(text)
    return lines


def _head(value):
    head = int(value)
    if not 0 <= head < u1.TOOLHEADS:
        raise ValueError("bad toolhead")
    return head
