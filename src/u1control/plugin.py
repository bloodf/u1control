"""OrcaSlicer glue: U1 Control tab, U1 print setup (slicing pipeline), the u1control printer agent and helper scripts."""

import json
import os
import pkgutil
import queue
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import weakref

import orca

import agent
import extended as ext
import gcode
import i18n
import peers
import requirements
import settings
import spoolman as sm
import spooler_bridge
import preview
import u1
import usage
from i18n import tr
from moonraker import Moonraker, PrinterError, permission_origin
from service import Service, Target

VERSION = "0.0.0-dev"

_service = None
_service_lock = threading.Lock()
_link = None             # peers.SpoolerLink while the plugin is loaded (U1ControlPage.on_load .. on_unload)
LEDGER_FILE = "usage_ledger.json"
MAX_ORIGINS = 16   # printers and Spoolman addresses remembered for the load-time network permission
_store = None
_store_lock = threading.Lock()
_page_ref = lambda: None   # the U1 Control tab once loaded (weakref)
_pipeline_done = set()   # process presets U1 print setup was already offered for this session
_host_done = set()       # printer presets given U1 Control's address (or told how) this session
_presets_lock = threading.Lock()   # preset edits (begin_update/commit) run one at a time, off the UI thread
_queue_on_main = None    # OrcaSlicer's queue_on_main, once it hands it to the printer agent
UI_WAIT = 5.0            # seconds a script's worker thread waits for the UI thread to read the presets
SETUP_TIMEOUT = 15 * 60  # seconds the print setup window may stay open before the send is abandoned


if __package__:   # the built wheel
    # Imported with the package, not on first use: OrcaSlicer imports the package outside the plugin's audit scope,
    # but a module first imported later (from get_icon) writes its bytecode cache inside it, and that write is an
    # audited "open" on a descriptor, with no path, shown to the user as a permission prompt without a target.
    from . import _assets  # noqa: E402


def _asset(name):
    """Packaged: the icon from _assets, the page from app.html next to the modules (pkgutil reads it from a folder
    or a zip alike). During development: from src/u1control/ui."""
    if __package__:
        if name == "icon.png":
            return _assets.ICON_PNG
        data = pkgutil.get_data(__package__, name)
        if data is None:
            raise FileNotFoundError("%s is missing from the u1control package" % name)
        return data.decode("utf-8")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", name)
    if name.endswith(".png"):
        with open(path, "rb") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


_host_lang = None   # OrcaSlicer's UI language as last read


def _host_language():
    """OrcaSlicer's UI language (`orca.host.app_language()`, e.g. "pt_BR"), or None when the host doesn't offer it.
    The page maps it to a language it has and falls back to the browser's; an explicit choice on the page wins.
    The last answer is kept for the threads where OrcaSlicer doesn't give one (it only changes with a restart)."""
    global _host_lang
    try:
        attr = orca.host.app_language
        lang = attr() if callable(attr) else attr
    except Exception:
        return _host_lang
    if isinstance(lang, str) and lang:
        _host_lang = lang
    return _host_lang


def use_language(cap=None):
    """Python's own texts (errors, notices, the agent's progress in OrcaSlicer's Print dialog) follow the page: the
    language chosen in Settings, else OrcaSlicer's, else English. Never raises.
    cap: the capability asking, when it reads the settings anyway; without one only settings already loaded count,
    so asking for the language never decides where the settings are kept (get_store)."""
    choice = "auto"
    try:
        store = get_store(cap) if cap is not None else _store
        if store is not None:
            choice = store.effective()["ui_language"]
    except Exception as e:
        log("language: settings not readable (%s)" % e)
    i18n.use(i18n.resolve(choice, _host_language()))


def page_html(mode, data=None, language="auto", theme="auto"):
    """The one compiled Vue page (ui/ -> src/u1control/ui/app.html) with its boot payload: the tab ("app") or the
    U1 print setup window ("setup", with the job data). `language`/`theme`: the user's explicit choice, "auto" otherwise."""
    boot = {"mode": mode, "version": VERSION, "lang": _host_language(),
            "pref": language if language in settings.UI_LANGUAGES else "auto",
            "theme": theme if theme in settings.UI_THEMES else "auto"}
    if data is not None:
        boot["data"] = data
    return _asset("app.html").replace("__BOOT__", json_for_html(boot), 1)


def log(msg):
    # stderr: OrcaSlicer tees sys.stderr (not stdout) into <data dir>/log/python_*.log (PythonInterpreter.cpp,
    # install_python_stderr_redirect). Logging must never raise: a Windows console (cp1252) cannot encode "\u2192".
    line = "[u1control] " + str(msg)
    try:
        print(line, file=sys.stderr, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stderr, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc), file=sys.stderr, flush=True)


_storage_dir = None


def _storage():
    """The plugin's storage folder ("" when unknown).

    OrcaSlicer 2.5 only answers plugin.storage() inside a plugin callback (load, tab hooks); from a page message
    or a worker thread it raises "plugin.storage() must be called from a plugin callback". The first answer is
    kept, so later calls from anywhere get the same folder.
    """
    global _storage_dir
    if _storage_dir:
        return _storage_dir
    try:
        _storage_dir = orca.host.plugin.storage() or None
    except Exception as e:
        log("no storage folder (%s)" % e)
    return _storage_dir or ""


def _storage_or_raise():
    folder = _storage()
    if not folder:
        raise RuntimeError("no storage folder")
    return folder


def service(publish=None):
    global _service
    with _service_lock:
        if _service is None:
            folder = _storage()
            _service = Service(publish or (lambda m: None), log,
                               ledger_path=os.path.join(folder, LEDGER_FILE) if folder else None)
            if not folder:
                log("the print ledger stays in memory: pending prints won't survive a restart")
        elif publish is not None:
            _service.publish = publish
        _service.peers = _link
        return _service


def start_link():
    """Say that U1 Control runs, and look for Spooler, through files in Orca's data folder (peers.py)."""
    global _link
    with _service_lock:
        if _link is not None:
            return _link
        root = peers.data_root(_storage())
        if not root:
            log("no OrcaSlicer data folder found; Spooler's stock can't be shown here")
            return None
        _link = peers.SpoolerLink(root, VERSION, log)
        _link.presence.start()
        if _service is not None:
            _service.peers = _link
        return _link


def stop_link():
    global _link
    with _service_lock:
        link, _link = _link, None
        if _service is not None:
            _service.peers = None
    if link is not None:
        link.presence.stop()


def get_store(cap):
    """The shared settings store. The file lives in the plugin's storage folder; without one
    (cloud plugin, nobody signed in) it falls back to `cap`'s config."""
    global _store
    with _store_lock:
        if _store is None:
            try:
                _store = settings.Store(os.path.join(_storage_or_raise(), "settings.json"))
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


def selected_u1_preset(bundle):
    """The selected printer preset when it is a Snapmaker U1, else None."""
    preset = bundle.current_printer_preset()
    return preset if is_u1_name(preset.config_value("printer_model"), preset.name, preset.config_value("inherits")) else None


def preset_value(bundle, preset, key):
    """A printer preset's own value, else the bundle's full config value."""
    return clean(preset.config_value(key)) or clean(bundle.full_config_value(key))


