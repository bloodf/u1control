"""Test doubles: a fake `orca` module and a fake U1 (Moonraker + Spoolman) HTTP server."""

import json
import sys
import tempfile
import threading
import types
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ---------------------------------------------------------------------- printer

def task_config():
    return {
        "filament_vendor": ["Snapmaker", "Generic", "NONE", "Generic"],
        "filament_type": ["PLA", "PETG", "NONE", "PLA"],
        "filament_sub_type": ["Basic", "Basic", "NONE", "Matte"],
        "filament_color_rgba": ["FF0000FF", "FFFFFFFF", "FFFFFFFF", "000000FF"],
        "filament_color_multi": [{"nums": 1, "alpha": 255, "colors": ["FF0000"], "mode": 0}] * 4,
        "filament_official": [True, False, False, False],
        "filament_exist": [True, True, False, True],
        "auto_bed_leveling": False, "flow_calibrate": True, "time_lapse_camera": False,
        "auto_replenish_filament": True, "end_unload_filament": [False, False, False, False],
    }


def fake_tag_info(tags):
    return [tags.get(t, {"VENDOR": "NONE", "MAIN_TYPE": "NONE"}) for t in range(4)]


class FakePrinter:
    def __init__(self, version="2.0.0.205", state="standby", extended=False, spoolman=False):
        self.version, self.state, self.extended, self.spoolman = version, state, extended, spoolman
        self.scripts, self.deleted, self.started = [], [], []
        self.files = {}   # "camera/t.mp4" -> bytes served under /server/files/
        self.task = task_config()
        self.tags = {}   # head -> filament_detect info dict
        self.spools = [
            {"id": 7, "location": "", "remaining_weight": 800,
             "filament": {"name": "Matte Black", "material": "PLA", "color_hex": "111111", "vendor": {"name": "Generic"}}},
            {"id": 9, "location": "", "remaining_weight": 500,
             "filament": {"name": "Fire Red", "material": "PLA", "color_hex": "EE1111", "vendor": {"name": "Snapmaker"}}},
            {"id": 11, "location": "", "remaining_weight": 900,
             "filament": {"name": "White", "material": "PETG", "color_hex": "FAFAFA", "vendor": {"name": "Generic"}}},
        ]
        self.patches, self.uses = [], []
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def host(self):
        return "127.0.0.1:%d" % self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def status(self):
        return {"print_stats": {"state": self.state, "filename": "a.gcode", "print_duration": 60,
                                "total_duration": 70, "info": {"current_layer": 3, "total_layer": 10}},
                "webhooks": {"state": "ready"}, "print_task_config": self.task,
                "toolhead": {"extruder": "extruder1"}, "heater_bed": {"temperature": 60.0, "target": 60},
                "extruder": {"temperature": 210.0, "target": 210}, "led cavity_led": {"color_data": [[0, 0, 0, 1]]},
                "purifier": {"power_detected": True}, "display_status": {"progress": 0.3},
                "filament_detect": {"info": fake_tag_info(self.tags)},
                "filament_feed left": {"extruder0": {"channel_state": "load_finish", "filament_detected": True}}}

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    return json.loads(raw or b"{}")
                except ValueError:
                    return {}

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                if u.path == "/printer/info":
                    return self._send(200, {"result": {"software_version": fake.version, "state": "ready", "hostname": "u1"}})
                if u.path == "/printer/objects/query":
                    return self._send(200, {"result": {"status": fake.status()}})
                if u.path == "/server/webcams/list":
                    return self._send(200, {"result": {"webcams": []}})
                if u.path == "/server/files/directory":
                    return self._send(200, {"result": {"dirs": [{"dirname": "sub"}, {"dirname": ".thumbs"}],
                                                       "files": [{"filename": "a.gcode", "size": 10, "modified": 2},
                                                                 {"filename": "b.gcode", "size": 20, "modified": 5}],
                                                       "disk_usage": {"free": 100}}})
                if u.path == "/server/files/metadata":
                    return self._send(200, {"result": {"filename": q.get("filename"), "filament_weights": [3.5, 0, 0, 1.5]}})
                if u.path == "/server/spoolman/status":
                    return self._send(200, {"result": {"spoolman_connected": fake.spoolman, "spool_id": None}})
                if u.path == "/firmware-config/api/status":
                    if fake.extended:
                        return self._send(200, {"Version": fake.version, "Profile": "extended"})
                    return self._send(200, b"<html>fluidd</html>", "text/html")
                if u.path == "/firmware-config/api/settings":
                    return self._send(200, {"settings": [{"id": "ssh", "current": "false", "options": ["false", "true"]}]})
                rel = urllib.parse.unquote(u.path[len("/server/files/"):])
                if u.path.startswith("/server/files/") and rel in fake.files:
                    return self._send(200, fake.files[rel], "application/octet-stream")
                if u.path == "/api/v1/health":
                    return self._send(200, {"status": "healthy"})
                if u.path == "/api/v1/spool":
                    return self._send(200, fake.spools)
                return self._send(404, {"error": {"message": "not found"}})

            def do_POST(self):
                u = urllib.parse.urlsplit(self.path)
                body = self._body()
                if u.path == "/printer/gcode/script":
                    if fake.state == "printing" and "SET_PRINT_EXTRUDER_MAP" in body.get("script", ""):
                        return self._send(400, {"error": {"message": "printing"}})
                    fake.scripts.append(body.get("script"))
                    return self._send(200, {"result": "ok"})
                if u.path == "/printer/print/start":
                    fake.started.append(body.get("filename"))
                    return self._send(200, {"result": "ok"})
                if u.path.startswith("/firmware-config/api/settings/"):
                    return self._send(200, b"running...\nSUCCESS: Setting updated successfully\n", "text/plain")
                return self._send(404, {"error": {"message": "not found"}})

            def do_PATCH(self):
                sid = int(self.path.rsplit("/", 1)[-1])
                body = self._body()
                fake.patches.append((sid, body))
                for s in fake.spools:
                    if s["id"] == sid:
                        s.update(body)
                return self._send(200, {})

            def do_PUT(self):
                fake.uses.append((int(self.path.split("/")[-2]), self._body()))
                return self._send(200, {})

            def do_DELETE(self):
                fake.deleted.append(urllib.parse.unquote(urllib.parse.urlsplit(self.path).path))
                return self._send(200, {"result": {}})

        return Handler


