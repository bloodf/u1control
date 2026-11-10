"""Printer-side work for the U1 Control tab, kept free of the `orca` module so it is testable.

Threads: one command worker (requests run in order) and one monitor (status, camera frames,
Spoolman sync) that only runs while the page holds a lease. Both are the plugin's own worker threads,
so network I/O never blocks OrcaSlicer's UI or slicing threads.
"""

import base64
import os
import queue
import threading
import time
import traceback

import extended as ext
import settings
import spoolman as sm
import u1
from moonraker import Moonraker, PrinterError

LEASE_SECONDS = 6.0
STATUS_EVERY = 2.0
CAMERA_KEEPALIVE = 50.0
FRAME_MIN_INTERVAL = 0.2    # ~5 fps cap
FRAME_ACK_TIMEOUT = 2.0     # fetch the next frame without an ack after this long
URGENT = ("emergency_stop", "pause", "cancel")   # never wait behind the command worker
DEDICATED = URGENT + ("download",)               # own short-lived thread
STOCK_CAMERA = "/server/files/camera/monitor.jpg"
EXT_CAMERA = "/webcam/snapshot.jpg"
GCODE_ROOT = "gcodes"
FILE_ROOTS = ("gcodes", "camera")   # camera = U1 timelapse videos and snapshots


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