def run_off_thread(fn, timeout=20):
    """Run fn on a plugin worker thread and wait, so network I/O never blocks OrcaSlicer's UI or slicing threads."""
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
        raise PrinterError(tr("the U1 did not answer in %d s") % timeout)
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
        png = _asset("icon.png")
        try:
            folders = [_storage_or_raise(), tempfile.gettempdir()]
        except Exception as e:
            log("icon: no storage folder (%s); using the temp folder" % e)
            folders = [tempfile.gettempdir()]
        for folder in folders:
            # A different base name from the old u1control.svg: OrcaSlicer strips the extension and tries <name>.svg
            # before <name>.png, so a leftover SVG of the same name would win.
            path = os.path.join(folder, "u1control-icon.png")
            try:
                try:
                    with open(path, "rb") as f:
                        same = f.read() == png
                except OSError:
                    same = False
                if not same:
                    with open(path, "wb") as f:
                        f.write(png)
                return path
            except OSError as e:
                log("icon: can't write %s (%s)" % (path, e))
        return ""

    def get_default_config(self):
        return {}

    def get_ui(self):
        use_language(self)
        cfg = self._config()
        return page_html("app", language=cfg["ui_language"], theme=cfg["ui_theme"])

    def _settings(self):
        return get_store(self)

    def _config(self):
        return self._settings().effective()

    def _target(self):
        cfg = self._config()
        host, key = clean(cfg.get("host")), clean(cfg.get("api_key"))
        if not host:
            bundle = orca.host.preset_bundle()
            preset = selected_u1_preset(bundle)
            if preset is None:
                raise ValueError(tr("Select a Snapmaker U1 printer, or set \"host\" in U1 Control's plugin config."))
            host, key = preset_value(bundle, preset, "print_host"), preset_value(bundle, preset, "printhost_apikey")
            if not host:
                raise ValueError(tr("The selected U1 has no address: click the Wi-Fi icon next to the printer and enter its IP."))
        return Target(host, key, settings.printer_label(clean(cfg.get("printer_name"))), clean(cfg.get("spoolman_url")),
                      bool(cfg["spoolman_auto"]), bool(cfg["spoolman_report_usage"]), bool(cfg["spoolman_write_printer"]))

    def on_message(self, data):
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        svc = service(self.post_message)
        try:
            if kind == "hello":
                use_language(self)
                try:
                    self._select(svc)
                except Exception as e:   # no U1 selected (or no address): the page disables every printer control
                    # Settings still needs the config: its form (and Save) stays off without it, and that is where
                    # the empty state sends the user to enter the printer address.
                    self.post_message(self._config_message())
                    self.post_message({"type": "reply", "id": data.get("id"), "error": str(e), "no_target": True})
                    return
                svc.touch(camera=False)
                svc.set_camera_fps(self._config()["camera_fps"])
                svc.submit(data.get("id"), "connect", {})
                self.post_message(self._config_message())
                self._auto_pipeline()
            elif kind == "lease":
                svc.touch(camera=data.get("camera"), screen=data.get("screen"), stock=data.get("stock") is True)
            elif kind == "frame_ack":
                svc.ack_frame()
            elif kind == "cmd":
                svc.touch()
                gen = data.get("gen")
                svc.submit(data.get("id"), data.get("cmd"), data.get("args") or {},
                           gen if isinstance(gen, int) and not isinstance(gen, bool) else None)
            elif kind == "sync_project":
                rid = data.get("id")

                def say(text, done=0, problems=0):
                    # The header button asks with an id and waits for this answer (busy state, tone); the RFID
                    # auto-sync posts without one and gets a notice.
                    if rid is None:
                        self.post_message({"type": "notice", "text": text})
                    else:
                        self.post_message({"type": "reply", "id": rid,
                                           "result": {"text": text, "done": done, "problems": problems}})
                view = svc.last_view
                if data.get("auto") and spooler_keeping_slots():
                    say(tr("Spooler is keeping slots synced"))
                elif not view:
                    say(tr("No printer status yet; try again in a moment."), problems=1)
                else:
                    overrides = self._config()["profile_overrides"]

                    def job():
                        try:
                            done, problems = sync_project(view["heads"], view["rfid"], overrides, bound=bound_spool_lookup(svc))
                            say(sync_message(done, problems), len(done), len(problems))
                        except Exception as e:
                            say(tr("Couldn't update the project filaments: %s") % e, problems=1)
                    if not self._background(job):
                        say(tr("Another preset update is running; try again in a moment."), problems=1)
            elif kind == "requirements":   # Settings > Requirements; recheck: its "Check again" (also looks for Spooler again)
                recheck = bool(data.get("recheck"))
                self.post_message({"type": "requirements", "items": requirements_state(svc, self._config(), recheck)})
                if recheck:   # the Spooler hints elsewhere on the page read the config message
                    self.post_message(self._config_message())
            elif kind == "ui_language":   # the page's language choice; nothing else is touched
                self._settings().update({"ui_language": data.get("value")})
                use_language(self)
            elif kind == "ui_theme":      # the page's light/dark choice; nothing else is touched
                self._settings().update({"ui_theme": data.get("value")})
            elif kind == "camera_fps":    # the camera card's frame rate; an invalid value keeps the stored one
                svc.set_camera_fps(self._settings().update({"camera_fps": data.get("value")})["camera_fps"])
            elif kind == "dashboard":   # the Dashboard's layouts, saved by the page; an invalid value keeps the stored one
                self._settings().update({"dashboard": data.get("value")})
            elif kind == "spoolman_refresh":   # Settings: how often the page re-reads Spoolman; invalid keeps the stored one
                self._settings().update({"spoolman_refresh_s": data.get("value")})
                self.post_message(self._config_message())
            elif kind == "save_settings":
                changes = dict(data.get("settings") or {})
                if changes.get("api_key") == "••••":
                    del changes["api_key"]  # the masked value the page was shown
                self._settings().update(changes)
                result = {"saved": True}
                try:
                    self._select(svc)
                except Exception as e:   # saved, but the new settings name no usable U1
                    result["connect_error"] = str(e)
                self.post_message(self._config_message())
                self.post_message({"type": "reply", "id": data.get("id"), "result": result})
                self._auto_pipeline()
        except Exception as e:
            self.post_message({"type": "reply", "id": data.get("id"), "error": str(e)})

    def _select(self, svc):
        """Point the service at the selected U1; when there is none, stop controlling the previous one."""
        try:
            target = self._target()
        except Exception:
            svc.clear_target()
            raise
        svc.set_target(target)
        try:
            remember_origins(self._settings(), target.host, target.spoolman_url)
        except Exception as e:   # only the next load's permission request misses it
            log("network permission: can't remember %s (%s)" % (target.host, e))

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
                "spooler": spooler, "version": VERSION, "pipeline": pipeline_state()}

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
        """UI thread (page messages, lifecycle events): presets are read here, only the writes run on a plugin
        thread."""
        cfg = self._config()
        try:
            plan = pipeline_plan(cfg)
        except Exception as e:
            log("auto-add U1 print setup failed: %r" % e)
            plan = None
        try:
            hplan = host_plan(cfg)
        except Exception as e:
            log("printer preset address not checked: %r" % e)
            hplan = None
        if hplan is not None and not cfg.get("auto_add_pipeline"):   # Expert, adding off: say how, write nothing
            self.post_message({"type": "notice", "text": tr(NO_PRESET_HOST) % hplan[1]["print_host"]})
            hplan = None
        message = self._config_message()   # the Settings page says whether this preset runs it

        def job():
            try:
                name = apply_pipeline(plan)
                if name:
                    message["pipeline"] = {"preset": name, "on": True}
                    self.post_message({"type": "notice", "text": tr("U1 print setup added to %s; save the preset to keep it") % name})
            except Exception as e:
                log("auto-add U1 print setup failed: %r" % e)
            try:
                name = apply_host(hplan)
                if name:
                    self.post_message({"type": "notice", "text": tr(HOST_ADDED) % name})
            except Exception as e:
                log("printer preset address not set: %r" % e)
                self.post_message({"type": "notice", "text": tr(NO_PRESET_HOST) % hplan[1]["print_host"]})
            self.post_message(message)
        if not self._background(job):   # another preset edit is running: still say which preset is selected now
            if plan is not None:
                _pipeline_done.discard(plan[0])   # not written: offered again on the next event
            if hplan is not None:
                _host_done.discard(hplan[0])
            self.post_message(message)

    def on_lifecycle_event(self, event, ctx):
        kind = getattr(ctx, "msg", "")
        if event == orca.LifecycleEvent.DeviceSelected or (
                event == orca.LifecycleEvent.PresetSelected and kind == "printer"):
            self.post_message({"type": "selection_changed"})
        if (event == orca.LifecycleEvent.PresetSelected and kind in ("print", "process", "printer")) or (
                event == getattr(orca.LifecycleEvent, "ProjectOpened", None)):
            self._auto_pipeline()

    def on_load(self):
        # OrcaSlicer calls this when the plugin loads, whether or not the tab is enabled or shown.
        global _page_ref
        try:
            _page_ref = weakref.ref(self)   # the print setup's "Plugin settings" opens this tab's Settings
        except TypeError as e:   # a host base class without weak references: no "Plugin settings" switch
            log("Plugin settings link off: %r" % e)
        _storage()  # a plugin callback: the one place storage() is sure to answer
        use_language()
        try:
            start_link()
        except Exception as e:   # never fail the plugin load over discovery
            log("Spooler discovery not started: %r" % e)

    def on_unload(self):
        global _service
        stop_link()
        with _service_lock:
            if _service is not None:
                _service.close()
                _service = None


# ====================================================================== requirements

_agent_used = False      # OrcaSlicer connected a printer through U1Agent this session
_agent_selected = None   # cached answer of orca.host.selected_printer(); None = not asked yet


