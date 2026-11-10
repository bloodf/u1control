"""Fill the screenshot frames in the u1control brand images with real renders of the plugin's pages.

What it does
  * Builds dist/u1control_any.whl, loads it against the fake `orca` module (tests/fakes.py) and takes the
    real app.html / setup.html it serves.
  * Injects a stub `window.orca` that answers the page's messages with realistic fake printer data
    (built from tests/fakes.FakePrinter + u1.summarize, so the shapes are exactly what the plugin sends),
    then screenshots each page with headless Chrome at 2x.
  * Composites the screenshot into the empty frame of each SVG template (parsed from the SVG itself,
    rounded to the frame radius, border kept) and exports the PNG over the existing one.
  * Inlines Spooler's full-colour icon (../spooler/assets/spooler-icon.svg) into the Spooler integration
    SVGs and re-exports their PNGs. The other SVG templates are never changed.

Needs: Python 3 (stdlib only) and Google Chrome (override with CHROME=/path/to/chrome). The Spooler
repo is expected next to this one (override with SPOOLER_ICON=/path/to/spooler-icon.svg).

Run from anywhere:  python3 scripts/render_images.py [name ...]
Names filter the outputs by substring (e.g. `hero`, `install-03`). Re-running overwrites the PNGs with
identical content for identical input, so it is safe to repeat.
"""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from calendar import timegm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SPOOLER_ICON = Path(os.environ.get("SPOOLER_ICON", ROOT.parent / "spooler" / "assets" / "spooler-icon.svg"))
SVG_NS = "{http://www.w3.org/2000/svg}"
MAX_PNG = 2 * 1024 * 1024   # Orca Cloud limit

THEMES = {
    "dark": {"--orca-bg": "#1e2228", "--orca-fg": "#eef0f3", "--orca-border": "#3a3f47", "--orca-muted": "#9aa1ab"},
    "light": {"--orca-bg": "#ffffff", "--orca-fg": "#1f2328", "--orca-border": "#d0d7de", "--orca-muted": "#59636e"},
}

# Each shot: template svg, page (app|setup), nav section, zoom (>1 = bigger UI), optional selector to
# scroll to, and the printer scenario. The viewport is the frame size divided by zoom, so no cropping is
# needed and the page is rendered at 2x the frame size.
O, R, I = "orca-cloud", "readme", "install"
SHOTS = [
    dict(svg=f"{R}/u1control-hero-dark", page="app", section="dash", zoom=0.84),
    dict(svg=f"{R}/u1control-hero-light", page="app", section="dash", zoom=0.84),
    dict(svg=f"{O}/frame-print-setup", page="setup", zoom=0.95),
    dict(svg=f"{O}/frame-live-control", page="app", section="dash", zoom=0.9),
    dict(svg=f"{O}/frame-toolheads-rfid", page="app", section="dash", zoom=0.88, scroll="#headCards"),
    dict(svg=f"{O}/frame-spoolman", page="app", section="dash", zoom=0.8, spools=True, scroll="#headCards"),
    dict(svg=f"{O}/frame-files-firmware", page="app", section="files", zoom=0.92),
    dict(svg=f"{I}/u1control-install-01", page="app", section="settings", zoom=0.8, scroll="#cHost"),
    dict(svg=f"{I}/u1control-install-02", page="app", section="dash", zoom=0.8),
    dict(svg=f"{I}/u1control-install-03", page="app", section="settings", zoom=0.8, scroll="#autoBox"),
    dict(svg=f"{I}/u1control-install-04", page="setup", zoom=0.8, scroll="#rows"),
]


# ------------------------------------------------------------------ plugin + fake data

def load_plugin():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
    sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "src" / "u1control")]
    import fakes
    fakes.install_orca()
    return fakes, fakes.load_wheel(ROOT / "dist" / "u1control_any.whl")


def ts(y, mo, d, h, mi):
    return timegm((y, mo, d, h, mi, 0))