class Service:
    def __init__(self, publish, log=print, client_factory=Moonraker):
        self.publish = publish
        self.log = log
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self.target = None
        self.client = None
        self.firmware = {"kind": "unknown", "version": ""}
        self.spoolman = None
        self.spools = []
        self.bindings = {}          # toolhead -> spool id
        self.written = {}           # toolhead -> signature of the filament we just wrote (not a user change)
        self.last_heads = None
        self.last_state = None
        self.last_view = None
        self.last_rfid = None
        self.jobs_sent = {}         # normalized basename -> {toolhead: grams}, recorded when u1control sends a print
        self.generation = 0         # bumps when the target changes; results from an older one are dropped
        self.frame_ack = threading.Event()
        self.frame_ack.set()
        self.last_frame_at = 0.0
        self.camera_on = False
        self.camera_keepalive_at = 0.0
        self.lease_until = 0.0
        self.closed = False
        self.jobs = queue.Queue()
        self.worker = threading.Thread(target=self._work, name="u1control-worker", daemon=True)
        self.monitor = threading.Thread(target=self._watch, name="u1control-monitor", daemon=True)
        self.worker.start()
        self.monitor.start()

    # ------------------------------------------------------------------ plumbing

    def set_target(self, target):
        with self.lock:
            if self.target is None or self.target.key() != target.key():
                self.generation += 1
                self.client = self.client_factory(target.host, target.api_key)
                self.spoolman = None
                self.spools, self.bindings, self.last_heads, self.written = [], {}, None, {}
                self.last_view, self.last_rfid = None, None
                self.firmware = {"kind": "unknown", "version": ""}
            self.target = target

    def touch(self, camera=None):
        with self.lock:
            self.lease_until = time.monotonic() + LEASE_SECONDS
            if camera is not None:
                self.camera_on = bool(camera)
                if not camera:
                    self.camera_keepalive_at = 0.0

    def ack_frame(self):
        self.frame_ack.set()

    def submit(self, request_id, command, args):
        job = (request_id, command, args or {})
        if command in DEDICATED:   # E-stop, pause, cancel and downloads must not queue behind a slow command
            threading.Thread(target=self._run, args=job, name="u1control-" + str(command), daemon=True).start()
        else:
            self.jobs.put(job)

    def close(self):
        self.closed = True
        self.jobs.put(None)
        for t in (self.worker, self.monitor):
            if t is not threading.current_thread():
                t.join(1.0)

    def _work(self):
        while not self.closed:
            job = self.jobs.get()
            if job is None:
                return
            self._run(*job)

    def _run(self, request_id, command, args):
        handler = getattr(self, "cmd_" + str(command), None)
        if handler is None:
            self.publish({"type": "reply", "id": request_id, "error": "unknown command %s" % command})
            return
        try:
            result = handler(**args)
            self.publish({"type": "reply", "id": request_id, "result": result})
        except (PrinterError, sm.SpoolmanError, ValueError) as e:
            self.publish({"type": "reply", "id": request_id, "error": str(e)})
        except Exception as e:  # never kill the worker; keep details in the log only
            self.log("u1control: %s failed: %s\n%s" % (command, e, traceback.format_exc()))
            self.publish({"type": "reply", "id": request_id, "error": "%s failed: %s" % (command, e)})

    def _client(self):
        with self.lock:
            if self.client is None:
                raise PrinterError("no U1 selected: choose a Snapmaker U1 printer with an address")
            return self.client

    # ------------------------------------------------------------------ monitor

    def _watch(self):
        next_status = 0.0
        while not self.closed:
            now = time.monotonic()
            with self.lock:
                active = now < self.lease_until and self.client is not None
                camera = active and self.camera_on
            if not active:
                time.sleep(0.25)
                continue
            try:
                if now >= next_status:
                    next_status = now + STATUS_EVERY
                    self._push_status()
                if camera and self._frame_due():
                    self._push_frame()
                else:
                    time.sleep(0.05 if camera else 0.2)
            except Exception as e:
                self.publish({"type": "offline", "error": str(e)})
                next_status = time.monotonic() + 3
                time.sleep(1)

    def _current(self, gen):
        with self.lock:
            return gen == self.generation

    def _push_status(self):
        with self.lock:
            gen = self.generation
        client = self._client()
        if self.firmware["kind"] == "unknown":
            self.cmd_connect()
        status = client.query(u1.STATUS_OBJECTS)
        if not self._current(gen):
            return   # the target changed while we were asking: this answer is about the old printer
        view = u1.summarize(status)
        view["spool_ids"] = (status.get("print_task_config") or {}).get("filament_spool_id")
        self._spoolman_follow(view, gen)
        self._report_usage(view)
        with self.lock:
            if gen != self.generation:
                return
            view["bindings"] = {str(k): v for k, v in self.bindings.items()}
            self.last_view = view
        self._rfid_follow(view, gen)
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
        client = self._client()
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
        self.frame_ack.clear()
        self.last_frame_at = time.monotonic()
        self.publish({"type": "frame", "image": "data:image/jpeg;base64," + base64.b64encode(data).decode()})

    # ------------------------------------------------------------------ spoolman

    def _spoolman(self):
        with self.lock:
            if self.spoolman is not None:
                return self.spoolman
            target, client, gen = self.target, self._client(), self.generation
        smc = sm.Spoolman(target.spoolman_url, client)
        smc.connect()
        with self.lock:
            if gen == self.generation:
                self.spoolman = smc
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
                    if not self._current(gen):
                        return
                    self._bind(t, pick)
                    self.publish({"type": "notice", "text": "T%d now uses Spoolman spool #%d (%s %s)"
                                  % (t + 1, pick["id"], pick["vendor"], pick["name"])})
        except (PrinterError, sm.SpoolmanError) as e:
            self.publish({"type": "notice", "text": "Spoolman: %s" % e})

    def _is_own_write(self, head, state):   # caller holds self.lock
        """True once (and clears the mark) when the head now shows what _bind just wrote to it."""
        expected = self.written.get(head)
        if expected is None:
            return False
        if expected == self._signature(state):
            self.written.pop(head, None)
            return True
        self.written.pop(head, None)  # the user changed it after our write: treat as a real change
        return False

    @staticmethod
    def _signature(state):
        return (u1._gcode_word(state.get("vendor")).lower(), u1._gcode_word(state.get("type")).upper(),
                u1.norm_colour(state.get("colour")))

    def _bind(self, head, spool, force=False):
        smc = self._spoolman()
        with self.lock:
            target, extended = self.target, self.firmware["kind"] == "extended"
            previous = self.bindings.get(head)
        location = sm.LOCATION_FMT % (target.name, head + 1)
        if previous and previous != spool["id"] and not extended:
            smc.set_location(previous, "")
        if not extended:
            smc.set_location(spool["id"], location)
        with self.lock:
            self.bindings = {h: sid for h, sid in self.bindings.items() if sid != spool["id"]}
            self.bindings[head] = spool["id"]
        if extended or target.spoolman_write_printer:
            self._client().gcode(sm.filament_command_for(head, spool, extended, force))
            if not extended:  # the next status shows this write; the change detector must not rebind on it
                with self.lock:
                    self.written[head] = self._signature({"vendor": spool["vendor"], "type": spool["material"],
                                                          "colour": spool["colour"] or "#FFFFFF"})

    def _report_usage(self, view):
        """Stock firmware without Moonraker's spoolman: deduct per-head filament at print end."""
        state, previous = view["state"], self.last_state
        self.last_state = state
        with self.lock:
            bindings, target, kind = dict(self.bindings), self.target, self.firmware["kind"]
        if previous != "printing" or state != "complete" or not bindings:
            return
        if kind == "extended" or not (target and target.spoolman_report_usage):
            return
        try:
            smc = self._spoolman()
            if smc.via_moonraker:
                return  # Moonraker already reports usage for the active spool
            with self.lock:
                per_head = self.jobs_sent.pop(job_key(view["filename"]), None)
            booked = False
            for t, grams in (per_head or {}).items():   # only jobs u1control sent have known grams
                if grams and t in bindings:
                    smc.use_weight(bindings[t], grams)
                    booked = True
            if booked:
                self.publish({"type": "notice", "text": "Spoolman updated with this print's filament use"})
        except (PrinterError, sm.SpoolmanError, ValueError, TypeError) as e:
            self.publish({"type": "notice", "text": "Spoolman usage not recorded: %s" % e})

    # ------------------------------------------------------------------ commands

    def remember_job(self, filename, mapping, filaments):
        """Called after an upload from the print-setup step: per-toolhead grams for usage reporting."""
        per_head = {}
        for f in filaments:
            t = mapping.get(f["index"])
            if t is not None and f.get("weight"):
                per_head[t] = per_head.get(t, 0) + f["weight"]
        with self.lock:
            self.jobs_sent[job_key(filename)] = per_head

    def cmd_connect(self):
        client = self._client()
        info = client.info()
        status = ext.Extended(client).status()
        self.firmware = u1.detect_firmware(info, status)
        return {"address": client.address, "firmware": self.firmware, "hostname": info.get("hostname"),
                "klipper_state": info.get("state"), "printer": self.target.name}

    def cmd_gcode(self, script):
        script = str(script or "").strip()
        if not script:
            raise ValueError("empty command")
        self._client().gcode(script, timeout=600)
        return True

    def cmd_pause(self):
        return self._client().pause()

    def cmd_resume(self):
        return self._client().resume()

    def cmd_cancel(self):
        return self._client().cancel()

    def cmd_emergency_stop(self):
        return self._client().emergency_stop()

    def cmd_light(self, on):
        return self.cmd_gcode("SET_LED LED=cavity_led WHITE=%d SYNC=0" % (1 if on else 0))

    def cmd_temperature(self, heater, target):
        target = max(0, min(int(target), 320))
        if heater == "bed":
            return self.cmd_gcode("M140 S%d" % min(target, 110))
        return self.cmd_gcode("M104 T%d S%d" % (_head(heater), target))

    def cmd_speed(self, percent):
        return self.cmd_gcode("M220 S%d" % max(10, min(int(percent), 300)))

    def cmd_purifier(self, mode):
        if mode == "idle":
            return self.cmd_gcode("SET_PURIFIER_MODE MODE=0")
        if mode not in u1.PURIFIER:
            raise ValueError("bad purifier mode")
        return self.cmd_gcode(u1.PURIFIER[mode])

    def cmd_preferences(self, prefs):
        """Toggle the printer's print preferences outside a print (as the touchscreen does)."""
        clean = {k: bool(v) for k, v in (prefs or {}).items() if k in u1.PREF_KEYS}
        params = []
        for key, param, _, _, _ in u1.PREFERENCES:
            if key in clean and key != "unload_when_done":
                params.append("%s=%d" % (param, 1 if clean[key] else 0))
        if not params:
            raise ValueError("nothing to change")
        return self.cmd_gcode("SET_PRINT_PREFERENCES " + " ".join(params))

    # toolheads -----------------------------------------------------------

    def cmd_set_filament(self, head, vendor, type, colour, sub_type="Basic"):
        return self.cmd_gcode(u1.filament_config_command(_head(head), vendor, type, sub_type, colour, force=True))

    def cmd_load(self, head):
        return self.cmd_gcode(u1.load_command(_head(head)))

    def cmd_unload(self, head):
        return self.cmd_gcode(u1.unload_command(_head(head)))

    def cmd_reread_rfid(self, head):
        return self.cmd_gcode("FILAMENT_DT_UPDATE CHANNEL=%d" % _head(head))

    # files -----------------------------------------------------------------

    def cmd_files(self, path=GCODE_ROOT):
        path = _safe_path(path)
        listing = self._client().directory(path)
        dirs = [{"name": d.get("dirname"), "modified": d.get("modified"), "size": d.get("size")}
                for d in listing.get("dirs", []) if not str(d.get("dirname", "")).startswith(".")]
        files = []
        for f in listing.get("files", []):
            name = f.get("filename") or ""
            if name.startswith("."):
                continue
            files.append({"name": name, "size": f.get("size"), "modified": f.get("modified"),
                          "time": f.get("estimated_time"), "weight": f.get("filament_weight_total"),
                          "thumbs": f.get("thumbnails") or []})
        return {"path": path, "dirs": sorted(dirs, key=lambda d: d["name"].lower()),
                "files": sorted(files, key=lambda f: -(f["modified"] or 0)),
                "disk": listing.get("disk_usage")}

    def cmd_thumbnail(self, path):
        path = _safe_path(path, (GCODE_ROOT,))
        rel = path[len(GCODE_ROOT) + 1:]
        meta = self._client().metadata(rel)
        thumbs = sorted(meta.get("thumbnails") or [], key=lambda t: -(t.get("width", 0) * t.get("height", 0)))
        if not thumbs:
            return None
        folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
        data = self._client().thumbnail(folder + thumbs[0]["relative_path"])
        return "data:image/png;base64," + base64.b64encode(data).decode()

    def cmd_delete(self, path, is_dir=False):
        path = _safe_path(path)
        if "/" not in path:
            raise ValueError("refusing to delete a file root")
        if is_dir:
            return self._client().delete_directory(path, force=True)
        return self._client().delete_file(path)

    def cmd_print_file(self, path):
        path = _safe_path(path, (GCODE_ROOT,))
        self._require_idle()
        return self._client().print_start(path[len(GCODE_ROOT) + 1:])

    def cmd_download(self, path):
        """Stream a printer file (e.g. a timelapse) to ~/Downloads/u1control/, never overwriting.
        The data goes to '<name>.part', renamed when complete; an interrupted download keeps its
        .part file. Runs on its own thread (see DEDICATED). Returns the saved path."""
        path = _safe_path(path)
        folder = os.path.join(os.path.expanduser("~"), "Downloads", "u1control")
        os.makedirs(folder, exist_ok=True)
        name = os.path.basename(path)
        part = []

        def open_out():
            target, out = _new_file(folder, name + ".part")
            part.append(target)
            return out

        try:
            self._client().download_to(path, open_out)
        except BaseException as e:
            if part:
                raise PrinterError("download interrupted, partial file kept at %s (%s)" % (part[0], e))
            raise
        target = _free_name(folder, name)
        os.rename(part[0], target)
        return target

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
        return self.cmd_gcode(u1.CALIBRATIONS[kind])

    def cmd_power_loss(self, action):
        """Resume or discard a print interrupted by a power cut."""
        if action == "resume":
            self._require_idle()
            return self.cmd_gcode("SDCARD_PRINT_PL_RESTORE")
        if action == "discard":
            return self.cmd_gcode("SDCARD_PRINT_PL_CLEAR_ENV")
        raise ValueError("bad action")

    # spoolman --------------------------------------------------------------

    def cmd_spools(self):
        smc = self._spoolman()
        spools = [sm.spool_view(s) for s in smc.spools()]
        with self.lock:
            self.spools = spools
            if self.firmware["kind"] != "extended":
                found = sm.bindings_from_locations(spools, self.target.name)
                self.bindings = found or self.bindings
            bindings = {str(k): v for k, v in self.bindings.items()}
        return {"spools": spools, "bindings": bindings, "via": "moonraker" if smc.via_moonraker else "direct"}

    def cmd_bind_spool(self, head, spool_id, force=False):
        """force=True sends FORCE=1 (overrides an official/RFID head); only the page's confirmed manual bind sets it."""
        head = _head(head)
        if not self.spools:
            self.cmd_spools()
        with self.lock:
            spool = next((s for s in self.spools if s["id"] == int(spool_id)), None)
        if spool is None:
            raise ValueError("spool #%s not found" % spool_id)
        self._bind(head, spool, bool(force))
        with self.lock:
            return {"bindings": {str(k): v for k, v in self.bindings.items()}}

    def cmd_unbind_spool(self, head):
        head = _head(head)
        with self.lock:
            sid = self.bindings.pop(head, None)
        if self.firmware["kind"] == "extended":
            self._client().gcode("SET_SPOOL_ID CHANNEL=%d SPOOL_ID=0" % head)
        elif sid:
            self._spoolman().set_location(sid, "")
        with self.lock:
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