def _field(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _selected_agent_is_ours():
    """Whether OrcaSlicer's selected printer runs through our agent. Host call: UI thread (page message) only.
    OrcaSlicer.conf can't be read from a plugin, so this and _agent_used are the only signs of the preference."""
    try:
        printer = orca.host.selected_printer()
    except Exception as e:   # older OrcaSlicer without the call, or not allowed here
        log("selected printer not readable (%r)" % e)
        return False
    agent_id = _field(printer, "agent") if printer is not None else None
    if agent_id is not None and not isinstance(agent_id, str):
        agent_id = _field(agent_id, "id")
    return clean(agent_id) in (AGENT_ID, AGENT_NAME)


def _agent_seen():
    global _agent_used
    _agent_used = True


def printer_agents_on(recheck=False):
    global _agent_selected
    if _agent_used:
        return True
    if recheck or _agent_selected is None:
        _agent_selected = _selected_agent_is_ours()
    return _agent_selected


def requirements_state(svc, cfg, recheck=False):
    """[{id, status, details}] for Settings > Requirements, from what the plugin already knows (no printer I/O).
    Only asked from a page message, never at import or while OrcaSlicer registers the plugin."""
    with svc.lock:
        firmware, link = dict(svc.firmware), svc.spoolman_link
    return requirements.check(printer_agents_on(recheck), firmware, clean(cfg.get("spoolman_url")), link, spooler_state())


# ====================================================================== print setup

def ensure_pipeline(cfg):
    """pipeline_plan then apply_pipeline, on one thread (tests and callers that are already off the UI thread)."""
    return apply_pipeline(pipeline_plan(cfg))


def pipeline_plan(cfg):
    """UI thread: (process preset name, new slicing_pipeline_plugin value) when "U1 print setup" should be added to
    the selected U1 process preset (once per preset name per session), else None. Only reads presets: OrcaSlicer's
    preset bundle is read on the UI thread, never on a plugin thread."""
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
    return name, value


def apply_pipeline(plan):
    """Plugin thread, never the UI thread (begin_update blocks until the UI thread has applied the change): write a
    pipeline_plan. Returns the preset name when it was added."""
    if plan is None:
        return None
    name, value = plan
    tx = orca.host.preset.process.begin_update("")
    tx.set("slicing_pipeline_plugin", value)
    tx.commit()
    try:
        ui = orca.host.ui
        ui.push_notification(ui.NotificationLevel.RegularNotificationLevel,
                             tr("U1 print setup added to %s; save the preset to keep it") % name)
    except Exception as e:
        log("notification failed: %r" % e)
    return name


HOST_ADDED = "U1 Control's printer address added to %s, so OrcaSlicer's Print button can send to the U1; save the preset to keep it"
NO_PRESET_HOST = ("OrcaSlicer's Print button stays greyed out (only Export G-code) until the U1 printer preset has an "
                  "address: click the Wi-Fi icon next to the printer and enter %s")


def host_plan(cfg):
    """UI thread: (printer preset name, {setting: value}) when the selected U1 printer preset has no address but
    U1 Control has one (Settings > Printer address). Without print_host OrcaSlicer greys out Print and offers only
    Export G-code (MainFrame::can_send_gcode), so U1 print setup never runs. Once per preset name per session;
    None when there is nothing to fill."""
    host = clean(cfg.get("host"))
    if not host:
        return None
    bundle = orca.host.preset_bundle()
    printer = bundle.current_printer_preset()
    if not is_u1_name(printer.config_value("printer_model"), printer.name, printer.config_value("inherits")):
        return None
    if clean(printer.config_value("print_host")) or clean(bundle.full_config_value("print_host")):
        return None
    if printer.name in _host_done:
        return None
    _host_done.add(printer.name)
    values = {"print_host": host}
    key = clean(cfg.get("api_key"))
    if key and not clean(printer.config_value("printhost_apikey")):
        values["printhost_apikey"] = key
    return printer.name, values


def apply_host(plan):
    """Plugin thread (begin_update blocks until the UI thread applied it): write a host_plan into the selected
    printer preset, unsaved like a hand edit. Returns the preset name when written."""
    if plan is None:
        return None
    name, values = plan
    tx = orca.host.preset.printer.begin_update("")
    if tx.target_name != name:   # the user switched printer meanwhile: leave the other preset alone
        _host_done.discard(name)
        return None
    for k, v in values.items():
        tx.set(k, v)
    tx.commit()
    try:
        ui = orca.host.ui
        ui.push_notification(ui.NotificationLevel.RegularNotificationLevel, tr(HOST_ADDED) % name)
    except Exception as e:
        log("notification failed: %r" % e)
    return name


def pipeline_state():
    """{"preset", "on"}: whether the selected U1 process preset runs "U1 print setup" (the toolhead choice);
    None when no U1 printer preset is selected or OrcaSlicer can't tell."""
    try:
        bundle = orca.host.preset_bundle()
        printer = bundle.current_printer_preset()
        if not is_u1_name(printer.config_value("printer_model"), printer.name, printer.config_value("inherits")):
            return None
        return {"preset": bundle.current_process_preset().name,
                "on": settings.PIPELINE_NAME in settings.parse_strings(bundle.full_config_value("slicing_pipeline_plugin"))}
    except Exception as e:
        log("reading the slicing pipeline failed: %r" % e)
        return None


Cancelled = agent.Cancelled   # one "the user said no" for the pipeline and the agent (nothing is sent)


COVER_TEXT = {"off": "left as sliced", "keep-warm": "keep warm", "weak": "weak cooling", "strong": "strong cooling"}


def _cover_text(mode):
    return tr(COVER_TEXT[mode]) if mode in COVER_TEXT else mode


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
        use_language(self)
        try:
            return orca.ExecutionResult.success(self._postprocess(ctx))
        except Cancelled:
            return orca.ExecutionResult.failure(orca.PluginResult.FatalError,
                                                tr("U1 print setup: cancelled, nothing was sent."))
        except Exception as e:
            log("print setup failed: %r" % e)
            return orca.ExecutionResult.failure(orca.PluginResult.FatalError, tr("U1 print setup: %s") % e)

    def _postprocess(self, ctx):
        lines, newline = gcode.read(ctx.gcode_path)
        cfg = gcode.settings(lines)
        if not gcode.is_u1(cfg):
            return tr("not a Snapmaker U1 print; skipped")
        store = self._settings()
        options = store.effective()
        sending = clean(ctx.host) not in ("", "File")
        if not sending:
            lines, mode = gcode.process(lines, cfg, options, version=VERSION)
            gcode.write(ctx.gcode_path, lines, newline)
            return tr("U1 G-code prepared (top cover: %s)") % _cover_text(mode)

        host = clean(ctx.config_value("print_host"))
        if not host:
            raise PrinterError(tr("no U1 address set: click the Wi-Fi icon next to the printer and enter its IP"))
        key = clean(ctx.config_value("printhost_apikey"))
        client = Moonraker(host, key, timeout=5)
        status = run_off_thread(lambda: client.query(u1.STATUS_OBJECTS))
        view = u1.summarize(status)
        if u1.machine_busy(view):
            raise PrinterError(tr("the U1 is busy (%s); wait for it to finish first")
                               % (view["machine_state"] or view["state"]).lower())
        if agent.setup_done(lines):   # this G-code went through print setup already: no second window or script
            return tr("U1 print setup already done for this G-code; nothing sent again")
        filaments = gcode.filaments(lines, cfg)
        heads = view["heads"]
        ace = u1.multiace(view)   # multiACE routes the filaments: no mapping, the file left as sliced
        mapping = {} if ace else u1.auto_map(filaments, heads)
        prefs = self._offered_prefs(options, view["options"])
        purifier, commands, choice = options["purifier"], False, None
        if options["print_dialog"]:
            cancel = getattr(ctx, "cancelled", None) or getattr(ctx, "canceled", None)

            def slicing_cancelled():
                try:
                    return bool(cancel() if callable(cancel) else cancel)
                except Exception:
                    return False
            choice = open_setup(store, options, view, host, client, lines, cfg, filaments, mapping, prefs,
                                clean(getattr(ctx, "output_name", "")), slicing_cancelled)
            mapping, prefs, purifier, commands = choice["map"], choice["prefs"], choice["purifier"], choice["commands"]
            heads = choice.get("heads") or heads
        else:
            problems = u1.mapping_warnings(filaments, heads, mapping)
            if problems:
                raise PrinterError(tr("%s. Turn on \"Show print setup before sending\" to choose toolheads.") % "; ".join(problems))
        if not ace:
            lines, mode = gcode.process(lines, cfg, {**options, **cover_fans(prefs), "purifier": purifier}, mapping,
                                        heads, VERSION)
            lines = gcode.stored_pressure_advance(lines, (choice or {}).get("pa"))
        _still_valid(ctx, host, client, heads, mapping)   # after the G-code work: checked right before the send
        script = u1.preprint_script(mapping, prefs, commands)
        if script:
            run_off_thread(lambda: client.gcode(script))
        if not ace:   # marked done only once the script went
            gcode.write(ctx.gcode_path, lines + [agent.SETUP_DONE], newline)
        if choice:
            remember_choice(store, options, choice)
        store.update({"printed_before": True})
        filename = clean(getattr(ctx, "output_name", "")) or os.path.basename(ctx.gcode_path)
        service().remember_job(filename, mapping, filaments, host=host, api_key=key, options={
            "printer_name": settings.printer_label(clean(options.get("printer_name"))),
            "spoolman_url": clean(options.get("spoolman_url")),
            "spoolman_report_usage": bool(options.get("spoolman_report_usage", True))})
        return tr("sent to %s: %s") % (client.address, script.replace("\n", " | "))

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





SETUP_COMMANDS = ("spools", "set_filament", "bind_spool", "unbind_spool")   # Heads settings in the print setup


def cover_fans(prefs):
    """The top-cover fan speeds chosen in the print setup, for gcode.process."""
    return {k: prefs[k] for k in u1.COVER_FANS if k in prefs}


def printer_commands(client):
    """The printer's command list (GET /printer/gcode/help), read once per print setup; empty when unreadable,
    which offers only the original options."""
    try:
        return run_off_thread(client.gcode_commands, timeout=10)   # never on the slicing or UI thread
    except Exception as e:
        log("command list not read (%s); only the basic print options are offered" % e)
        return frozenset()


def setup_pa(heads, spools, client):
    """{head: PA} stored on the bound spools for the nozzles the heads have; the printer's nozzle diameters are read
    only when a bound spool has stored values. {} when none or unreadable."""
    if not any((sp or {}).get("pa") for sp in (spools or {}).values()):
        return {}
    try:
        status = run_off_thread(lambda: client.query({"configfile": ["settings"]}), timeout=10)
        diameters = u1.nozzle_diameters((status.get("configfile") or {}).get("settings"))
    except Exception as e:
        log("nozzle diameters not read (%s); stored pressure advance not offered" % e)
        return {}
    return u1.stored_pa(heads, diameters, spools)


def setup_job(lines, cfg, name, client):
    """The print shown at the top of the print setup, from the sliced G-code only: name, time, weight, layers,
    tool changes, plate preview and the top-down path preview."""
    return {**gcode.summary(lines, cfg), "name": name, "address": client.address, "thumbnail": gcode.thumbnail(lines),
            "tool_changes": preview.tool_changes(lines), "preview": preview.paths(lines)}


def rfid_flags(view):
    """[bool] per toolhead: it read an RFID tag. With "official", what the Dashboard calls a tagged head."""
    return [bool(tag) for tag in (view.get("rfid") or [])]


def setup_spools(host):
    """{"<toolhead>": {"name", "colour"}} for the heads linked to a Spoolman spool, from what the U1 Control tab
    already read (no network); {} while it isn't running or follows another printer."""
    with _service_lock:
        svc = _service
    try:
        return svc.spool_names(host) if svc is not None else {}
    except Exception as e:
        log("spool names not read: %r" % e)
        return {}


def remember_choice(store, options, choice):
    """"Remember these options" ticked: the next print setup starts from these options."""
    if choice.get("remember"):
        store.update({"prefs": choice["prefs"], "stored_pa": bool(choice.get("stored_pa")),
                      **({"purifier": choice["purifier"]} if options["mode"] == settings.EXPERT else {})})


def open_setup(store, options, view, host, client, lines, cfg, filaments, mapping, prefs, name, cancelled,
               keep_map=False):
    """Everything the print setup needs, then the window (job thread). prefs: the basic options as offered so far;
    the extra ones are offered only when the printer has their command. Returns ask_setup's answer plus
    "commands". keep_map: the slots came from OrcaSlicer's Print dialog, so a refresh of the toolheads keeps them.
    The caller remembers the options (remember_choice) only after the send went through."""
    commands = printer_commands(client)
    saved = options["prefs"] if options["remember_print_options"] else {}
    offered = {**prefs, **u1.offered_extras(saved, view, commands)}
    extras = {"printer": {"name": settings.printer_label(clean(options.get("printer_name"))),
                          "busy": u1.machine_busy(view), "address": host},
              "spools": setup_spools(host), "remember": bool(options["remember_print_options"]),
              "features": u1.features(commands), "tags": rfid_flags(view), "keep_map": keep_map,
              "multiace": u1.multiace(view), "stored_pa": bool(options.get("stored_pa")),
              "ui_theme": options["ui_theme"]}
    if not extras["multiace"]:
        extras["pa"] = setup_pa(view["heads"], extras["spools"], client)
    choice = ask_setup(setup_job(lines, cfg, name, client), cancelled, filaments, view["heads"], mapping, offered,
                       options["purifier"], client, extras, options["ui_language"], host)
    return {**choice, "commands": commands}   # remembered by the caller once the print was accepted


def _run_setup_command(window, host, msg, refresh, stop):
    """Heads settings in the print setup: the Dashboard's own commands, run by the U1 Control service when it
    follows this printer. Replies {"type": "reply", "id", "result" | "error"} to the window. Nothing runs once the
    window was answered or closed (stop set)."""
    cmd, rid, args = msg.get("cmd"), msg.get("id"), msg.get("args") or {}
    if stop.is_set():
        return
    try:
        with _service_lock:
            svc = _service
        if cmd not in SETUP_COMMANDS or not isinstance(args, dict):
            raise ValueError(tr("unknown command"))
        if svc is None or svc.target is None or svc.target.ident != usage.printer_ident(host):
            raise PrinterError(tr("open the U1 Control tab for this printer to change its toolheads"))
        reply = {"type": "reply", "id": rid, "result": getattr(svc, "cmd_" + cmd)(**args)}
    except Exception as e:
        reply = {"type": "reply", "id": rid, "error": str(e)}
    if stop.is_set():
        return
    try:
        window.post(reply)
    except Exception as e:   # the window closed meanwhile
        log("print setup reply not shown: %r" % e)
    refresh()


def show_settings_tab():
    """The print setup's "Plugin settings": the U1 Control tab opens its Settings (no host call can bring a tab
    forward; it shows there once this window is closed). Runs in a host UI callback: never raises."""
    try:
        page = _page_ref()
        if page is not None:
            page.post_message({"type": "show_tab", "tab": "settings"})
    except Exception as e:
        log("Plugin settings not opened: %r" % e)


def _clean_answer(answer, filaments, mapping, shown, prefs, purifier, remember_default, ace=False):
    """The window's answer, checked: toolheads in range, warnings acknowledged for the toolheads shown last,
    only offered options (u1.pick_prefs), the exhaust fan left out while the cover recirculates. ace: multiACE
    routes the filaments, so there is no mapping to take or check."""
    if not isinstance(answer, dict) or answer.get("cancelled"):
        raise Cancelled()
    chosen = {}
    for f, t in ({} if ace else answer.get("map") or {}).items():
        if str(f).isdigit() and isinstance(t, int) and not isinstance(t, bool) and 0 <= t < u1.TOOLHEADS \
                and int(f) in mapping:
            chosen[int(f)] = t
    final = {**mapping, **chosen}
    warned = u1.warning_ids(filaments, shown, final)
    acked = answer.get("acknowledged")
    if warned and (not isinstance(acked, list) or sorted(str(x) for x in acked) != sorted(warned)):
        raise PrinterError(tr("the print setup has warnings (%s) that weren't confirmed for these toolheads; "
                              "nothing was sent") % "; ".join(u1.mapping_warnings(filaments, shown, final)))
    purifier = answer.get("purifier") if answer.get("purifier") in ("auto", "off", *u1.PURIFIER) else purifier
    picked = u1.pick_prefs(prefs, answer.get("prefs") if isinstance(answer.get("prefs"), dict) else {})
    mode = u1.purifier_mode(filaments) if purifier == "auto" else purifier
    if u1.exhaust_blocked(mode):
        picked.pop("exhaust_fan", None)
    remember = answer.get("remember")
    return {"map": final, "prefs": picked, "purifier": purifier, "heads": shown,
            "remember": remember if isinstance(remember, bool) else remember_default}


# The print setup page, boot data included. OrcaSlicer 2.5.1 on Windows (WebView2) showed a blank window for a
# 1.78 MB page (1.2 MB app + a 540 KB path preview) and the page as expected at 1.24 MB.
SETUP_PAGE_LIMIT = 1_450_000
# WebView2 takes a page as at most 2 MiB of base64, so 1,572,864 bytes of HTML; a bigger page renders blank.
WEBVIEW_PAGE_LIMIT = 1_572_864
# OrcaSlicer creates the window later, on its UI thread (orca.host.ui.create_window queues it with CallAfter), and
# runs this post-process on the slicing thread. Its UI thread can be busy for a while (loading the G-code preview of
# a long print) or blocked waiting for the slicing thread; ctx.cancelled() stays False at this step, so the plugin
# can't tell the two apart. It waits this long for the window, then gives up so a blocked OrcaSlicer recovers.
SETUP_SHOW_WAIT = 60
# First thing in the page, before its 1.4 MB of script: says the window exists. From then on the user sees it and
# can close it, so a page that loads slowly is waited for.
SHOWN_PING = "<script>try{window.orca.postMessage({shown:true})}catch(e){}</script>"


def ask_setup(job, cancelled, filaments, heads, mapping, prefs, purifier, client, extras=None, language="auto",
              host=""):
    """Show the U1 print setup window and wait for the answer (call from a worker thread, never the UI thread:
    the window itself is created on the UI thread by OrcaSlicer). cancelled() -> True closes it.
    Returns {"map", "prefs", "purifier", "heads", "remember"}; raises Cancelled, or PrinterError (timeout, window
    never shown, warnings not acknowledged for the toolheads shown last)."""
    extras = extras or {}
    ui = orca.host.ui
    data = {
        "job": job, "filaments": filaments, "heads": heads, "map": {str(k): v for k, v in mapping.items()},
        "prefs": prefs, "labels": {p[0]: p[2] for p in u1.PREFERENCES},
        "levels": {k: list(v) for k, v in u1.LEVELS.items()}, "features": extras.get("features") or [],
        "purifier": purifier, "auto_purifier": u1.purifier_mode(filaments),
        "printer": extras.get("printer"), "spools": extras.get("spools") or {},
        "remember": bool(extras.get("remember", True)), "tags": extras.get("tags") or [],
        "keep_map": bool(extras.get("keep_map")), "multiace": bool(extras.get("multiace")),
        "pa": {str(t): v for t, v in (extras.get("pa") or {}).items()}, "stored_pa": bool(extras.get("stored_pa")),
    }
    html = page_html("setup", data, language=language, theme=extras.get("ui_theme", "auto"))
    if len(html.encode("utf-8")) > SETUP_PAGE_LIMIT and (data["job"] or {}).get("preview"):
        # A page this big stays blank in OrcaSlicer's WebView2 on Windows (never "ready": the window times out).
        log("print setup: the plate preview makes the page %d bytes; shown without it" % len(html.encode("utf-8")))
        data["job"] = {**data["job"], "preview": None}
        html = page_html("setup", data, language=language, theme=extras.get("ui_theme", "auto"))
    if len(html.encode("utf-8")) > WEBVIEW_PAGE_LIMIT and (data["job"] or {}).get("thumbnail"):
        log("print setup: the G-code thumbnail makes the page %d bytes; shown without it" % len(html.encode("utf-8")))
        data["job"] = {**data["job"], "thumbnail": None}
        html = page_html("setup", data, language=language, theme=extras.get("ui_theme", "auto"))
    html = html.replace("<head>", "<head>" + SHOWN_PING, 1)
    done, alive, wanted, stop = (threading.Event() for _ in range(4))
    result = {}
    window_box = []
    shown = [heads]   # the toolheads the window shows now; the choice is checked against them

    def refresher():   # one long-lived thread; refresh requests that arrive while it is busy coalesce
        while not stop.is_set():
            if not wanted.wait(0.5):
                continue
            wanted.clear()
            try:
                view = u1.summarize(client.query(u1.STATUS_OBJECTS))
                fresh = view["heads"]
                shown.append(fresh)
                window_box[0].post({"heads": fresh, "busy": u1.machine_busy(view), "spools": setup_spools(host),
                                    "tags": rfid_flags(view),
                                    "map": {str(k): v for k, v in u1.auto_map(filaments, fresh).items()}})
            except Exception as e:
                log("refresh failed: %s" % e)

    def on_message(msg):
        if not isinstance(msg, dict):
            return
        if msg.get("shown") or msg.get("ready"):
            alive.set()
        if msg.get("refresh") and window_box:
            wanted.set()
        if msg.get("type") == "cmd" and window_box:
            threading.Thread(target=_run_setup_command, args=(window_box[0], host, msg, wanted.set, stop),
                             name="u1control-setup-cmd", daemon=True).start()
        if msg.get("open_settings"):
            show_settings_tab()

    def on_submit(msg):
        result["data"] = msg
        done.set()

    def asked_to_stop():
        try:
            return bool(cancelled and cancelled())
        except Exception:
            return False

    window = ui.create_window(html, title=tr("U1 Control — print setup"), width=900, height=820,
                              on_message=on_message, on_close=done.set, on_submit=on_submit, style=ui.WINDOW_MODAL)
    window_box.append(window)
    threading.Thread(target=refresher, name="u1control-refresh", daemon=True).start()
    started = time.monotonic()
    try:
        while not done.wait(0.25):  # never wait forever on a window the UI thread never shows
            waited = time.monotonic() - started
            if asked_to_stop():
                window.close()
                raise Cancelled()
            if waited > SETUP_TIMEOUT:
                window.close()
                raise PrinterError(tr("print setup timed out; nothing was sent"))
            if not window.is_open():
                break
            if not alive.is_set() and waited > SETUP_SHOW_WAIT:
                window.close()
                raise PrinterError(tr("the print setup window didn't open (OrcaSlicer was busy); nothing was sent"))
    finally:
        stop.set()
    answer = _clean_answer(result.get("data"), filaments, mapping, shown[-1], prefs, purifier, data["remember"],
                           extras.get("multiace"))
    use_pa = isinstance(result.get("data"), dict) and result["data"].get("stored_pa") is True
    stored = {int(t): v for t, v in data["pa"].items()} if use_pa else {}
    return {**answer, "stored_pa": use_pa, "pa": {t: stored[t] for t in set(answer["map"].values()) if t in stored}}


HEAD_FACTS = ("loaded", "type", "colour", "vendor", "official")


def _still_valid(ctx, host, client, heads, mapping):
    """Right before anything is written or sent: same printer address, the U1 still idle, and the toolheads
    the print uses still hold what the user saw. Otherwise nothing is sent."""
    if clean(ctx.config_value("print_host")) != host:
        raise PrinterError(tr("the printer address changed while the print setup was open; nothing was sent"))
    view = u1.summarize(run_off_thread(lambda: client.query(u1.STATUS_OBJECTS)))
    if u1.machine_busy(view):
        raise PrinterError(tr("the U1 became busy (%s); nothing was sent")
                           % (view["machine_state"] or view["state"]).lower())
    for t in sorted(set(mapping.values())):
        if any(heads[t].get(k) != view["heads"][t].get(k) for k in HEAD_FACTS):
            raise PrinterError(tr("T%d changed after you chose the toolheads; nothing was sent. Send again.") % (t + 1))


# ====================================================================== printer agent

pa = orca.printer_agent
AGENT_ID = "u1control"
AGENT_NAME = "Snapmaker U1 (u1control)"
JOBS_DIR = "jobs"        # under the plugin storage: OrcaSlicer denies tempfile.* off the main thread
# OrcaSlicer status codes (src/slic3r/Utils/bambu_networking.hpp, v2.5.0)
OK, ERR_INVALID_HANDLE, ERR_CANCELED, ERR_INVALID_RESULT = 0, -1, -18, -19
ERR_LP_UPLOAD, ERR_LP_PUBLISH, ERR_SG_UPLOAD, ERR_CONNECT = -4020, -4030, -5010, -6010
STAGE_CREATE, STAGE_UPLOAD, STAGE_SENDING, STAGE_FINISHED, STAGE_ERROR = 0, 1, 3, 6, 7
AGENT_POLL = 2.0         # s between status queries while OrcaSlicer is connected to the U1
CATALOG_EVERY = 30.0     # s between re-reads of Spooler's presets, profiles.json and the Spoolman links for tray ids


URGENT_KINDS = ("pause", "resume", "stop")   # Device tab commands sent at once, on their own thread
DEVICE_GCODE_TIMEOUT = 600   # s: a Device tab G-code line may run long (homing, heating), as the console's cmd_gcode


def host_of(address):
    """'http://192.168.1.5:7125/x' -> '192.168.1.5:7125' (scheme and path stripped; Moonraker keeps the port)."""
    return clean(address).split("://", 1)[-1].split("/", 1)[0]


def _hostname(address):
    """The host name alone: 'http://192.168.1.5:7125/x' and '192.168.1.5' are the same U1."""
    address = clean(address)
    return urllib.parse.urlsplit(address if "://" in address else "http://" + address).hostname or ""


def base_url(host, port="", use_ssl=False):
    """MRA normalize_base_url: http(s)://host[:port][/prefix]. A port already in the host wins; so does an https
    scheme, and a path prefix (a reverse proxy) is kept."""
    address = clean(host)
    scheme, _, rest = address.rpartition("://")
    host, _, prefix = rest.partition("/")
    has_port = host.rsplit("]", 1)[-1].count(":") == 1
    port = clean(str(port or ""))
    scheme = "https" if use_ssl or scheme.lower() == "https" else "http"
    prefix = prefix.split("?", 1)[0].split("#", 1)[0].strip("/")
    return "%s://%s%s%s" % (scheme, host, ":" + port if port and not has_port else "", "/" + prefix if prefix else "")


def network_grants(cap):
    """scheme://host of the printer and Spoolman set in the settings or used before (remember_origins), for the
    load-time permission request. A new address is left to the runtime prompt until the next load."""
    addresses = []
    try:   # never presets here: reading them while OrcaSlicer loads them crashed 2.5.1
        cfg = get_store(cap).effective()
        addresses += [clean(cfg.get("host")), clean(cfg.get("spoolman_url"))] + cfg["network_origins"]
    except Exception as e:
        log("network permission: settings not readable at load (%s)" % e)
    return _origins(addresses)


def _origins(addresses):
    out = []
    for origin in map(permission_origin, filter(None, addresses)):
        if origin and origin not in out:
            out.append(origin)
    return out


def remember_origins(store, *addresses):
    """Keep the scheme://host of a printer or Spoolman in use, so the next load asks for it once (network_grants)."""
    known = store.effective()["network_origins"]
    merged = _origins(known + list(addresses))
    if merged != known:
        store.update({"network_origins": merged[-MAX_ORIGINS:]})


def slicer_temp_root():
    """OrcaSlicer's per-user temp folder, where Print and Send write the sliced job (OrcaSlicer.cpp per_user_temp_dir):
    "<temp>/orcaslicer_<uid>" on macOS and Linux, "<temp>" on Windows."""
    base = tempfile.gettempdir().rstrip("/\\") or os.sep
    return base if os.name == "nt" else os.path.join(base, "orcaslicer_%d" % os.getuid())


def job_read_grants():
    """Read grants for the sliced job: the realpath form first (/private/var/... on macOS), then as given."""
    out = []
    for form in (os.path.realpath(slicer_temp_root()), slicer_temp_root()):
        target = form.rstrip("/\\") + "/*"
        if target not in out:
            out.append(target)
    return out


def call_safely(key, fn, *args):
    """Run a host callback queued to OrcaSlicer's UI thread. Nothing may escape: an exception leaving a queued call
    ends OrcaSlicer (GUI_App::OnExceptionInMainLoop returns false)."""
    try:
        fn(*args)
    except Exception as e:   # pybind's error_already_set arrives as an Exception too; never re-raised
        try:
            log("host callback %s failed: %r" % (key, e))
        except Exception:
            pass


class U1Agent(pa.PrinterAgentBase):
    """Printer agent `u1control`: OrcaSlicer's Print / Send dialog and Device tab for the U1, with the same toolhead
    map, print options and G-code fixes as U1 print setup. Printer I/O runs on the agent's own threads."""

    def __init__(self):
        super().__init__()
        self._cb = {}
        self._lock = threading.Lock()
        self.selected = ""
        self.dev_id, self.host, self.api_key = "", "", ""
        self.client = None
        self.view = None
        self.firmware = ""
        self._catalog = ([], "", None)       # (Spooler presets, printer label, Spooler's profiles.json) for tray ids
        self._catalog_at = 0.0
        self._mine = []                      # user_presets(), for spools linked to one of them (orca_filament_preset)
        self._links = ([], {})               # (spools, {toolhead: spool id}) the agent read from Spoolman itself
        self._links_busy = threading.Lock()
        self.base = ""
        self.camera_url = ""                 # the Device tab's camera (agent.camera_source), read at each connect
        self.camera_mode = "None_"
        self._camera_watched = None          # time.monotonic() the Device tab last asked for the camera URL
        self._monitor_at = None              # time.monotonic() of the last camera.start_monitor
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._commands = queue.Queue()   # Device tab commands, run in order by one worker (_command_worker)
        self._worker = None

    def get_name(self):
        return AGENT_NAME

    def get_agent_info(self):
        use_language()
        return pa.AgentInfo(AGENT_ID, AGENT_NAME, VERSION, tr("Snapmaker U1 over Moonraker, by u1control"))

    def _settings(self):
        return get_store(self)

    # host callbacks: stored, may be None -------------------------------------------------------------
    def _store_cb(self, key, fn):
        with self._lock:
            self._cb[key] = fn
        return OK

    def set_on_ssdp_msg_fn(self, fn): return self._store_cb("ssdp", fn)
    def set_on_local_connect_fn(self, fn): return self._store_cb("local_connect", fn)
    def set_on_local_message_fn(self, fn): return self._store_cb("local_message", fn)
    def set_on_message_fn(self, fn): return self._store_cb("message", fn)
    def set_on_user_message_fn(self, fn): return self._store_cb("user_message", fn)
    def set_on_printer_connected_fn(self, fn): return self._store_cb("printer_connected", fn)
    def set_on_subscribe_failure_fn(self, fn): return self._store_cb("subscribe_failure", fn)
    def set_server_callback(self, fn): return self._store_cb("server_error", fn)
    def set_queue_on_main_fn(self, fn):
        global _queue_on_main
        _queue_on_main = fn   # also for the scripts' preset reads (on_ui_thread)
        return self._store_cb("queue_on_main", fn)

    def _emit(self, key, *args):
        """Call a host callback the way MoonrakerPrinterAgent dispatches: through queue_on_main when set."""
        with self._lock:
            fn, queue = self._cb.get(key), self._cb.get("queue_on_main")
        if fn is None:
            return
        try:
            if queue is not None:
                queue(lambda: call_safely(key, fn, *args))
            else:
                fn(*args)
        except Exception as e:
            log("host callback %s failed: %r" % (key, e))

    def _dev_id(self):
        with self._lock:
            return self.dev_id

    def _message(self, payload):
        self._emit("local_message", self._dev_id(), json.dumps(payload))

    # discovery and selection ---------------------------------------------------------------------------
    def _announce_host(self):
        """The U1 to list in the Device tab: the connected one, else U1 Control's own "host", else the selected U1
        printer preset's address; "" when there is none. OrcaSlicer lists printers before it connects."""
        with self._lock:
            host = self.host
        return host or host_of(clean(self._settings().effective().get("host"))) or self._preset_host()

    @staticmethod
    def _preset_host():
        """The selected U1 printer preset's address, read on OrcaSlicer's UI thread; "" (and why, in the log) if none."""
        def read():
            bundle = orca.host.preset_bundle()
            preset = selected_u1_preset(bundle)
            return None if preset is None else host_of(preset_value(bundle, preset, "print_host"))
        try:
            host = on_ui_thread(read)
        except Exception as e:
            log("agent: discovery lists nothing: the selected printer's address is not readable (%s)" % e)
            return ""
        if host is None:
            log("agent: discovery lists nothing: the selected printer is not a Snapmaker U1")
        elif not host:
            log("agent: discovery lists nothing: no U1 address set (set the printer preset's host to the U1's IP)")
        return host or ""

    def start_discovery(self, start, sending):
        host = self._announce_host() if start else ""   # never a network scan (MRA announce_printhost_device)
        if host:
            self._emit("ssdp", json.dumps({
                "dev_name": "Snapmaker U1", "dev_id": self.dev_id or host, "dev_ip": host,
                "dev_type": agent.U1_MODEL_ID, "dev_signal": "0", "connect_type": "lan", "bind_state": "free",
                "sec_link": "secure", "ssdp_version": "v1"}))
        return True

    def get_user_selected_machine(self):
        return self.selected

    def set_user_selected_machine(self, dev_id):
        self.selected = dev_id or ""
        return OK

    def bind_detect(self, dev_ip, sec_link, detect):
        detect.dev_id = self.dev_id if self.host and self.host == host_of(dev_ip) else dev_ip
        detect.dev_name, detect.model_id = "Snapmaker U1", agent.U1_MODEL_ID
        detect.version = self.firmware
        detect.connect_type, detect.bind_state = "lan", "free"
        return OK

    # connection -------------------------------------------------------------------------------------------
    def connect_printer(self, params):
        """UI thread: remember the printer and start the status thread (which does all the I/O)."""
        host = host_of(getattr(params, "host", ""))
        if not host or not getattr(params, "dev_id", ""):
            return ERR_INVALID_HANDLE
        self.disconnect_printer()
        _agent_seen()   # OrcaSlicer uses us as the printer agent: its "Use printer agents" preference is on
        key = clean(getattr(params, "password", ""))
        # the address as given: an https scheme or a reverse-proxy path prefix is part of how the U1 is reached
        base = base_url(getattr(params, "host", ""), getattr(params, "port", ""), bool(getattr(params, "use_ssl", False)))
        client = Moonraker(base, key, timeout=5)
        try:
            remember_origins(self._settings(), base)
        except Exception as e:   # only the next load's permission request misses it
            log("network permission: can't remember %s (%s)" % (base, e))
        self._catalog_at = 0.0   # the first push re-reads Spooler's profiles.json
        with self._lock:   # one step: a reader under the lock never sees the new printer with the old one's id
            self.dev_id, self.host, self.api_key, self.base = params.dev_id, host, key, base
            self.firmware = ""   # another printer, or the same one updated meanwhile
            self.client = client
            self._stop = threading.Event()
            stop = self._stop
        self._links = ([], {})   # another printer's links never reach this one's trays
        self._refresh_catalog()
        threading.Thread(target=self._poll, args=(stop, client), name="u1control-agent", daemon=True).start()
        return OK

    def disconnect_printer(self):
        with self._lock:
            self._stop.set()
            self.view, self.client, self.camera_url, self.camera_mode = None, None, "", "None_"
            self._monitor_at = None
            while True:   # queued commands were for this printer: drop them (the worker also checks the client)
                try:
                    if self._commands.get_nowait() is None:
                        self._commands.put(None)   # keep a pending worker stop
                        break
                except queue.Empty:
                    break
        self._wake.set()
        return OK

    def on_load(self):
        try:
            removed = agent.sweep_jobs(self._work_dir())
        except Exception as e:   # no storage folder yet: nothing of ours to sweep
            log("agent: work files not checked (%s)" % e)
            return
        if removed:
            log("agent: removed %d work file(s) left by an earlier session" % removed)

    def on_unload(self):
        self.disconnect_printer()
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                self._commands.put(None)
            self._worker = None

    def _refresh_catalog(self, profiles=None):
        """UI thread, no I/O: re-read Spooler's presets (it adds its own at any time), then the toolheads' links
        from Spoolman on a thread of their own, so sync from AMS knows them without the tab ever opening."""
        try:
            presets, label = filament_catalog()
            mine = _user_presets_safe()
            cfg = self._settings().effective()
        except Exception as e:
            log("agent: filament presets not readable (%s); trays show generic presets" % e)
            return
        self._mine = mine
        self._catalog = (presets, label, profiles if profiles is not None else self._catalog[2])
        args = (clean(cfg.get("spoolman_url")), settings.printer_label(clean(cfg.get("printer_name"))))
        threading.Thread(target=self._load_links, args=args, name="u1control-links", daemon=True).start()

    def _load_links(self, url, printer_name):
        """Spools and links by Spoolman location ("<printer name> T<n>"), through the U1's own Spoolman link
        when it has one, else url."""
        with self._lock:
            client = self.client
        if client is None or not self._links_busy.acquire(blocking=False):
            return   # not connected, or the last read is still running
        try:
            smc = sm.Spoolman(url, client)
            smc.connect()
            spools = [sm.spool_view(s) for s in smc.spools()]
            self._links = (spools, sm.bindings_from_locations(spools, printer_name))
        except Exception as e:   # no Spoolman, or it is down: keep the last links
            log("agent: Spoolman links for the Device tab not read (%s)" % e)
        finally:
            self._links_busy.release()

    def _bound_spools(self):
        """{toolhead index: Spoolman spool} for this U1's toolheads linked to spools: the tab's (up to date with
        every link made there, Extended Firmware's too) when it shows this U1, else the agent's own read."""
        svc = _service
        spools, bindings = self._links
        if svc is not None:
            with svc.lock:
                if svc.target and _hostname(svc.target.host) == _hostname(self.host) and svc.spools:
                    spools, bindings = list(svc.spools), dict(svc.bindings)
        by_id = {s["id"]: s for s in spools}
        return {h: by_id[sid] for h, sid in bindings.items() if sid in by_id}

    def _preferred(self):
        """preferred(head) for agent.push_status: the filament_id of the head's spool's preset, or ""."""
        with self._lock:
            on_main = self._cb.get("queue_on_main")
        if time.time() - self._catalog_at >= CATALOG_EVERY:   # this thread may read files, not presets
            self._catalog_at = time.time()
            profiles = spooler_bridge.read_json(spooler_dir(), spooler_bridge.PROFILES_FILE)
            if on_main is not None:
                on_main(lambda: self._refresh_catalog(profiles or {}))
        bound = self._bound_spools()
        presets, label, profiles = self._catalog
        mine = self._mine

        if mine and on_main is not None:   # ponytail: no readable user preset at all -> no notice; Apply gives one
            for index, spool in bound.items():
                text = link_notice(index + 1, spool.get("orca_preset"), mine)
                if text:
                    on_main(lambda text=text: call_safely("notice", notify, text))

        def preferred(head):   # a linked standalone user preset first, else the Spooler preset
            spool = bound.get(head["index"])
            return linked_filament_id(spool, mine) or spooler_bridge.tray_filament_id(spool, presets, profiles, label)
        return preferred

    def _poll(self, stop, client):
        connected, thumb = False, (None, "")   # thumb: (file name, its thumbnail URL), read once per file
        logged_unreachable = False   # the current run of failed reads is in the log
        while not stop.is_set():
            try:
                if not self.firmware:
                    firmware = str((client.info() or {}).get("software_version") or "")
                    with self._lock:   # as the view below: never about the printer of an earlier connection
                        if stop.is_set():
                            return
                        self.firmware = firmware
                view = u1.summarize(client.query(u1.STATUS_OBJECTS))
                with self._lock:   # a disconnect or reconnect meanwhile: this answer is about the old printer
                    if stop.is_set():
                        return
                    self.view = view
                logged_unreachable = False
                if not connected:
                    connected = True   # MRA perform_connection_async: ConnectStatusOk, then printer_connected
                    threading.Thread(target=self._read_camera, args=(stop, client), name="u1control-camera",
                                     daemon=True).start()   # never holds up the status push
                    dev_id = self._dev_id()
                    self._emit("local_connect", 0, dev_id, "0")
                    self._emit("printer_connected", dev_id)
                if view.get("filename") != thumb[0]:
                    thumb = (view.get("filename"), self._thumbnail(client, view.get("filename")))
                self._message(agent.push_status(view, self._preferred(), thumb[1]))
                self._keep_camera(stop, client)
            except Exception as e:
                if connected:
                    log("agent: the U1 stopped answering (%s)" % e)
                elif not logged_unreachable:
                    log("agent: the U1 did not answer the first status read (%s)" % e)
                logged_unreachable = True
                connected = False
                with self._lock:
                    if not stop.is_set():
                        self.view = None   # Device tab commands answer "not connected" instead of queueing
            self._wake.wait(AGENT_POLL)
            self._wake.clear()

    @staticmethod
    def _thumbnail(client, filename):
        """The Device tab's picture of the file the U1 prints or printed last, or "" (no file, no thumbnail)."""
        if not filename:
            return ""
        try:
            return agent.thumbnail_url(client.metadata(filename.lstrip("/")), filename, client.base or "")
        except Exception as e:   # no metadata (file gone, or not a print file): OrcaSlicer's placeholder
            log("agent: thumbnail of %s not read (%s)" % (filename, e))
            return ""

    def _read_camera(self, stop, client):
        try:
            webcams = client.request("GET", "/server/webcams/list")
        except Exception as e:   # no webcam API (stock firmware): its own camera picture
            log("agent: webcam list not read (%s); the stock camera picture" % e)
            webcams = None
        mode, url = agent.camera_source(webcams, client.base or "")
        with self._lock:   # as the poll: never about an earlier connection's printer
            if not stop.is_set():
                self.camera_mode, self.camera_url = mode, url
        self._wake.set()

    def _keep_camera(self, stop, client):
        """Poll thread: while the Device tab shows the stock camera picture, ask the U1 to keep renewing it."""
        now = time.monotonic()
        with self._lock:
            stock = self.camera_url.endswith(agent.STOCK_CAMERA)
            if not stock or stop.is_set() or not agent.monitor_due(now, self._camera_watched, self._monitor_at):
                return
            self._monitor_at = now

        def start():
            try:   # registered for websocket clients only (as service._push_frame)
                client.ws_call("camera.start_monitor", {"domain": "lan", "interval": 0}, timeout=4)
            except Exception as e:
                log("agent: camera.start_monitor: %s" % e)
        threading.Thread(target=start, name="u1control-camera-monitor", daemon=True).start()

    def get_camera_stream_mode(self):
        return getattr(pa.CameraStreamMode, self.camera_mode, pa.CameraStreamMode.None_) if self.camera_url \
            else pa.CameraStreamMode.None_

    def get_camera_url(self):
        self._camera_watched = time.monotonic()   # OrcaSlicer asks on every Device tab update while it shows the U1
        return self.camera_url

    def command_start_camera(self, dev_id):
        """The Device tab's Play: renew the stock camera picture now rather than at the next keepalive."""
        with self._lock:
            self._camera_watched, self._monitor_at = time.monotonic(), None
        self._wake.set()
        return OK

    # Device tab commands ------------------------------------------------------------------------------------
    def send_message(self, dev_id, json_str, qos, flag):
        return self.send_message_to_printer(dev_id, json_str, qos, flag)

    def send_message_to_printer(self, dev_id, json_str, qos, flag):
        command = agent.parse_command(json_str)
        kind = command["kind"]
        if kind == "invalid":
            return ERR_INVALID_RESULT
        if kind == "unsupported":
            return agent.UNSUPPORTED
        if kind == "get_version":
            self._message(agent.version_reply(self.firmware))
            return OK
        if kind == "get_access_code":
            self._message(agent.access_code_reply(self.api_key))
            return OK
        if kind == "pushall":
            self._wake.set()
            return OK
        if kind == "noop":
            return OK
        with self._lock:
            client, view = self.client, self.view
        if client is None or view is None:
            return ERR_CONNECT
        if kind in URGENT_KINDS:   # never behind a long G-code line in the queue (as the tab's URGENT/DEDICATED)
            threading.Thread(target=self._run_command, args=(client, command), name="u1control-device-urgent",
                             daemon=True).start()
            return OK
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._command_worker, name="u1control-device", daemon=True)
                self._worker.start()
        self._commands.put((client, command))
        return OK

    def _command_worker(self):
        """One thread runs the Device tab's G-code lines and light switch in the order they came. A command queued
        for a printer that is no longer the connected one is dropped, never sent."""
        while True:
            item = self._commands.get()
            if item is None:
                return
            client, command = item
            with self._lock:
                current = self.client
            if client is not current:
                log("agent: Device tab %s dropped: the printer was disconnected" % command["kind"])
                continue
            self._run_command(client, command)

    def _run_command(self, client, command):
        kind, ok = command["kind"], False
        try:
            if kind == "pause":
                client.pause()
            elif kind == "resume":
                client.resume()
            elif kind == "stop":
                client.cancel()
            elif kind == "set_light":
                client.gcode(agent.LIGHT_ON if command["on"] else agent.LIGHT_OFF)
            elif kind == "gcode":
                if agent.guarded_line(command["script"]):   # home, heaters, fans: as the tab, only on an idle U1
                    why = agent.line_refusal(command["script"], u1.summarize(client.query(u1.STATUS_OBJECTS)))
                    if why:
                        raise PrinterError(why)
                client.gcode(command["script"], timeout=DEVICE_GCODE_TIMEOUT)
            ok = True
        except Exception as e:
            log("agent: Device tab %s failed: %s" % (kind, e))
        if kind == "gcode":
            self._message(agent.gcode_reply(command["seq"], command["script"], ok))
        self._wake.set()

    # jobs (OrcaSlicer's job threads: blocking is fine) ---------------------------------------------------------
    def _job_client(self, params):
        """The printer the job names (PrintParams.dev_ip, as OrcaSlicer's Multi-device tab sends it), else the
        connected one. Never the connected U1 for a job that names another."""
        address = clean(getattr(params, "dev_ip", ""))
        asked = host_of(address)
        with self._lock:
            connected, key, base = self.host, self.api_key, self.base
        host = asked or connected
        if not host:
            raise PrinterError(tr(NO_ADDRESS))
        if host != connected:   # another U1: its own address and key from the job
            key, base = clean(getattr(params, "password", "")), base_url(address)
        return host, key, Moonraker(base, key, timeout=10)

    @staticmethod
    def _job_path(params):
        dst = clean(getattr(params, "dst_file", ""))
        return dst if dst and os.path.exists(dst) else clean(params.filename)

    @staticmethod
    def _progress(update_fn):
        last = [-1]

        def progress(sent, total):
            pct = int(sent * 100 / total) if total else 100
            if update_fn and pct != last[0]:
                last[0] = pct
                update_fn(STAGE_UPLOAD, pct, tr("Uploading G-code..."))
        return progress

    @staticmethod
    def _fail(update_fn, code, error):
        log("agent: job failed (%d): %s" % (code, error))
        if update_fn:
            update_fn(STAGE_ERROR, code, "U1: %s" % error)
        return code

    @staticmethod
    def _work_dir():
        return os.path.join(_storage_or_raise(), JOBS_DIR)

    def start_send_gcode_to_sdcard(self, params, update_fn, cancel_fn, wait_fn):
        use_language(self)
        try:
            host, key, client = self._job_client(params)
            if getattr(params, "project_name", "") == "verify_job":   # PrintJob.cpp: a connectivity check only
                client.info()
                return OK
            if update_fn:
                update_fn(STAGE_CREATE, 0, tr("Preparing..."))
            options = self._settings().effective()
            agent.send_job(client, self._job_path(params), clean(params.project_name) or clean(params.task_name),
                           getattr(params, "plate_index", 1), options, VERSION, self._work_dir(),
                           self._progress(update_fn), cancel_fn)
        except agent.Cancelled:
            return ERR_CANCELED
        except Exception as e:
            return self._fail(update_fn, ERR_SG_UPLOAD, e)
        if update_fn:
            update_fn(STAGE_FINISHED, 100, tr("File uploaded"))
        return OK

    def start_local_print(self, params, update_fn, cancel_fn):
        use_language(self)
        if update_fn:
            update_fn(STAGE_CREATE, 0, tr("Preparing..."))
        if cancel_fn and cancel_fn():
            return ERR_CANCELED
        stage = ["prepare"]

        def on_stage(name):
            stage[0] = name
            if update_fn and name == "start":
                update_fn(STAGE_SENDING, 0, tr("Starting print..."))
        try:
            host, key, client = self._job_client(params)
            options = self._settings().effective()
            task = {"bed_leveling": getattr(params, "task_bed_leveling", False),
                    "flow_cali": getattr(params, "task_flow_cali", False),
                    "timelapse": getattr(params, "task_record_timelapse", False)}
            name = clean(params.project_name) or clean(params.task_name)
            job = agent.run_job(client, self._job_path(params), name,
                                getattr(params, "plate_index", 1), getattr(params, "ams_mapping", ""), options,
                                lambda view: U1PrintSetup._offered_prefs(options, view["options"]), task, VERSION,
                                self._work_dir(), self._progress(update_fn), cancel_fn, on_stage,
                                self._chooser(options, host, name, client, cancel_fn))
        except agent.Cancelled:
            return ERR_CANCELED
        except Exception as e:
            return self._fail(update_fn, ERR_LP_UPLOAD if stage[0] == "upload" else ERR_LP_PUBLISH, e)
        log("agent: sent %s to %s: %s" % (job["filename"], host, job["script"].replace("\n", " | ")))
        if job.get("choice"):
            remember_choice(self._settings(), options, job["choice"])
        self._settings().update({"printed_before": True})
        try:
            service().remember_job(job["filename"], job["mapping"], job["filaments"], host=host, api_key=key, options={
                "printer_name": settings.printer_label(clean(options.get("printer_name"))),
                "spoolman_url": clean(options.get("spoolman_url")),
                "spoolman_report_usage": bool(options.get("spoolman_report_usage", True))})
        except Exception as e:   # the print runs; only the filament booking is lost
            log("agent: filament use not recorded: %r" % e)
        self._wake.set()
        if update_fn:
            update_fn(STAGE_FINISHED, 100, tr("Print started"))
        return OK

    def _chooser(self, options, host, name, client, cancel_fn):
        """prepare_gcode's choose: U1 print setup after OrcaSlicer's Print dialog, on this job thread, starting
        from the dialog's slots and options. None (OrcaSlicer's choice as is) when the setting is off."""
        def choose(view, filaments, mapping, prefs, lines, cfg):
            if not options["print_dialog"]:
                return None
            return open_setup(self._settings(), options, view, host, client, lines, cfg, filaments, mapping, prefs,
                              name, cancel_fn, keep_map=True)
        return choose

    def start_local_print_with_record(self, params, update_fn, cancel_fn, wait_fn):
        return self.start_local_print(params, update_fn, cancel_fn)

    def start_print(self, params, update_fn, cancel_fn, wait_fn):
        return agent.UNSUPPORTED   # cloud printing: the U1 is driven over the LAN only

    def start_sdcard_print(self, params, update_fn, cancel_fn):
        """Print a file already on the U1 with the printer's own toolhead map and options."""
        name = os.path.basename(clean(getattr(params, "dst_file", "")) or clean(params.filename))
        use_language()
        try:
            _, _, client = self._job_client(params)
            if u1.machine_busy(u1.summarize(client.query(u1.STATUS_OBJECTS))):
                raise PrinterError(tr("the U1 is busy; wait for it to finish first"))
            client.print_start(name)
        except Exception as e:
            return self._fail(update_fn, ERR_LP_PUBLISH, e)
        if update_fn:
            update_fn(STAGE_FINISHED, 100, tr("Print started"))
        return OK

    # no binding or certificates on this printer -------------------------------------------------------------
    def check_cert(self): return OK
    def install_device_cert(self, dev_id, lan_only): return None
    def ping_bind(self, ping_code): return OK
    def bind(self, dev_ip, dev_id, dev_model, sec_link, timezone, improved, update_fn): return OK
    def unbind(self, dev_id): return OK
    def request_bind_ticket(self): return (OK, "")

    # filaments ----------------------------------------------------------------------------------------------
    def get_filament_sync_mode(self):
        return pa.FilamentSyncMode.Subscription

    def fetch_filament_info(self, dev_id, sync_mode=None):
        self._wake.set()   # the next push carries the toolheads
        return True