FILES = [
    ("desk-organizer_4color.gcode", 18.4e6, ts(2026, 11, 9, 21, 14), 18720),
    ("phone-stand_PETG.gcode", 4.2e6, ts(2026, 11, 8, 17, 41), 6480),
    ("gridfinity-bin-2x3.gcode", 2.7e6, ts(2026, 11, 6, 9, 5), 3360),
    ("benchy_PLA.gcode", 3.1e6, ts(2026, 11, 2, 19, 30), 3900),
    ("cable-clip-x12.gcode", 1.1e6, ts(2026, 10, 28, 8, 12), 1440),
]
EXT_SETTINGS = [
    ("web-frontend", "Web frontend", "fluidd", ["fluidd", "mainsail"]),
    ("camera-internal", "Internal camera", "paxx12", ["paxx12", "snapmaker", "none"]),
    ("rfid", "RFID reader", "openrfid", ["snapmaker", "openrfid", "openrfid-generic", "external"]),
    ("spoolman", "Spoolman", "enabled", ["disabled", "enabled"]),
    ("ssh", "SSH access", "false", ["false", "true"]),
]


def printer_status(fakes, u1, tags=False):
    """A mid-print U1 status as Moonraker reports it (FakePrinter's, filled out), and its summary."""
    fp = fakes.FakePrinter(state="printing", extended=True)
    try:
        fp.task.update({
            "filament_vendor": ["Snapmaker", "Generic", "Snapmaker", "Generic"],
            "filament_type": ["PLA", "PETG", "PLA", "PLA"],
            "filament_sub_type": ["Basic", "Basic", "Basic", "Matte"],
            "filament_color_rgba": ["E5322DFF", "F5F5F5FF", "1E5BFFFF", "1A1A1AFF"],
            "filament_color_multi": [{"nums": 1, "alpha": 255, "colors": [c], "mode": 0}
                                     for c in ("E5322D", "F5F5F5", "1E5BFF", "1A1A1A")],
            "filament_official": [True, False, True, False], "filament_exist": [True] * 4,
        })
        s = fp.status()
        s["print_stats"] = {"state": "printing", "filename": "desk-organizer_4color.gcode", "print_duration": 11620,
                            "total_duration": 11880, "info": {"current_layer": 142, "total_layer": 230}}
        s["display_status"] = {"progress": 0.62}
        s["gcode_move"] = {"speed_factor": 1.0}
        s["toolhead"] = {"extruder": "extruder1"}
        for i, (cur, tgt) in enumerate(((171, 0), (218.4, 220), (154, 0), (166, 0))):
            s[u1.EXTRUDERS[i]] = {"temperature": cur, "target": tgt}
        s["heater_bed"] = {"temperature": 60.1, "target": 60}
        s["purifier"] = {"power_detected": True, "mode": "weak"}
        s["filament_feed left"] = {"extruder0": {"channel_state": "load_finish", "filament_detected": True},
                                   "extruder1": {"channel_state": "load_finish", "filament_detected": True}}
        s["filament_feed right"] = {"extruder2": {"channel_state": "load_finish", "filament_detected": True},
                                    "extruder3": {"channel_state": "load_finish", "filament_detected": True}}
        if tags:
            s["filament_detect"] = {"info": fakes.fake_tag_info({
                0: {"VENDOR": "Snapmaker", "MAIN_TYPE": "PLA", "SUB_TYPE": "Basic", "OFFICIAL": True, "RGB_1": 0xE5322D,
                    "HOTEND_MIN_TEMP": 190, "HOTEND_MAX_TEMP": 230, "BED_TEMP": 60, "CARD_UID": [4, 82, 193, 107]},
                1: {"VENDOR": "Generic", "MAIN_TYPE": "PETG", "SUB_TYPE": "Basic", "RGB_1": 0xF5F5F5,
                    "HOTEND_MIN_TEMP": 220, "HOTEND_MAX_TEMP": 250, "BED_TEMP": 70, "CARD_UID": [4, 17, 9, 200]},
                2: {"VENDOR": "Snapmaker", "MAIN_TYPE": "PLA", "SUB_TYPE": "Basic", "OFFICIAL": True, "RGB_1": 0x1E5BFF,
                    "HOTEND_MIN_TEMP": 190, "HOTEND_MAX_TEMP": 230, "BED_TEMP": 60, "CARD_UID": [4, 90, 33, 14]}})}
        return s
    finally:
        fp.close()