def job_key(filename):
    """Normalized job name: lowercase basename, so 'Dir/Part.gcode' and 'part.gcode' match."""
    return str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()


def _head(value):
    head = int(value)
    if not 0 <= head < u1.TOOLHEADS:
        raise ValueError("bad toolhead")
    return head


def _free_name(folder, name):
    """folder/name, or 'name (1).ext', 'name (2).ext', ... when taken."""
    stem, ext = os.path.splitext(name or "download")
    for n in range(10000):
        target = os.path.join(folder, name if n == 0 else "%s (%d)%s" % (stem, n, ext))
        if not os.path.exists(target):
            return target
    raise PrinterError("too many files named %s in %s" % (name, folder))


def _new_file(folder, name):
    """Open folder/name for writing without overwriting: 'name (1).ext', 'name (2).ext', ..."""
    stem, ext = os.path.splitext(name or "download")
    for n in range(10000):
        target = os.path.join(folder, name if n == 0 else "%s (%d)%s" % (stem, n, ext))
        try:
            return target, open(target, "xb")
        except FileExistsError:
            continue
    raise PrinterError("too many files named %s in %s" % (name, folder))


def _safe_path(path, roots=FILE_ROOTS):
    """Normalize a Moonraker path under one of roots; reject traversal."""
    path = str(path or "").strip().strip("/")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or parts[0] not in roots or ".." in parts:
        raise ValueError("bad path %r" % path)
    return "/".join(parts)