NO_ADDRESS = "no U1 address set: set the printer preset's host to the U1's IP"


# ====================================================================== scripts

def _selected_u1():
    bundle = orca.host.preset_bundle()
    preset = bundle.current_printer_preset()
    host = clean(preset.config_value("print_host")) or clean(bundle.full_config_value("print_host"))
    key = clean(preset.config_value("printhost_apikey")) or clean(bundle.full_config_value("printhost_apikey"))
    if not host:
        raise ValueError(tr("Select your Snapmaker U1 printer and set its IP (Wi-Fi icon next to the printer)."))
    return Moonraker(host, key, timeout=5)


def on_ui_thread(fn):
    """fn() run on OrcaSlicer's UI thread through queue_on_main, from a worker thread (a script, a preset job); its
    result, or its exception raised here. Waits at most UI_WAIT seconds; on the main thread fn runs at once. Without queue_on_main (OrcaSlicer hands it only to a
    printer agent it has created) fn runs here: after start-up the presets are loaded, so this is the old behaviour,
    not the load-time race."""
    queue = _queue_on_main
    if queue is None or threading.current_thread() is threading.main_thread():   # already on it: never wait on itself
        return fn()
    box, done = {}, threading.Event()

    def task():
        try:
            box["value"] = fn()
        except Exception as e:   # handed back to the worker
            box["error"] = e
        finally:
            done.set()
    queue(lambda: call_safely("script", task))
    if not done.wait(UI_WAIT):
        raise TimeoutError(tr("OrcaSlicer did not answer in time; try again"))
    if "error" in box:
        raise box["error"]
    return box["value"]