def app_data(fakes, mods, scenario):
    u1, sm, st = mods["u1"], mods["spoolman"], mods["settings"]
    status = printer_status(fakes, u1, tags=True)
    view = u1.summarize(status)
    fp = fakes.FakePrinter()
    try:
        spools = [sm.spool_view(s) for s in fp.spools]
    finally:
        fp.close()
    view["bindings"] = {"0": 9, "1": 11, "3": 7} if scenario.get("spools") else {}
    cfg = {**st.CONNECTION, **st.automagic_values(), "mode": "automagic", "host": "192.168.1.50",
           "spoolman_url": "http://192.168.1.10:7912", "spooler_hint_dismissed": False,
           "rfid_auto_sync": True, "prefs": {}, "printed_before": True}
    automations = [{"key": k, "label": label, "help": hint, "automagic": value, "choices": None if kind == "bool" else list(kind)}
                   for k, label, hint, value, kind in st.AUTOMATIONS if k != "mode"]
    fw = {"kind": "extended", "version": "2.0.0-paxx12-24"}
    return {
        "hello": {"address": "192.168.1.50", "firmware": fw, "hostname": "u1", "klipper_state": "ready", "printer": "Snapmaker U1"},
        "config": {"settings": cfg, "automations": automations, "mode": "automagic", "stored": {}, "version": "0.2.0",
                   "spooler": {"installed": True, "presets": 12, "url": "https://github.com/bloodf/spooler", "dismissed": False}},
        "status": view,
        "cmds": {
            "files": {"path": "gcodes", "disk": {"free": 21.3e9},
                      "dirs": [{"name": "calibration"}, {"name": "functional"}],
                      "files": [{"name": n, "size": b, "modified": m, "time": t, "weight": None, "thumbs": []} for n, b, m, t in FILES]},
            "spools": {"spools": spools, "bindings": view["bindings"], "via": "moonraker"},
            "ext_settings": {"status": {"Version": fw["version"], "Profile": "extended"},
                             "settings": [{"id": i, "label": label, "current": cur, "options": opts} for i, label, cur, opts in EXT_SETTINGS]},
            "folders": ["gcodes", "gcodes/calibration", "gcodes/functional"],
            "thumbnail": None,
        },
    }


def setup_data(fakes, mods):
    u1 = mods["u1"]
    heads = u1.summarize(printer_status(fakes, u1))["heads"]
    filaments = [
        {"index": 0, "type": "PLA", "colour": "#E5322D", "softening": 55.0, "weight": 14.2, "name": ""},
        {"index": 1, "type": "PETG", "colour": "#F5F5F5", "softening": 70.0, "weight": 9.8, "name": ""},
        {"index": 2, "type": "ABS", "colour": "#1E5BFF", "softening": 100.0, "weight": 6.1, "name": ""},
        {"index": 3, "type": "PLA", "colour": "#1A1A1A", "softening": 55.0, "weight": 8.3, "name": ""},
    ]
    mapping = u1.auto_map(filaments, heads)
    labels = {p[0]: p[2] for p in u1.PREFERENCES}
    task_opts = u1.summarize(printer_status(fakes, u1))["options"]
    prefs = {k: v for k, v in task_opts.items()}
    return {"job": {"time": "5h 12m", "weight": "38.4", "layers": "230", "printer": "Snapmaker U1", "process": "0.20mm Standard",
                    "plate": "Textured PEI", "name": "desk-organizer_4color.gcode", "address": "192.168.1.50", "thumbnail": None},
            "filaments": filaments, "heads": heads, "map": {str(k): v for k, v in mapping.items()}, "prefs": prefs,
            "labels": labels, "purifier": "auto", "auto_purifier": u1.purifier_mode(filaments)}, u1.mapping_warnings(filaments, heads, mapping)


# ------------------------------------------------------------------ page + Chrome