# ---------------------------------------------------------------------- orca

class FakeWindow:
    def __init__(self, on_message, on_submit, answer):
        self.on_message, self.on_submit, self.answer, self.open, self.posted = on_message, on_submit, answer, True, []
        on_message({"ready": True})
        on_submit(answer)

    def is_open(self):
        return self.open

    def close(self):
        self.open = False

    def post(self, data):
        self.posted.append(data)


def install_orca(answer=None, preset=None, filament_names=(), filament_meta=None, bundle_ids=(), storage=None):
    """Register a fake `orca` module. answer: what the print setup pop-up submits."""
    orca = types.ModuleType("orca")
    orca.windows = []

    class Base:
        _stored = None

        def get_config(self):
            return json.dumps(self._stored if self._stored is not None else self.get_default_config())

        def save_config(self, text):
            self._stored = json.loads(text)
            return True

        def get_default_config(self):
            return {}

        def post_message(self, data):
            self.posted = getattr(self, "posted", []) + [data]

    class Result:
        def __init__(self, status, message=""):
            self.status, self.message = status, message

    orca.ExecutionResult = types.SimpleNamespace(
        success=lambda message="", data="": Result("success", message),
        skipped=lambda message="": Result("skipped", message),
        failure=lambda status, message, data="": Result("failure", message))
    orca.PluginResult = types.SimpleNamespace(FatalError="fatal", RecoverableError="recoverable")
    orca.LifecycleEvent = types.SimpleNamespace(DeviceSelected=1, PresetSelected=2, ProjectOpened=3)
    orca.slicing = types.SimpleNamespace(SlicingPipelineCapabilityBase=Base,
                                         Step=types.SimpleNamespace(psGCodePostProcess="post", psSkirtBrim="brim"))
    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=Base)
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=Base)
    orca.base = object
    orca.registered = []
    orca.plugin = lambda cls: cls
    orca.register_capability = orca.registered.append
    orca.request_permissions = lambda **kw: None

    def create_window(html, title="", width=0, height=0, on_message=None, on_close=None, on_submit=None, style=None):
        w = FakeWindow(on_message, on_submit, answer if answer is not None else {"map": {}, "prefs": {}, "purifier": "auto"})
        w.html = html
        orca.windows.append(w)
        return w

    preset = preset or {}
    filament_meta = filament_meta or {}
    names = list(filament_names)

    class FPreset:
        def __init__(self, name):
            self.name = name
            self.bundle_id = filament_meta.get(name, {}).get("bundle_id", "")

        def config_value(self, key):
            return filament_meta.get(self.name, {}).get(key)

    class Preset:
        name = preset.get("name", "Snapmaker U1 (0.4 nozzle)")
        file = ""

        def config_value(self, key):
            return preset.get(key)

    bundle = types.SimpleNamespace(current_printer_preset=lambda: Preset(),
                                   current_process_preset=lambda: Preset(),
                                   full_config_value=lambda k: preset.get(k),
                                   filaments=types.SimpleNamespace(preset_names=lambda: list(filament_names),
                                                                   size=lambda: len(names), preset=lambda i: FPreset(names[i])))
    orca.filament_calls = []
    orca.process_calls, orca.notifications = [], []

    class Tx:
        def __init__(self, slot, name):
            self.slot, self.name, self.values = slot, name, {}

        def set(self, key, value):
            self.values[key] = value

        def commit(self):
            orca.filament_calls.append((self.slot, self.name, self.values))

    def begin_update(slot, name):
        if slot == 99:
            raise RuntimeError("no such slot")
        return Tx(slot, name)

    class ProcessTx(Tx):
        def commit(self):
            orca.process_calls.append((self.name, self.values))
            preset["slicing_pipeline_plugin"] = self.values.get("slicing_pipeline_plugin")

    store_dir = storage or tempfile.mkdtemp()
    orca.host = types.SimpleNamespace(
        preset=types.SimpleNamespace(filament=types.SimpleNamespace(begin_update=begin_update),
                                     process=types.SimpleNamespace(begin_update=lambda name: ProcessTx(0, name)),
                                     bundles=types.SimpleNamespace(list_ids=lambda: list(bundle_ids))),
        ui=types.SimpleNamespace(create_window=create_window, WINDOW_MODAL=1, message=lambda *a, **k: "yes",
                                 NotificationLevel=types.SimpleNamespace(RegularNotificationLevel=1),
                                 push_notification=lambda level, text, **k: orca.notifications.append(text)),
        preset_bundle=lambda: bundle, plugin=types.SimpleNamespace(storage=lambda: store_dir))
    sys.modules["orca"] = orca
    return orca