class CheckConnection(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Check U1 connection"

    def execute(self):
        use_language()
        try:
            client = on_ui_thread(_selected_u1)
            info, ext_status = run_off_thread(lambda: (client.info(), ext.Extended(client).status()))
            heads = run_off_thread(lambda: u1.summarize(client.query(u1.STATUS_OBJECTS))["heads"])
        except Exception as e:
            return orca.ExecutionResult.skipped(tr("Couldn't reach the U1: %s") % e)
        fw = u1.detect_firmware(info, ext_status)   # as the tab does: the version alone misses some Extended builds
        loaded = ", ".join("T%d %s" % (h["index"] + 1, ("%s %s" % (h["type"], h["colour"] or "")).strip()
                                       if h["loaded"] else tr("not named") if h.get("unnamed") else tr("empty")) for h in heads)
        about = tr("U1 at %s (Extended Firmware %s)") if fw["kind"] == "extended" else tr("U1 at %s (official firmware %s)")
        return orca.ExecutionResult.success("%s. %s" % (about % (client.address, fw["version"]), loaded))


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
        return spooler_bridge.data_dir(_storage_or_raise())
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


def filament_catalog():
    """(Spooler presets, printer label) for the Device tab's tray ids; UI thread, no I/O. Presets: the Spooler
    presets OrcaSlicer counts as compatible with the selected printer, the only ones its sync from AMS loads, as
    spooler_bridge.tray_filament_id meta."""
    bundle = orca.host.preset_bundle()
    printer = bundle.current_printer_preset()
    collection = bundle.filaments
    presets = []
    for i in range(collection.size()):
        preset = collection.preset(i)
        # is_compatible defaults to False here and in user_presets: OrcaSlicer 2.5 binds it, and a host that doesn't
        # can't say a preset suits the printer, which sync from AMS (is_compatible) and a link both need.
        if (getattr(preset, "bundle_id", "") or "") != spooler_bridge.BUNDLE_ID or not getattr(preset, "is_compatible", False):
            continue
        first = lambda key: (spooler_bridge.as_list(preset.config_value(key)) or [""])[0]   # noqa: E731
        presets.append({"name": preset.name, "bundle_id": spooler_bridge.BUNDLE_ID, "vendor": first("filament_vendor"),
                        "colour": first("default_filament_colour") or first("filament_colour")})
    return presets, clean(printer.config_value("printer_model")) or printer.name


def user_presets():
    """UI thread, no I/O: the filament presets a Spoolman preset link may name, the user's own (not system or
    default, not a plugin's `_local/` one) and compatible with the selected printer: [{"name", "file", "inherits"}]."""
    collection = orca.host.preset_bundle().filaments
    out = []
    for i in range(collection.size()):
        preset = collection.preset(i)
        if preset.name.startswith("_local/") or not getattr(preset, "is_compatible", False) or not preset.is_user():   # default: filament_catalog
            continue
        out.append({"name": preset.name, "file": getattr(preset, "file", "") or "",
                    "inherits": clean(preset.config_value("inherits"))})
    return out


def _user_presets_safe():
    """user_presets(), or [] when OrcaSlicer won't answer (logged once): a link problem never stops the rest."""
    try:
        return user_presets()
    except Exception as e:
        if "user_presets" not in _logged_once:
            _logged_once.add("user_presets")
            log("user filament presets not readable (%r); Spoolman preset links are ignored" % e)
        return []


def linked_preset(name, presets):
    """The user_presets() entry a spool's orca_filament_preset names: the exact name, else the only one equal
    ignoring case; None when there is none."""
    if not name:
        return None
    exact = [p for p in presets if p["name"] == name]
    loose = exact or [p for p in presets if p["name"].casefold() == name.casefold()]
    return loose[0] if len(loose) == 1 else None


def linked_filament_id(spool, presets):
    """filament_id a tray reports for a spool linked to a standalone user preset, or "". OrcaSlicer's sync from AMS
    (PresetBundle::sync_ams_list) loads only a preset that is its own base: one that inherits has its parent's id
    and the sync would load the parent. Reads the preset's file (OrcaSlicer's API doesn't show filament_id)."""
    preset = linked_preset((spool or {}).get("orca_preset"), presets)
    if not preset or preset["inherits"] or not preset["file"]:
        return ""
    path = preset["file"]
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        mtime = None
    cached = _file_ids.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, encoding="utf-8") as f:
            fid = json.load(f).get("filament_id")
        fid = fid.strip() if isinstance(fid, str) else ""
    except (OSError, ValueError, AttributeError) as e:
        log("agent: %s not readable (%s); the tray keeps its usual id" % (path, e))   # once per file version
        fid = ""
    _file_ids[path] = (mtime, fid)
    return fid


