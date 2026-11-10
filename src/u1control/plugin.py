"""OrcaSlicer glue: U1 Control tab, U1 print setup (slicing pipeline) and helper scripts."""

import json
import os
import re
import tempfile
import threading
import time

import orca

import gcode
import settings
import spooler_bridge
import u1
from moonraker import Moonraker, PrinterError
from service import Service, Target

VERSION = "0.0.0-dev"
APP_HTML = None     # build.py inlines ui/app.html
SETUP_HTML = None   # build.py inlines ui/setup.html
ICON_SVG = None     # build.py inlines ui/icon.svg

_service = None
_service_lock = threading.Lock()
_store = None
_store_lock = threading.Lock()
_pipeline_done = set()   # process presets U1 print setup was already offered for this session
_presets_lock = threading.Lock()   # preset edits (begin_update/commit) run one at a time, off the UI thread
SETUP_TIMEOUT = 15 * 60  # seconds the print setup window may stay open before the send is abandoned


def _asset(name):
    """Inlined at build time; read from src/u1control/ui during development."""
    inlined = {"app.html": APP_HTML, "setup.html": SETUP_HTML, "icon.svg": ICON_SVG}[name]
    if inlined is not None:
        return inlined
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", name), encoding="utf-8") as f:
        return f.read()


def log(msg):
    print("[u1control] " + str(msg))


def service(publish=None):
    global _service
    with _service_lock:
        if _service is None:
            _service = Service(publish or (lambda m: None), log)
        elif publish is not None:
            _service.publish = publish
        return _service


def get_store(cap):
    """The shared settings store. The file lives in the plugin's storage folder; without one
    (cloud plugin, nobody signed in) it falls back to `cap`'s config."""
    global _store
    with _store_lock:
        if _store is None:
            try:
                _store = settings.Store(os.path.join(orca.host.plugin.storage(), "settings.json"))
            except Exception as e:
                log("settings: no storage folder (%s); using the plugin config" % e)
                _store = settings.Store(load=lambda: json.dumps(_cap_config(cap).get("u1_settings") or {}),
                                        save=lambda text: cap.save_config(
                                            json.dumps({**_cap_config(cap), "u1_settings": json.loads(text)})))
        return _store


def _cap_config(cap):
    try:
        data = json.loads(cap.get_config())
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def clean(value):
    return value.strip().strip('"') if isinstance(value, str) else ""


def is_u1_name(*values):
    return any(re.search(r"snapmaker[ _-]*u1|\bu1\b", clean(v), re.I) for v in values if v)