STUB = """<script>
const DATA = %s;
let handler = null;
const emit = m => handler && handler(m);
window.orca = {
  onMessage: f => { handler = f; },
  submit: () => {},
  postMessage: m => setTimeout(() => {
    if (m.type === "hello") { emit({type: "reply", id: m.id, result: DATA.hello}); emit({type: "config", ...DATA.config}); emit({type: "status", data: DATA.status}); }
    else if (m.type === "cmd") emit({type: "reply", id: m.id, result: m.cmd in DATA.cmds ? DATA.cmds[m.cmd] : {}});
  }, 0)
};
</script>"""


def font_css():
    def face(family, name, weights):
        b64 = base64.b64encode((ASSETS / "fonts" / name).read_bytes()).decode()
        return '@font-face{font-family:"%s";font-weight:%s;src:url(data:font/ttf;base64,%s) format("truetype")}' % (family, weights, b64)
    return face("Outfit", "Outfit.ttf", "100 900") + face("JetBrains Mono", "JetBrainsMono.ttf", "100 800")


# Render-only touches: keep long spool names inside their toolhead card, and don't draw the empty
# thumbnail boxes (the fake file list has no G-code previews to show).
FIXUPS = ".head select{font-size:11px;padding:5px 4px}"  # denser text for the small render only


def make_page(html, theme, stub_data, section=None, scroll=None):
    root = ":root{%s}" % ";".join("%s:%s" % kv for kv in THEMES[theme].items())
    head = "<style>%s%s%s</style>%s" % (font_css(), root, FIXUPS, STUB % json.dumps(stub_data).replace("</", "<\\/"))
    steps = []
    if section:
        steps.append('document.querySelector(\'#nav button[data-s="%s"]\').click();' % section)
    if scroll:
        steps.append('setTimeout(()=>{const e=document.querySelector("%s");e.closest(".card,tr,section").scrollIntoView({block:"start"});},900);' % scroll)
    html = html.replace("<head>", "<head>" + head, 1)
    return html.replace("</body>", "<script>%s</script></body>" % "".join(steps), 1)


def chrome(url, out, w, h, scale):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--virtual-time-budget=2500", "--no-first-run",
                        "--disable-gpu", f"--user-data-dir={profile}", f"--window-size={w},{h}",
                        f"--force-device-scale-factor={scale}", f"--screenshot={out}", url],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


# ------------------------------------------------------------------ frames + compositing

def frame_of(svg_text, square=False):
    """Geometry of the screenshot frame: the largest stroked, rounded rect (or the stroked square)."""
    best = None
    for r in ET.fromstring(svg_text).iter(SVG_NS + "rect"):
        a = r.attrib
        if "stroke" not in a or float(a.get("rx", 0)) == 0:
            continue
        g = {k: float(a[k]) for k in ("x", "y", "width", "height", "rx")}
        g["sw"] = float(a.get("stroke-width", 1))
        g["attrs"] = dict(a)
        if square and g["width"] != g["height"]:
            continue
        if best is None or g["width"] * g["height"] > best["width"] * best["height"]:
            best = g
    if best is None:
        raise SystemExit("no frame found")
    return best


def composite(svg_text, g, shot_png, uid="u1c"):
    inset = g["sw"] / 2
    x, y, w, h, rx = g["x"] + inset, g["y"] + inset, g["width"] - g["sw"], g["height"] - g["sw"], max(g["rx"] - inset, 0)
    img = base64.b64encode(Path(shot_png).read_bytes()).decode()
    border = "<rect %s fill=\"none\"/>" % " ".join('%s="%s"' % (k, v) for k, v in g["attrs"].items() if k != "fill")
    layer = ('<defs><clipPath id="%s-clip"><rect x="%g" y="%g" width="%g" height="%g" rx="%g"/></clipPath></defs>'
             '<g clip-path="url(#%s-clip)"><image x="%g" y="%g" width="%g" height="%g" preserveAspectRatio="xMidYMin slice" '
             'href="data:image/png;base64,%s"/></g>%s\n') % (uid, x, y, w, h, rx, uid, x, y, w, h, img, border)
    return svg_text.replace("</svg>", layer + "</svg>")