def link_notice(slot, name, presets):
    """The notice for a toolhead whose orca_filament_preset names no usable preset, once per name per session
    (Apply and AMS sync share it); "" when it is fine or was said already."""
    if not name:
        return ""
    if linked_preset(name, presets):
        _links_warned.discard(name)   # fixed: if it breaks again, say so again
        return ""
    if name in _links_warned:
        return ""
    _links_warned.add(name)
    if sum(p["name"].casefold() == name.casefold() for p in presets) > 1:
        return tr("T%d: several user presets match \"%s\" ignoring case; write the exact name. The usual preset is used") % (slot, name)
    return tr("T%d: no compatible user preset \"%s\" in OrcaSlicer, so the usual preset is used") % (slot, name)


def notify(text):
    """UI thread: an OrcaSlicer notification."""
    ui = orca.host.ui
    ui.push_notification(ui.NotificationLevel.RegularNotificationLevel, text)


_links_warned = set()   # orca_filament_preset names already given a notice, this session
_file_ids = {}          # preset file -> (mtime, filament_id) for linked_filament_id
_logged_once = set()


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
    problem = spooler_bridge.profiles_problem(profiles)
    if problem:
        log("Spooler's %s can't be used (%s); matching presets by colour" % (spooler_bridge.PROFILES_FILE, problem))

    def prefer(names, head, tag):
        spool = bound(head["index"])
        return spooler_bridge.preset_for_spool(presets, spool, profiles, printer_label) if spool else None
    return prefer