def run_off_thread(fn, timeout=20):
    """Run fn in a plugin thread (unaudited) and wait. Printer I/O never runs on Orca's threads."""
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # handed back to the caller
            box["error"] = e

    t = threading.Thread(target=target, name="u1control-io", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise PrinterError("the U1 did not answer in %d s" % timeout)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def json_for_html(data):
    """JSON safe inside a <script> block: no literal <, > or & can end it or open a tag."""
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# ====================================================================== U1 Control tab

class U1ControlPage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "U1 Control"

    def get_icon(self):
        svg = _asset("icon.svg")
        try:
            folders = [orca.host.plugin.storage(), tempfile.gettempdir()]
        except Exception as e:
            log("icon: no storage folder (%s); using the temp folder" % e)
            folders = [tempfile.gettempdir()]
        for folder in folders:
            path = os.path.join(folder, "u1control.svg")
            try:
                try:
                    with open(path, encoding="utf-8") as f:
                        same = f.read() == svg
                except OSError:
                    same = False
                if not same:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(svg)
                return path
            except OSError as e:
                log("icon: can't write %s (%s)" % (path, e))
        return ""

    def get_default_config(self):
        return {}

    def get_ui(self):
        return _asset("app.html").replace("__VERSION__", VERSION)

    def _settings(self):
        return get_store(self)

    def _config(self):
        return self._settings().effective()

    def _target(self):
        cfg = self._config()
        host, key = clean(cfg.get("host")), clean(cfg.get("api_key"))
        if not host:
            bundle = orca.host.preset_bundle()
            preset = bundle.current_printer_preset()
            if not is_u1_name(preset.config_value("printer_model"), preset.name, preset.config_value("inherits")):
                raise ValueError("Select a Snapmaker U1 printer, or set \"host\" in U1 Control's plugin config.")
            host = clean(preset.config_value("print_host")) or clean(bundle.full_config_value("print_host"))
            key = clean(preset.config_value("printhost_apikey")) or clean(bundle.full_config_value("printhost_apikey"))
            if not host:
                raise ValueError("The selected U1 has no address: click the Wi-Fi icon next to the printer and enter its IP.")
        return Target(host, key, settings.printer_label(clean(cfg.get("printer_name"))), clean(cfg.get("spoolman_url")),
                      bool(cfg["spoolman_auto"]), bool(cfg["spoolman_report_usage"]), bool(cfg["spoolman_write_printer"]))

    def on_message(self, data):
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        svc = service(self.post_message)
        try:
            if kind == "hello":
                svc.set_target(self._target())
                svc.touch(camera=False)
                svc.submit(data.get("id"), "connect", {})
                self.post_message(self._config_message())
                self._auto_pipeline()
            elif kind == "lease":
                svc.touch(camera=data.get("camera"))
            elif kind == "frame_ack":
                svc.ack_frame()
            elif kind == "cmd":
                svc.touch()
                svc.submit(data.get("id"), data.get("cmd"), data.get("args") or {})
            elif kind == "sync_project":
                view = svc.last_view
                if data.get("auto") and spooler_keeping_slots():
                    self.post_message({"type": "notice", "text": "Spooler is keeping slots synced"})
                elif not view:
                    self.post_message({"type": "notice", "text": "No printer status yet; try again in a moment."})
                else:
                    overrides = self._config()["profile_overrides"]

                    def job():
                        try:
                            done, problems = sync_project(view["heads"], view["rfid"], overrides, bound=bound_spool_lookup(svc))
                            text = sync_message(done, problems)
                        except Exception as e:
                            text = "Couldn't update the project filaments: %s" % e
                        self.post_message({"type": "notice", "text": text})
                    if not self._background(job):
                        self.post_message({"type": "notice", "text": "Another preset update is running; try again in a moment."})
            elif kind == "save_settings":
                changes = dict(data.get("settings") or {})
                if changes.get("api_key") == "••••":
                    del changes["api_key"]  # the masked value the page was shown
                self._settings().update(changes)
                svc.set_target(self._target())
                self.post_message(self._config_message())
                self._auto_pipeline()
        except Exception as e:
            self.post_message({"type": "reply", "id": data.get("id"), "error": str(e)})

    def _config_message(self):
        cfg = self._config()
        cfg["api_key"] = "••••" if cfg.get("api_key") else ""
        spooler = spooler_state()
        spooler["dismissed"] = bool(cfg["spooler_hint_dismissed"])
        automations = [{"key": k, "label": label, "help": hint, "automagic": value,
                        "choices": None if kind == "bool" else list(kind)}
                       for k, label, hint, value, kind in settings.AUTOMATIONS if k != "mode"]
        return {"type": "config", "settings": cfg, "automations": automations, "mode": cfg["mode"],
                "stored": {k: v for k, v in self._settings().raw().items() if k in settings.automagic_values()},
                "spooler": spooler, "version": VERSION}

    @staticmethod
    def _background(job):
        """Run `job` on a plugin thread, one preset edit at a time: begin_update() must never run on the
        UI thread (OrcaSlicer blocks the caller until the UI thread has applied the selection).
        False when another edit is still running."""
        if not _presets_lock.acquire(blocking=False):
            return False

        def run():
            try:
                job()
            except Exception as e:
                log("preset update failed: %r" % e)
            finally:
                _presets_lock.release()
        threading.Thread(target=run, name="u1control-presets", daemon=True).start()
        return True

    def _auto_pipeline(self):
        cfg = self._config()

        def job():
            try:
                name = ensure_pipeline(cfg)
                if name:
                    self.post_message({"type": "notice", "text": "U1 print setup added to %s; save the preset to keep it" % name})
            except Exception as e:
                log("auto-add U1 print setup failed: %r" % e)
        self._background(job)

    def on_lifecycle_event(self, event, ctx):
        kind = getattr(ctx, "msg", "")
        if event == orca.LifecycleEvent.DeviceSelected or (
                event == orca.LifecycleEvent.PresetSelected and kind == "printer"):
            self.post_message({"type": "selection_changed"})
        if (event == orca.LifecycleEvent.PresetSelected and kind in ("print", "process")) or (
                event == getattr(orca.LifecycleEvent, "ProjectOpened", None)):
            self._auto_pipeline()

    def on_unload(self):
        global _service
        with _service_lock:
            if _service is not None:
                _service.close()
                _service = None


# ====================================================================== print setup

def ensure_pipeline(cfg):
    """Add "U1 print setup" to the selected U1 process preset's Slicing Pipeline Plugin, once per
    preset name per session. Call from a plugin thread or the Script worker, never the UI thread
    (begin_update blocks until the UI thread has applied the change).
    Returns the preset name when it was added."""
    if not cfg.get("auto_add_pipeline"):
        return None
    bundle = orca.host.preset_bundle()
    printer = bundle.current_printer_preset()
    if not is_u1_name(printer.config_value("printer_model"), printer.name, printer.config_value("inherits")):
        return None
    name = bundle.current_process_preset().name
    if name in _pipeline_done:
        return None
    _pipeline_done.add(name)  # before trying: a failure must not retry on every event
    value = settings.with_pipeline(bundle.full_config_value("slicing_pipeline_plugin"))
    if value is None:
        return None
    tx = orca.host.preset.process.begin_update("")
    tx.set("slicing_pipeline_plugin", value)
    tx.commit()
    try:
        ui = orca.host.ui
        ui.push_notification(ui.NotificationLevel.RegularNotificationLevel,
                             "U1 print setup added to %s; save the preset to keep it" % name)
    except Exception as e:
        log("notification failed: %r" % e)
    return name


class Cancelled(Exception):
    pass


def _cover_text(mode):
    return "left as sliced" if mode == "off" else mode


class U1PrintSetup(orca.slicing.SlicingPipelineCapabilityBase):
    """Process > Others > Slicing Pipeline Plugin > "U1 print setup"."""

    def get_name(self):
        return "U1 print setup"

    def get_default_config(self):
        return {}

    def _settings(self):
        return get_store(self)

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.skipped()
        try:
            return orca.ExecutionResult.success(self._postprocess(ctx))
        except Cancelled:
            return orca.ExecutionResult.failure(orca.PluginResult.FatalError,
                                                "U1 print setup: cancelled, nothing was sent.")
        except Exception as e:
            log("print setup failed: %r" % e)
            return orca.ExecutionResult.failure(orca.PluginResult.FatalError, "U1 print setup: %s" % e)

    def _postprocess(self, ctx):
        lines, newline = gcode.read(ctx.gcode_path)
        cfg = gcode.settings(lines)
        if not gcode.is_u1(cfg):
            return "not a Snapmaker U1 print; skipped"
        store = self._settings()
        options = store.effective()
        sending = clean(ctx.host) not in ("", "File")
        if not sending:
            lines, mode = gcode.process(lines, cfg, options, version=VERSION)
            gcode.write(ctx.gcode_path, lines, newline)
            return "U1 G-code prepared (top cover: %s)" % _cover_text(mode)

        host = clean(ctx.config_value("print_host"))
        if not host:
            raise PrinterError("no U1 address set: click the Wi-Fi icon next to the printer and enter its IP")
        key = clean(ctx.config_value("printhost_apikey"))
        client = Moonraker(host, key, timeout=5)
        status = run_off_thread(lambda: client.query(u1.STATUS_OBJECTS))
        view = u1.summarize(status)
        if u1.machine_busy(view):
            raise PrinterError("the U1 is busy (%s); wait for it to finish first"
                               % (view["machine_state"] or view["state"]).lower())
        filaments = gcode.filaments(lines, cfg)
        heads = view["heads"]
        mapping = u1.auto_map(filaments, heads)
        prefs = self._offered_prefs(options, view["options"])
        purifier = options["purifier"]
        dialog = options["print_dialog"]
        if dialog == "always" or (dialog == "auto" and u1.needs_dialog(
                filaments, heads, mapping, bool(view["options"]), not options["printed_before"])):
            choice = self._ask(ctx, lines, cfg, filaments, heads, mapping, prefs, purifier, client)
            mapping, prefs, purifier = choice["map"], choice["prefs"], choice["purifier"]
            if options["remember_print_options"]:
                store.update({"prefs": prefs, **({"purifier": purifier} if options["mode"] == settings.EXPERT else {})})
        else:
            problems = u1.mapping_warnings(filaments, heads, mapping)
            if problems:
                raise PrinterError("; ".join(problems) + ". Set the print setup pop-up to auto or always to choose toolheads.")
        lines, mode = gcode.process(lines, cfg, {**options, "purifier": purifier}, mapping, heads, VERSION)
        gcode.write(ctx.gcode_path, lines, newline)
        script = u1.preprint_script(mapping, prefs)
        run_off_thread(lambda: client.gcode(script))
        store.update({"printed_before": True})
        filename = clean(getattr(ctx, "output_name", "")) or os.path.basename(ctx.gcode_path)
        if _service is not None:
            _service.remember_job(filename, mapping, filaments)
        return "sent to %s: %s" % (client.address, script.replace("\n", " | "))

    @staticmethod
    def _offered_prefs(options, printer_opts):
        saved = options["prefs"] if options["remember_print_options"] else {}
        prefs = {}
        for key, _, _, _, basic in u1.PREFERENCES:
            if basic:
                prefs[key] = bool(saved.get(key, options[key]))
            elif key in printer_opts:
                prefs[key] = bool(saved[key]) if key in saved else printer_opts[key]
        return prefs

    def _ask(self, ctx, lines, cfg, filaments, heads, mapping, prefs, purifier, client):
        ui = orca.host.ui
        data = {
            "job": {**gcode.summary(lines, cfg), "name": clean(getattr(ctx, "output_name", "")),
                    "address": client.address, "thumbnail": gcode.thumbnail(lines)},
            "filaments": filaments, "heads": heads, "map": {str(k): v for k, v in mapping.items()},
            "prefs": prefs, "labels": {p[0]: p[2] for p in u1.PREFERENCES},
            "purifier": purifier, "auto_purifier": u1.purifier_mode(filaments),
        }
        html = _asset("setup.html").replace("__DATA__", json_for_html(data))
        done, ready, wanted, stop = (threading.Event() for _ in range(4))
        result = {}
        window_box = []

        def refresher():   # one long-lived thread; refresh requests that arrive while it is busy coalesce
            while not stop.is_set():
                if not wanted.wait(0.5):
                    continue
                wanted.clear()
                try:
                    fresh = u1.summarize(client.query(u1.STATUS_OBJECTS))["heads"]
                    window_box[0].post({"heads": fresh, "map": {str(k): v for k, v in
                                                                u1.auto_map(filaments, fresh).items()}})
                except Exception as e:
                    log("refresh failed: %s" % e)

        def on_message(msg):
            if not isinstance(msg, dict):
                return
            if msg.get("ready"):
                ready.set()
            if msg.get("refresh") and window_box:
                wanted.set()

        def on_submit(msg):
            result["data"] = msg
            done.set()

        cancel = getattr(ctx, "cancelled", None) or getattr(ctx, "canceled", None)

        def slicing_cancelled():
            try:
                return bool(cancel() if callable(cancel) else cancel)
            except Exception:
                return False

        window = ui.create_window(html, title="U1 print setup", width=720, height=640, on_message=on_message,
                                  on_close=done.set, on_submit=on_submit, style=ui.WINDOW_MODAL)
        window_box.append(window)
        threading.Thread(target=refresher, name="u1control-refresh", daemon=True).start()
        started = time.monotonic()
        try:
            while not done.wait(0.25):  # UI from a slicing hook: give up if the UI thread never shows it
                waited = time.monotonic() - started
                if slicing_cancelled():
                    window.close()
                    raise Cancelled()
                if waited > SETUP_TIMEOUT:
                    window.close()
                    raise PrinterError("print setup timed out; nothing was sent")
                if not window.is_open():
                    break
                if not ready.is_set() and waited > 20:
                    window.close()
                    raise PrinterError("the print setup window didn't open (OrcaSlicer was busy); nothing was sent")
        finally:
            stop.set()
        answer = result.get("data")
        if not isinstance(answer, dict) or answer.get("cancelled"):
            raise Cancelled()
        chosen = {}
        for f, t in (answer.get("map") or {}).items():
            if str(f).isdigit() and isinstance(t, int) and 0 <= t < u1.TOOLHEADS and int(f) in mapping:
                chosen[int(f)] = t
        picked = answer.get("prefs") or {}
        purifier = answer.get("purifier") if answer.get("purifier") in ("auto", "off", *u1.PURIFIER) else "auto"
        return {"map": {**mapping, **chosen}, "prefs": {k: bool(picked.get(k, v)) for k, v in prefs.items()},
                "purifier": purifier}


# ====================================================================== scripts

def _selected_u1():
    bundle = orca.host.preset_bundle()
    preset = bundle.current_printer_preset()
    host = clean(preset.config_value("print_host")) or clean(bundle.full_config_value("print_host"))
    key = clean(preset.config_value("printhost_apikey")) or clean(bundle.full_config_value("printhost_apikey"))
    if not host:
        raise ValueError("Select your Snapmaker U1 printer and set its IP (Wi-Fi icon next to the printer).")
    return Moonraker(host, key, timeout=5)


class CheckConnection(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Check U1 connection"

    def execute(self):
        try:
            client = _selected_u1()
            info = run_off_thread(client.info)
            heads = run_off_thread(lambda: u1.summarize(client.query(u1.STATUS_OBJECTS))["heads"])
        except Exception as e:
            return orca.ExecutionResult.skipped("Couldn't reach the U1: %s" % e)
        fw = u1.detect_firmware(info)
        loaded = ", ".join("T%d %s" % (h["index"] + 1, ("%s %s" % (h["type"], h["colour"] or "")).strip()
                                       if h["loaded"] else "empty") for h in heads)
        return orca.ExecutionResult.success("U1 at %s (%s firmware %s). %s" % (client.address, fw["kind"],
                                                                               fw["version"], loaded))


SUB_TYPE_WORDS = {"matte", "silk", "snapspeed", "hf", "cf", "gf", "basic", "pro", "lite", "tough", "galaxy",
                  "marble", "glow", "sparkle", "wood", "metal", "high", "speed", "rapid"}


def _words(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def override_name(names, head, tag, overrides):
    """User-pinned preset: UID: first, then SKU:, then "Vendor|TYPE|SubType". Only if it exists."""
    pins = {str(k).strip().lower(): v for k, v in (overrides or {}).items()}
    tag = tag or {}
    vendor = tag.get("vendor") or tag.get("manufacturer") or head.get("vendor") or ""
    ftype = tag.get("type") or head.get("type") or ""
    sub = tag.get("sub_type") or head.get("sub_type") or ""
    keys = ["uid:" + str(tag.get("uid") or ""), "sku:" + str(tag.get("sku") or ""),
            "%s|%s|%s" % (vendor, ftype, sub), "%s|%s|" % (vendor, ftype)]
    for key in keys:
        name = pins.get(key.lower())
        if name in names:
            return name
    return ""


def pick_filament_preset(names, head, tag=None, overrides=None, printer_hint="U1", preference=None, colours=None):
    """Best Orca filament preset name for what a toolhead (and its RFID tag) holds, or "".
    preference(names, head, tag) -> name or None is consulted after overrides, before scoring.
    colours: preset name -> "#RRGGBB"; the nearest colour wins between equally scored presets."""
    tag = tag or {}
    pinned = override_name(names, head, tag, overrides)
    if pinned:
        return pinned
    if preference:
        chosen = preference(names, head, tag)
        if chosen in names:
            return chosen
    ftype = (tag.get("type") or head.get("type") or "").upper()
    family = u1.material_family(ftype)
    vendor = (tag.get("vendor") or tag.get("manufacturer") or head.get("vendor") or "").lower()
    sub = _words(tag.get("sub_type") or head.get("sub_type")) - {"basic"}
    on_printer = re.compile(r"@\s*(snapmaker\s*)?%s\b" % re.escape(printer_hint), re.I)

    def score(name):
        n, up = name.lower(), name.upper()
        if not family or not re.search(r"\b%s" % re.escape(family), up):
            return None
        s = 20 if re.search(r"(?<![A-Z0-9])%s(?![A-Z0-9+])" % re.escape(ftype), up.replace(" ", "-")) else 5
        if vendor and vendor in n:
            s += 30
        elif "generic" in n:
            s += 5
        if on_printer.search(name):
            s += 10
        elif "@" in name:
            s -= 10
        if "0.4" in name:
            s += 1
        extra = (_words(name) & SUB_TYPE_WORDS) - {"basic"}
        s += 8 * len(sub & extra) - 6 * len(extra - sub)
        return s

    want = tag.get("colour") or head.get("colour")

    def far(name):
        return u1.colour_distance(want, colours.get(name)) if colours and want else 0

    ranked = sorted(((-r, far(n), len(n), n) for r, n in ((score(n), n) for n in names) if r is not None))
    return ranked[0][3] if ranked else ""


def spooler_dir():
    try:
        return spooler_bridge.data_dir(orca.host.plugin.storage())
    except Exception:
        return ""


def spooler_keeping_slots():
    try:
        preset = orca.host.preset_bundle().current_printer_preset()
        labels = (clean(preset.config_value("printer_model")), clean(preset.name))
    except Exception:
        labels = ()
    return spooler_bridge.keep_slots_active(spooler_bridge.read_json(spooler_dir(), spooler_bridge.KEEP_SLOTS_FILE),
                                            time.time(), labels)


def filament_meta(full=True):
    """Spooler-relevant facts about every filament preset (colour and compatibility only when full)."""
    collection = orca.host.preset_bundle().filaments
    out = []
    for i in range(collection.size()):
        preset = collection.preset(i)
        meta = {"name": preset.name, "bundle_id": getattr(preset, "bundle_id", "") or ""}
        if full:
            colours = (spooler_bridge.as_list(preset.config_value("default_filament_colour"))
                       or spooler_bridge.as_list(preset.config_value("filament_colour")))
            vendor = spooler_bridge.as_list(preset.config_value("filament_vendor"))
            meta.update(compatible_printers=spooler_bridge.as_list(preset.config_value("compatible_printers")),
                        colour=colours[0] if colours else "", vendor=vendor[0] if vendor else "")
        out.append(meta)
    return out


def spooler_state():
    """{"installed", "presets", "url"}: is the Spooler plugin around (its bundle, presets or settings file)?"""
    try:
        ids = list(orca.host.preset.bundles.list_ids())
    except Exception:
        ids = []
    try:
        meta = filament_meta(full=False)
    except Exception:
        meta = []
    try:
        has_file = os.path.exists(os.path.join(spooler_dir(), spooler_bridge.SETTINGS_FILE))
    except Exception:
        has_file = False
    return {**spooler_bridge.detect(ids, meta, has_file), "url": spooler_bridge.URL}


def bound_spool_lookup(svc):
    """toolhead index -> the Spoolman spool bound to it (as the service last loaded it), or None."""
    def lookup(index):
        wanted = svc.bindings.get(index) if svc else None
        return next((s for s in (svc.spools if svc else []) if s["id"] == wanted), None)
    return lookup


def spooler_preference(presets, bound, printer_label=""):
    """`preference` hook for pick_filament_preset: the Spooler preset of the head's bound spool."""
    profiles = spooler_bridge.read_json(spooler_dir(), spooler_bridge.PROFILES_FILE)

    def prefer(names, head, tag):
        spool = bound(head["index"])
        return spooler_bridge.preset_for_spool(presets, spool, profiles, printer_label) if spool else None
    return prefer


def sync_project(heads, tags, overrides=None, preset_preference=None, bound=None):
    """Apply each loaded toolhead's best filament preset and colour to project slot n+1.
    Spooler's presets are preferred for heads with a bound spool (bound: head index -> spool).
    Returns (done, problems) as lists of strings."""
    meta = filament_meta()
    names = [m["name"] for m in meta]
    colours = {m["name"]: m["colour"] for m in meta}
    if preset_preference is None and bound:
        printer = orca.host.preset_bundle().current_printer_preset()
        presets = spooler_bridge.spooler_presets(meta, (printer.name, clean(printer.config_value("inherits"))))
        if presets:
            preset_preference = spooler_preference(presets, bound,
                                                   clean(printer.config_value("printer_model")) or printer.name)
    done, problems = [], []
    for head in heads:
        tag = (tags[head["index"]] if head["index"] < len(tags or []) else None) or None
        if not head["loaded"] and not tag:
            continue
        slot = head["index"] + 1
        preset_name = pick_filament_preset(names, head, tag, overrides, preference=preset_preference, colours=colours)
        colour = (tag or {}).get("colour") or head["colour"]
        try:
            tx = orca.host.preset.filament.begin_update(slot, preset_name)
            if colour:
                tx.set("filament_colour", colour)
            tx.commit()
            done.append("%d: %s" % (slot, preset_name or (tag or head).get("type") or "?"))
        except Exception as e:
            problems.append("filament %d: %s" % (slot, e))
    return done, problems


def sync_message(done, problems):
    message = "Project filaments " + (", ".join(done) or "unchanged")
    return message + (". Problems: " + "; ".join(problems) if problems else "")


class SyncHeadsToProject(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Sync U1 toolheads to project filaments"

    def execute(self):
        try:
            client = _selected_u1()
            view = run_off_thread(lambda: u1.summarize(client.query(u1.STATUS_OBJECTS)))
        except Exception as e:
            return orca.ExecutionResult.skipped("Couldn't reach the U1: %s" % e)
        overrides = get_store(self).effective()["profile_overrides"]
        done, problems = sync_project(view["heads"], view["rfid"], overrides, bound=bound_spool_lookup(_service))
        return orca.ExecutionResult.success(sync_message(done, problems))


# Snapmaker Orca's U1 process values that upstream 2.5 sets differently (fork profiles, 2026-10).
FORK_PROCESS_TUNING = (
    ("wall_generator", "classic"),
    ("precise_outer_wall", "0"),
    ("tree_support_branch_angle_organic", "45"),
)


def tuning_changes(preset_name, current):
    """[(key, old, new)] to bring the active U1 process preset to Snapmaker Orca's values.
    current: key -> value as the preset has it."""
    changes = [(k, current.get(k), v) for k, v in FORK_PROCESS_TUNING if str(current.get(k)) != v]
    # Upstream 2.5 bug: "0.18 Standard @Snapmaker U1 (0.6 nozzle)" ships layer_height 0.25.
    if preset_name.startswith("0.18 ") and str(current.get("layer_height")) == "0.25":
        changes.append(("layer_height", "0.25", "0.18"))
    return changes


class ApplyForkTuning(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Apply Snapmaker Orca U1 process tuning"

    def execute(self):
        bundle = orca.host.preset_bundle()
        printer = bundle.current_printer_preset()
        if not is_u1_name(printer.config_value("printer_model"), printer.name, printer.config_value("inherits")):
            return orca.ExecutionResult.skipped("Select a Snapmaker U1 printer first.")
        process = bundle.current_process_preset()
        keys = [k for k, _ in FORK_PROCESS_TUNING] + ["layer_height"]
        changes = tuning_changes(process.name, {k: bundle.full_config_value(k) for k in keys})
        if not changes:
            return orca.ExecutionResult.success("\"%s\" already matches Snapmaker Orca." % process.name)
        listing = "\n".join("  %s: %s -> %s" % c for c in changes)
        if orca.host.ui.message("Change the process preset \"%s\" to Snapmaker Orca's U1 values?\n\n%s\n\n"
                                "The preset stays unsaved until you save it." % (process.name, listing),
                                title="U1 Control", buttons="yes_no", icon="question") != "yes":
            return orca.ExecutionResult.skipped("No changes made.")
        tx = orca.host.preset.process.begin_update("")
        for key, _, value in changes:
            tx.set(key, value)
        tx.commit()
        return orca.ExecutionResult.success("Updated %d setting(s); save the preset to keep them." % len(changes))


@orca.plugin
class U1Control(orca.base):
    def register_capabilities(self):
        orca.request_permissions(threading=True)
        orca.register_capability(U1ControlPage)
        orca.register_capability(U1PrintSetup)
        orca.register_capability(CheckConnection)
        orca.register_capability(SyncHeadsToProject)
        orca.register_capability(ApplyForkTuning)