def inline_spooler(svg_text):
    """Put Spooler's icon into the empty logo square (rect-7); the icon's own rounded background
    is set to the square's corner radius."""
    g = frame_of(svg_text, square=True)
    icon = SPOOLER_ICON.read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1)
    inner = re.sub(r"<title.*?</title>|<desc.*?</desc>", "", inner, flags=re.S).strip()
    inner = inner.replace('rx="56"', 'rx="%g"' % (g["rx"] * 256 / g["width"]), 1)
    border = "<rect %s fill=\"none\"/>" % " ".join('%s="%s"' % (k, v) for k, v in g["attrs"].items() if k != "fill")
    logo = ('<!--spooler-logo--><svg x="%g" y="%g" width="%g" height="%g" viewBox="0 0 256 256">%s</svg>%s<!--/spooler-logo-->'
            % (g["x"], g["y"], g["width"], g["height"], inner, border))
    if "<!--spooler-logo-->" in svg_text:
        return re.sub(r"<!--spooler-logo-->.*?<!--/spooler-logo-->", lambda m: logo, svg_text, flags=re.S), g
    pattern = r'(<g id="rect-7">)<rect [^>]*/>(</g>)'
    if not re.search(pattern, svg_text):
        raise SystemExit("spooler logo square not found")
    return re.sub(pattern, lambda m: m.group(1) + logo + m.group(2), svg_text, count=1), g


def export_svg(svg_path, png_path, tmp):
    """Screenshot an SVG at its own size."""
    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    chrome(svg_path.as_uri(), str(png_path), int(float(root.get("width"))), int(float(root.get("height"))), 1)


def report(png, g=None):
    size = png.stat().st_size
    flag = "" if size <= MAX_PNG else "  OVER 2 MB!"
    geo = "" if g is None else "  frame x=%g y=%g %gx%g rx=%g" % (g["x"], g["y"], g["width"], g["height"], g["rx"])
    print("%-52s %7.0f kB%s%s" % (png.relative_to(ROOT), size / 1024, geo, flag))


def main(argv):
    want = argv[1:]
    pick = lambda name: not want or any(w in name for w in want)
    if not Path(CHROME).exists():
        raise SystemExit("Chrome not found at %s (set CHROME=...)" % CHROME)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for theme in ("dark", "light"):   # Spooler logo: SVG gets the inlined icon, PNG is re-exported
            name = "integration/u1control-works-with-spooler-" + theme
            if not pick(name):
                continue
            path = ASSETS / (name + ".svg")
            text, g = inline_spooler(path.read_text(encoding="utf-8"))
            if text != path.read_text(encoding="utf-8"):
                path.write_text(text, encoding="utf-8")
            export_svg(path, ASSETS / (name + ".png"), tmp)
            report(ASSETS / (name + ".png"), g)
        shots = [s for s in SHOTS if pick(s["svg"])]
        if not shots:
            return
        fakes, ns = load_plugin()
        mods = {n: sys.modules["u1control." + n] for n in ("u1", "spoolman", "settings")}
        for i, s in enumerate(shots):
            svg_path = ASSETS / (s["svg"] + ".svg")
            svg_text = svg_path.read_text(encoding="utf-8")
            g = frame_of(svg_text)
            theme = "light" if s["svg"].endswith("light") else "dark"
            if s["page"] == "setup":
                data, warnings = setup_data(fakes, mods)
                html = ns["_asset"]("setup.html").replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
                print("  %s: warnings %s" % (s["svg"], warnings))
                page = make_page(html, theme, {"cmds": {}}, scroll=s.get("scroll"))
            else:
                page = make_page(ns["_asset"]("app.html").replace("__VERSION__", ns["VERSION"]), theme, app_data(fakes, mods, s), s["section"], s.get("scroll"))
            html_path, shot = tmp / ("page%d.html" % i), tmp / ("shot%d.png" % i)
            html_path.write_text(page, encoding="utf-8")
            zoom = s["zoom"]
            chrome(html_path.as_uri(), str(shot), round(g["width"] / zoom), round(g["height"] / zoom), 2 * zoom)
            out = tmp / ("final%d.svg" % i)
            out.write_text(composite(svg_text, g, shot), encoding="utf-8")
            png = ASSETS / (s["svg"] + ".png")
            export_svg(out, png, tmp)
            report(png, g)


if __name__ == "__main__":
    main(sys.argv)