def _sync_reads(with_printer):
    """UI thread: what sync_project needs from the presets, as plain data (filament_meta, the selected printer's
    name, inherits and model when with_printer, and user_presets)."""
    meta = filament_meta()
    if not with_printer:
        return meta, None, _user_presets_safe()
    printer = orca.host.preset_bundle().current_printer_preset()
    return meta, {"name": printer.name, "inherits": clean(printer.config_value("inherits")),
                  "model": clean(printer.config_value("printer_model"))}, _user_presets_safe()


def sync_project(heads, tags, overrides=None, preset_preference=None, bound=None):
    """Apply each loaded toolhead's best filament preset and colour to project slot n+1.
    A bound spool's orca_filament_preset (a user preset) comes first, then Spooler's presets for heads with a bound
    spool (bound: head index -> spool). Returns (done, problems) as lists of strings."""
    meta, printer, mine = on_ui_thread(lambda: _sync_reads(preset_preference is None and bool(bound)))
    names = [m["name"] for m in meta]
    colours = {m["name"]: m["colour"] for m in meta}
    if printer is not None:
        presets = spooler_bridge.spooler_presets(meta, (printer["name"], printer["inherits"]))
        if presets:
            preset_preference = spooler_preference(presets, bound, printer["model"] or printer["name"])
    done, problems = [], []
    colour_ok = True   # OrcaSlicer 2.5 refuses filament_colour here: a project setting, not a filament preset one
    for head in heads:
        tag = (tags[head["index"]] if head["index"] < len(tags or []) else None) or None
        if not head["loaded"] and not tag:
            continue
        slot = head["index"] + 1
        link = ((bound(head["index"]) if bound else None) or {}).get("orca_preset")
        linked = linked_preset(link, mine)
        notice = link_notice(slot, link, mine)
        if notice:
            problems.append(notice)
        preset_name = linked["name"] if linked else pick_filament_preset(
            names, head, tag, overrides, preference=preset_preference, colours=colours)
        colour = (tag or {}).get("colour") or head["colour"]
        try:
            try:
                _set_slot(slot, preset_name, colour if colour_ok else "")
            except Exception as e:
                if not (colour and colour_ok and "filament_colour" in str(e)):
                    raise
                colour_ok = False   # the preset still counts; colours stay as they are for every slot
                log("project sync: this OrcaSlicer doesn't take filament_colour from a plugin (%s); colours left as they are" % e)
                problems.append(tr("colours weren't changed: this OrcaSlicer doesn't let plugins set filament colours; "
                                   "set them by hand"))
                _set_slot(slot, preset_name, "")
            done.append("%d: %s" % (slot, preset_name or (tag or head).get("type") or "?"))
        except Exception as e:
            problems.append(tr("filament %d: %s") % (slot, e))
    return done, problems


def _set_slot(slot, preset_name, colour):
    """Project slot `slot`'s filament preset, and its colour when given (accepted by OrcaSlicer before 2.5)."""
    tx = orca.host.preset.filament.begin_update(slot, preset_name)
    if colour:
        tx.set("filament_colour", colour)
    tx.commit()


def sync_message(done, problems):
    message = tr("Project filaments %s") % (", ".join(done) or tr("unchanged"))
    return message + (tr(". Problems: %s") % "; ".join(problems) if problems else "")


class SyncHeadsToProject(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Sync U1 toolheads to project filaments"

    def execute(self):
        use_language(self)
        try:
            client = on_ui_thread(_selected_u1)
            view = run_off_thread(lambda: u1.summarize(client.query(u1.STATUS_OBJECTS)))
        except Exception as e:
            return orca.ExecutionResult.skipped(tr("Couldn't reach the U1: %s") % e)
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


def _tuning_reads():
    """UI thread: (process preset name, tuning_changes) for the selected U1, or (None, []) when it is not a U1."""
    bundle = orca.host.preset_bundle()
    printer = bundle.current_printer_preset()
    if not is_u1_name(printer.config_value("printer_model"), printer.name, printer.config_value("inherits")):
        return None, []
    process = bundle.current_process_preset()
    keys = [k for k, _ in FORK_PROCESS_TUNING] + ["layer_height"]
    return process.name, tuning_changes(process.name, {k: bundle.full_config_value(k) for k in keys})


class ApplyForkTuning(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Apply Snapmaker Orca U1 process tuning"

    def execute(self):
        use_language()
        try:
            name, changes = on_ui_thread(_tuning_reads)   # the presets are read on the UI thread; the write below not
        except TimeoutError as e:
            return orca.ExecutionResult.skipped(str(e))
        if name is None:
            return orca.ExecutionResult.skipped(tr("Select a Snapmaker U1 printer first."))
        if not changes:
            return orca.ExecutionResult.success(tr("\"%s\" already matches Snapmaker Orca.") % name)
        listing = "\n".join("  %s: %s -> %s" % c for c in changes)
        if orca.host.ui.message(tr("Change the process preset \"%s\" to Snapmaker Orca's U1 values?\n\n%s\n\n"
                                "The preset stays unsaved until you save it.") % (name, listing),
                                title="U1 Control", buttons="yes_no", icon="question") != "yes":
            return orca.ExecutionResult.skipped(tr("No changes made."))
        tx = orca.host.preset.process.begin_update("")
        for key, _, value in changes:
            tx.set(key, value)
        tx.commit()
        return orca.ExecutionResult.success(tr("Updated %d setting(s); save the preset to keep them.") % len(changes))


@orca.plugin
class U1Control(orca.base):
    def register_capabilities(self):
        # Network I/O runs on the plugin's own worker threads; downloads are saved under ~/Downloads/u1control.
        # (Declarations match exact target strings, so the folder is informational for the user.)
        # The printer agent reads the sliced job from OrcaSlicer's temp folder (job_read_grants).
        # The printer and Spoolman are asked for once each, as scheme://host (every port and path on it): a runtime
        # approval only covers the exact URL it saw (GitHub #48).
        grants = {"threading": True, "fs_read": job_read_grants(),
                  "fs_readwrite": [os.path.join(os.path.expanduser("~"), "Downloads", "u1control")]}
        _storage()
        network = network_grants(self)
        try:
            orca.request_permissions(**grants, network_http=network)
        except TypeError:   # an OrcaSlicer without network targets: each URL is asked for when first used
            orca.request_permissions(**grants)
        orca.register_capability(U1ControlPage)
        orca.register_capability(U1PrintSetup)
        orca.register_capability(CheckConnection)
        orca.register_capability(SyncHeadsToProject)
        orca.register_capability(ApplyForkTuning)
        orca.register_capability(U1Agent)
