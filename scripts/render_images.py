"""Finish the U1 Control artwork: put real renders of the plugin's pages into the marketing images and export them.

What it does
  * Builds dist/u1control_any.whl, loads it against the fake `orca` module (tests/fakes.py) and takes the
    real Vue page in app and setup modes.
  * Injects a stub `window.orca` that answers the page's messages with realistic fake printer data
    (built from tests/fakes.FakePrinter + u1.summarize, so the shapes are exactly what the plugin sends),
    then screenshots each page with headless Chrome at 2x.
  * Marketing artwork (assets/marketing/source/*.png, the native originals): scales each image to its listing
    size, finds the empty screenshot square from the pixels, renders the matching screen at exactly that size
    and pastes it inside the square's frame with the same rounded corners. Nothing else in the image changes.
  * README screenshots: the dashboard and the print setup window, light and dark, in English.
  * Writes assets/marketing/asset-manifest.json: every export with its source, operation, size, bytes and date.
  * Inlines Spooler's full-colour icon (../spooler/assets/spooler-icon.svg) into the Spooler integration
    SVGs and re-exports their PNGs. The other SVG diagrams are never changed.

Needs: Python 3 with Pillow (`pip install pillow`; only this script uses it), Node 24+ and Google Chrome (override
with CHROME=/path/to/chrome). The Spooler repo is expected next to this one for the integration images only
(override with SPOOLER_ICON=/path/to/spooler-icon.svg).

Run from anywhere:  python3 scripts/render_images.py [name ...]
Names filter the outputs by substring (e.g. `hero`, `feature-03`, `screenshot`, `integration`). Without names
everything except the integration images is redone and the manifest is rewritten. Set RENDER_OUT=/path/to/output
to keep the existing artwork unchanged.
"""

import base64
import hashlib
import io
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from calendar import timegm
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "marketing" / "source"
OUT = Path(os.environ.get("RENDER_OUT", ASSETS))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SPOOLER_ICON = Path(os.environ.get("SPOOLER_ICON", ROOT.parent / "spooler" / "assets" / "spooler-icon.svg"))
SVG_NS = "{http://www.w3.org/2000/svg}"
MAX_PNG = 2 * 1024 * 1024   # Orca Cloud limit

THEMES = {
    # OrcaSlicer's own colours, which the host injects into plugin pages
    "dark": {"--orca-bg": "#2b2c30", "--orca-fg": "#eceef1", "--orca-border": "#43454c", "--orca-muted": "#a0a3aa",
             "--orca-accent": "#009688", "--orca-accent-fg": "#ffffff"},
    "light": {"--orca-bg": "#ffffff", "--orca-fg": "#262e30", "--orca-border": "#d0d7de", "--orca-muted": "#59636e",
              "--orca-accent": "#009688", "--orca-accent-fg": "#ffffff"},
}

# What each screen shows: the page (app|setup), its section, the CSS width it is laid out at inside a wide
# square (a narrower square gets NARROW, the phone layout), the printer scenario and a script run once the
# page is up.
NARROW = 430
SCROLL_TO = ('document.querySelector("main").style.paddingBottom="600px";'   # the panel, just under the sticky app bar
             'const p=document.querySelector("%s").closest("section");'
             'p.style.scrollMarginTop=document.querySelector(".oui-appbar").offsetHeight+10+"px";p.scrollIntoView({block:"start"});'
             'scrollTo(0,Math.round(scrollY));')
CAMERA_ON = ('document.querySelector(\'[data-test="camera"]\').click();'      # start the camera, answer with the mock picture
             'setTimeout(()=>emit({type:"frame",image:DATA.frame}),50);setTimeout(()=>{%s},150);')
# Then down just far enough that the whole camera picture is in view: in the default layout it sits under the fold.
CAMERA_IN_VIEW = ('const r=document.querySelector("img.oui-camera-picture")?.getBoundingClientRect();'
                  'if(r&&r.bottom>innerHeight-12)scrollTo(0,Math.round(scrollY+r.bottom-innerHeight+12));')
# Nothing after the toolheads: the panel that follows would show its title and little else.
HEADS_LAST = ('const hp=document.querySelector("#heads-h").closest(".oui-panel");document.querySelectorAll("main .oui-panel").forEach(p=>{'
              'if(hp.compareDocumentPosition(p)&Node.DOCUMENT_POSITION_FOLLOWING&&!hp.contains(p))p.remove();});')
# The toolhead cards without their heater row, feeder line and buttons: the spools are what they show here.
COMPACT_HEADS = 'document.querySelectorAll(".hc .oui-slot-extra>[data-heater-row],.hc .oui-slot-extra>p.oui-meta,.hc .oui-slot-actions").forEach(e=>e.remove());'
SCREENS = {
    # the Dashboard in its default layout, as it comes (two columns from GRID_WIDTH, else one in reading order)
    "dash": dict(page="app", section="dash", width=640, spools=True),
    "camera": dict(page="app", section="dash", width=640, spools=True, js=CAMERA_ON % CAMERA_IN_VIEW),
    "heads": dict(page="app", section="dash", width=640, spools=True, js=HEADS_LAST + SCROLL_TO % "#heads-h" + COMPACT_HEADS),   # all four fit the square
    "files": dict(page="app", section="files", width=880),
    "setup": dict(page="setup", width=900),                  # the window's own width: four filaments in one row, options and buttons under them
    "wide": dict(page="app", section="dash", spools=True),
}
# Listing sizes by the kind of image (the name of the source file says which).
SIZES = {"tile": (512, 512), "square": (900, 900), "social": (1280, 640)}
LANDSCAPE = (1600, 900)
# Layout width in CSS px of the app page inside a marketing image: wide enough for the whole header line
# ("Snapmaker U1 · 192.168.1.50 · Extended firmware 2.0.0"), narrow enough to keep the two-row header.
CSS_WIDTHS = {"en": 740, "pt-BR": 760}      # wide squares: room for the whole firmware line in the header
GRID_WIDTH = 1040                           # the landscape images: wide enough for the Dashboard's two columns (from 1000)
CSS_WIDTH_SOCIAL = 760                      # the small square: wide layout too, so the header line fits and no button wraps
FILES_WIDTH_PT = 960                        # the Files tab in Portuguese: its longer tab names need a wider one-row app bar
USES = {"tile": "store tile and plugin table icon", "square": "Orca Cloud square image", "social": "GitHub social preview",
        "hero": "README hero", "main": "Orca Cloud main image", "feature": "Orca Cloud gallery and README feature grid"}
# README screenshots: name, screen, CSS viewport. Exported at 1.25x.
# The viewports hold the whole page: every toolhead and the controls, and the setup window (900 px wide in OrcaSlicer) down to its buttons.
PLAIN = [("dashboard", "wide", (1280, 1240)), ("print-setup", "setup", (900, 640))]
PLAIN_SCALE = 1.25
# The mock camera picture: the print inside the printer, cut from the cover photograph (x, y, width, height).
CAMERA_CROP = ("u1control-workshop-cover-en.png", (372, 668, 208, 117))


# ------------------------------------------------------------------ plugin + fake data

def load_plugin(output):
    sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "src" / "u1control")]
    import fakes
    fakes.install_orca()
    runpy.run_path(str(ROOT / "scripts" / "build.py"))["build"](output)
    return fakes, fakes.load_wheel(output / "u1control_any.whl")


def ts(y, mo, d, h, mi):
    return timegm((y, mo, d, h, mi, 0))


FILES = [
    ("desk-organizer.gcode", 18.4e6, ts(2026, 11, 9, 21, 14), 18720, 38.4),
    ("phone-stand.gcode", 4.2e6, ts(2026, 11, 8, 17, 41), 6480, 61.0),
    ("gridfinity-bin.gcode", 2.7e6, ts(2026, 11, 6, 9, 5), 3360, 27.5),
    ("benchy.gcode", 3.1e6, ts(2026, 11, 2, 19, 30), 3900, 12.9),
    ("cable-clips.gcode", 1.1e6, ts(2026, 10, 28, 8, 12), 1440, 8.2),
]
TIMELAPSES = [
    ("desk-organizer_20261109211402", "desk-organizer", 48.6e6, ts(2026, 11, 10, 2, 26)),
    ("phone-stand_20261108174110", "phone-stand", 21.9e6, ts(2026, 11, 8, 19, 29)),
    ("benchy_20261102193001", "benchy", 12.3e6, ts(2026, 11, 2, 20, 35)),
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
        s["print_stats"] = {"state": "printing", "filename": "desk-organizer.gcode", "print_duration": 11620,
                            "total_duration": 11880, "info": {"current_layer": 142, "total_layer": 230}}
        s["display_status"] = {"progress": 0.62}
        s["gcode_move"] = {"speed_factor": 1.0}
        s["toolhead"] = {"extruder": "extruder1"}
        for i, (cur, tgt) in enumerate(((171, 0), (218.4, 220), (154, 0), (166, 0))):
            s[u1.EXTRUDERS[i]] = {"temperature": cur, "target": tgt}
        s["heater_bed"] = {"temperature": 60.1, "target": 60}
        s["purifier"] = {"power_detected": True, "mode": "weak", "exhaust_fan": {"speed": 0.4}, "inner_fan": {"speed": 0.0}}
        s["fan"], s["fan_generic cavity_fan"] = {"speed": 0.8}, {"speed": 0.3}
        s["temperature_sensor cavity"] = {"temperature": 34.6}
        for name, obj in u1.DRIVERS:   # TMC2240 (X, Y) read their own temperature
            s[obj] = {"drv_status": {}, **({"temperature": 41.0 if name == "X" else 39.0} if "2240" in obj else {})}
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


DEMO_LEFT = {7: {"remaining_weight": 85}}   # grams left on a demo spool, where the fake printer's own amount is not the picture wanted


def app_data(fakes, mods, scenario):
    u1, sm, st = mods["u1"], mods["spoolman"], mods["settings"]
    status = printer_status(fakes, u1, tags=True)
    view = u1.summarize(status)
    fp = fakes.FakePrinter()
    try:
        # demo spools are 1 kg spools, so the images show each reel's fill and level bar
        # and a believable mix: T1 half, T2 nearly full, T4 low; T3 has no spool linked, so its amount is unknown
        spools = [sm.spool_view({"initial_weight": 1000, **s, **DEMO_LEFT.get(s["id"], {})}) for s in fp.spools]
    finally:
        fp.close()
    view["bindings"] = {"0": 9, "1": 11, "3": 7} if scenario.get("spools") else {}
    view["estimated_time"] = 18720   # the slicer's estimate of desk-organizer.gcode (FILES), read by the plugin from its metadata
    view["left"] = u1.time_left(view)
    cfg = {**st.CONNECTION, **st.automagic_values(), "mode": "automagic", "host": "192.168.1.50",
           "spoolman_url": "http://192.168.1.10:7912", "spooler_hint_dismissed": False,
           "rfid_auto_sync": True, "prefs": {}, "printed_before": True}
    automations = [{"key": k, "label": label, "help": hint, "automagic": value, "choices": None if kind == "bool" else list(kind)}
                   for k, label, hint, value, kind in st.AUTOMATIONS if k != "mode"]
    fw = {"kind": "extended", "version": "2.0.0"}
    return {
        "frame": scenario.get("frame"),
        "hello": {"address": "192.168.1.50", "firmware": fw, "hostname": "u1", "klipper_state": "ready", "printer": "Snapmaker U1", "generation": 1},
        "config": {"settings": cfg, "automations": automations, "mode": "automagic", "stored": {}, "version": mods["version"],
                   "spooler": {"installed": True, "presets": 12, "url": "https://github.com/bloodf/spooler", "dismissed": False}},
        "status": view,
        "cmds": {
            "stock": {"spooler": {"state": "active", "text": "", "version": "0.20.1"},
                      "stock": {"state": "ok", "code": "ok", "text": "", "rows": spools}, "same_spoolman": True,
                      "bindings": view["bindings"], "usage": "u1control"},
            "usage": {"pending": [], "unconfirmed": [], "acknowledged": [], "acknowledged_total": 0,
                      "save_error": "", "restore_notice": ""},
            "files": {"path": "gcodes", "disk": {"free": 21.3e9},
                      "dirs": [{"name": "calibration"}, {"name": "functional"}],
                      "files": [{"name": n, "size": b, "modified": m, "time": t, "weight": g, "thumbs": []} for n, b, m, t, g in FILES]},
            "timelapses": {"supported": True, "videos": [
                {"path": "timelapse/%s.mp4" % f, "file": f + ".mp4", "name": n, "size": b, "modified": m, "cover": "timelapse/%s_cover.jpg" % f}
                for f, n, b, m in TIMELAPSES]},
            "timelapse_cover": scenario.get("frame"),
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
        {"index": 2, "type": "PLA", "colour": "#1E5BFF", "softening": 55.0, "weight": 6.1, "name": ""},
        {"index": 3, "type": "PLA", "colour": "#1A1A1A", "softening": 55.0, "weight": 8.3, "name": ""},
    ]
    mapping = u1.auto_map(filaments, heads)
    labels = {p[0]: p[2] for p in u1.PREFERENCES}
    task_opts = u1.summarize(printer_status(fakes, u1))["options"]
    prefs = {**task_opts, "bed_level": True, "flow_calibrate": True}   # U1 Control's defaults
    return {"job": {"time": "5h 12m", "weight": "38.4", "layers": "230", "printer": "Snapmaker U1", "process": "0.20mm Standard",
                    "plate": "Textured PEI", "name": "desk-organizer.gcode", "address": "192.168.1.50", "thumbnail": None},
            "filaments": filaments, "heads": heads, "map": {str(k): v for k, v in mapping.items()}, "prefs": prefs,
            "labels": labels, "purifier": "auto", "auto_purifier": u1.purifier_mode(filaments)}, u1.mapping_warnings(filaments, heads, mapping)


# ------------------------------------------------------------------ page + Chrome

STUB = """<script>
const DATA = %s;
// One demo clock for every image: 17:36 UTC, so "Finishes" reads 19:34 (7:34 PM) in all of them.
const RealDate = Date, NOW = RealDate.UTC(2026, 10, 16, 17, 36, 0);
window.Date = class extends RealDate {
  constructor(...a) { a.length ? super(...a) : super(NOW); }
  static now() { return NOW; }
};
window.addEventListener('error', e => { document.documentElement.dataset.renderError = e.message; });
window.addEventListener('unhandledrejection', e => { document.documentElement.dataset.renderError = String(e.reason); });
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


# Ends the page at a clean edge: the first row or card that would be cut by the bottom of the image (at `H`
# CSS px) is hidden with everything below it, under a block in the page colour.
CLEAN_CUT = """(H=>{
  // the open tab's page (the other tabs are hidden); above: where the page ends if `el` goes whole
  let el = [...document.querySelectorAll("main")].find(m => m.offsetHeight) || document.body, cut = H, above = 0;
  // the boxes inside `e`: a display: contents wrapper has none of its own, its children stand in for it
  const boxes = e => [...e.children].flatMap(k => getComputedStyle(k).display === "contents" ? boxes(k) : [k]);
  for (;;) {
    const kids = boxes(el).filter(k => k.offsetHeight > 0), rect = k => k.getBoundingClientRect();
    const s = kids.find(k => rect(k).top < H && rect(k).bottom > H);
    if (!s) {   // nothing is cut here; a block with no measurable children goes whole
      const ends = kids.map(k => rect(k).bottom).filter(b => b <= H);
      cut = ends.length ? Math.max(...ends) : above; break;
    }
    const i = kids.indexOf(s), here = ((i ? rect(kids[i - 1]).bottom : rect(s).top) + rect(s).top) / 2;
    if (rect(s).height <= 90 || !s.children.length) {
      // a group left with only its label goes whole too
      cut = i && kids.slice(0, i).every(k => k.matches(".oui-label")) ? above : here; break;
    }
    above = here; el = s;
  }
  const d = document.createElement("div");
  d.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99;top:" + Math.min(cut, H) + "px;background:" + getComputedStyle(document.body).backgroundColor;
  document.body.append(d);
})(%d);"""


def make_page(html, theme, stub_data, section=None, scroll=None, js=None, cut=None):
    root = ":root{%s}" % ";".join("%s:%s" % kv for kv in THEMES[theme].items())
    head = "<style>%s%s::-webkit-scrollbar{display:none}</style>%s" % (font_css(), root, STUB % json.dumps(stub_data).replace("</", "<\\/"))
    steps = []
    if section:
        steps.append('setTimeout(()=>document.querySelector(\'[data-tab="%s"]\').click(),300);' % section)
    if scroll:
        steps.append('setTimeout(()=>{const e=document.querySelector("%s");e.closest("section").scrollIntoView({block:"start"});},900);' % scroll)
    if js:   # extra page script, run after the scroll (e.g. open the spool picker)
        steps.append("setTimeout(()=>{%s},1300);" % js)
    if cut:
        steps.append("setTimeout(()=>{%s},1600);" % (CLEAN_CUT % cut))
    steps.append("setTimeout(()=>{if(!document.querySelector('#app .p-button'))throw Error('Vue did not mount');document.documentElement.dataset.renderReady='true';},1800);")
    html = html.replace("<head>", "<head>" + head, 1)
    return html.replace("</body>", "<script>%s</script></body>" % "".join(steps), 1)


def chrome(url, out, w, h, scale, validate=False):
    # The shared test launcher supplies --use-mock-keychain --password-store=basic.
    subprocess.run(["node", str(ROOT / "scripts/render_page.mjs"), url, str(out), str(w), str(h),
                    str(scale), str(validate).lower(), str(OUT)],
                   env={**os.environ, "CHROME": CHROME, "TZ": "UTC"}, check=True, timeout=120)


# ------------------------------------------------------------------ screenshots

def camera_frame():
    """The mock camera picture as a data URI."""
    from PIL import Image
    name, (x, y, w, h) = CAMERA_CROP
    buf = io.BytesIO()
    Image.open(SOURCE / name).convert("RGB").crop((x, y, x + w, y + h)).resize((640, 360), Image.LANCZOS).save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def shoot(env, screen, theme, lang, size, css_width=None, clean=False):
    """One screen of the plugin as an image of exactly `size` pixels, laid out `css_width` CSS pixels wide."""
    from PIL import Image, ImageOps
    s = SCREENS[screen]
    zoom = size[0] / (css_width or (s["width"] if size[0] >= 560 else NARROW))
    if s["page"] == "setup":
        data, _ = setup_data(env["fakes"], env["mods"])
        page = make_page(env["ns"]["page_html"]("setup", data, language=lang), theme, {"cmds": {}})
    else:
        data = app_data(env["fakes"], env["mods"], {**s, "frame": env["frame"]})
        page = make_page(env["ns"]["page_html"]("app", language=lang), theme, data, s["section"], None, s.get("js"),
                         round(size[1] / zoom) if clean else None)
    env["n"] += 1
    html_path, shot = env["tmp"] / ("page%d.html" % env["n"]), env["tmp"] / ("shot%d.png" % env["n"])
    html_path.write_text(page, encoding="utf-8")
    # at 2x and scaled down: a whole device pixel ratio keeps the scrolled page from showing a row above the sticky bar
    chrome(html_path.as_uri(), str(shot), round(size[0] / zoom), round(size[1] / zoom), 2, validate=True)
    return ImageOps.fit(Image.open(shot).convert("RGB"), size, Image.LANCZOS, centering=(0, 0))


# ------------------------------------------------------------------ marketing artwork

def find_square(im):
    """The empty screenshot square of a marketing image, read from its pixels: the box inside the frame
    (left, top, right, bottom) and the corner radius. The square is one flat colour on the right."""
    px, (w, h) = im.load(), im.size
    sx, sy = round(w * 0.76), round(h * 0.5)
    c = px[sx, sy]

    def same(x, y):
        return max(abs(a - b) for a, b in zip(px[x, y], c)) <= 30

    def walk(x, y, dx, dy):
        while 0 < x + dx < w - 1 and 0 < y + dy < h - 1 and same(x + dx, y + dy):
            x, y = x + dx, y + dy
        return x if dx else y

    # the innermost of several probes per side, so no pixel of the frame is covered
    l0, r0, t0, b0 = walk(sx, sy, -1, 0), walk(sx, sy, 1, 0), walk(sx, sy, 0, -1), walk(sx, sy, 0, 1)
    ys = [t0 + (b0 - t0) * i // 20 for i in range(4, 17)]
    xs = [l0 + (r0 - l0) * i // 20 for i in range(4, 17)]
    left, right = max(walk(sx, y, -1, 0) for y in ys), min(walk(sx, y, 1, 0) for y in ys)
    top, bottom = max(walk(x, sy, 0, -1) for x in xs), min(walk(x, sy, 0, 1) for x in xs)
    # Corner radius from the top-left corner: a row k pixels down starts off pixels in, and on a circle
    # r = off + k + sqrt(2 * off * k). The median over a few rows.
    radii = []
    for k in range(1, 7):
        off = next(i for i in range(w) if same(left + i, top + k))
        if off:
            radii.append(off + k + (2 * off * k) ** 0.5)
    radius = round(sorted(radii)[len(radii) // 2]) if radii else 0
    bw, bh = right - left + 1, bottom - top + 1
    if not (0.3 * h < bh < 0.85 * h and 0.9 < bw / bh < 1.2 and radius < bw / 6):
        raise SystemExit("no screenshot square found (%dx%d at %d,%d, radius %d)" % (bw, bh, left, top, radius))
    return (left, top, right + 1, bottom + 1), radius


def paste_rounded(art, shot, box, radius):
    from PIL import Image, ImageDraw
    w, h = box[2] - box[0], box[3] - box[1]
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), radius * 4, fill=255)
    art.paste(shot, box[:2], mask.resize((w, h), Image.LANCZOS))


def artwork(src):
    """Where a source image goes and what it shows: (export path under assets/, size, use, screen, theme, lang)."""
    stem = src.stem.replace("-workshop", "").replace("-cover-", "-main-")
    kind = next(k for k in ("tile", "square", "social", "hero", "feature", "main") if k in stem)
    folder = {"hero": "readme", "social": "social"}.get(kind, "orca-cloud")
    screen = None if kind == "tile" else next((v for k, v in (("setup", "setup"), ("dashboard", "camera"), ("filament", "heads"),
                                                              ("files", "files")) if kind == "feature" and k in stem), "dash")
    return ("%s/%s.png" % (folder, stem), SIZES.get(kind, LANDSCAPE), USES[kind], screen,
            "light" if "light" in stem else "dark", "pt-BR" if stem.endswith("pt-BR") else "en")


def save(im, rel):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG", optimize=True)
    size = path.stat().st_size
    print("%-58s %4dx%-4d %5.0f kB%s" % (rel, im.width, im.height, size / 1024, "" if size <= MAX_PNG else "  OVER 2 MB!"))
    if size > MAX_PNG:
        raise SystemExit("%s is over Orca Cloud's 2 MB limit" % rel)
    return {"file": "assets/" + rel, "width": im.width, "height": im.height, "bytes": size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "date": time.strftime("%Y-%m-%d")}


def css_width_for(rel, screen, lang):
    if screen == "files" and lang == "pt-BR":
        return FILES_WIDTH_PT          # the one-row app bar cuts "Ajustes" and "Imprimindo" short below this
    if screen not in ("dash", "camera"):   # the setup window, toolheads and files keep their own layout widths
        return None
    if rel.startswith("social/"):
        return CSS_WIDTH_SOCIAL
    return CSS_WIDTHS[lang] if "square" in rel else GRID_WIDTH


def export_artwork(env, src):
    from PIL import Image
    rel, size, use, screen, theme, lang = artwork(src)
    native = Image.open(src).convert("RGB")
    art = native.resize(size, Image.LANCZOS)
    op = "resized %dx%d to %dx%d (Lanczos)" % (native.size + size)
    if screen:
        box, radius = find_square(art)
        paste_rounded(art, shoot(env, screen, theme, lang, (box[2] - box[0], box[3] - box[1]),
                                 css_width_for(rel, screen, lang), clean=True), box, radius)
        op += "; mock screenshot '%s' (%s, %s) pasted inside the square at x=%d y=%d, %dx%d, corner radius %d" % (
            screen, theme, lang, box[0], box[1], box[2] - box[0], box[3] - box[1], radius)
    return {**save(art, rel), "source": "assets/marketing/source/" + src.name, "operation": op, "use": use}


def export_plain(env, name, screen, viewport, theme, lang):
    size = (round(viewport[0] * PLAIN_SCALE), round(viewport[1] * PLAIN_SCALE))
    rel = "readme/u1control-screenshot-%s-%s-%s.png" % (name, theme, lang)
    return {**save(shoot(env, screen, theme, lang, size, viewport[0], clean=True), rel), "source": "the built page (src/u1control/ui/app.html) with fake data",
            "operation": "mock screenshot '%s' (%s, %s), %dx%d CSS px at %gx" % ((screen, theme, lang) + viewport + (PLAIN_SCALE,)),
            "use": "README screenshot"}


def write_manifest(entries):
    """One record per export; a partial run keeps the records of the files it did not redo."""
    path = OUT / "marketing" / "asset-manifest.json"
    old = json.loads(path.read_text(encoding="utf-8"))["exports"] if path.exists() else []
    merged = {e["file"]: e for e in old if (ROOT / e["file"]).exists()}   # a file since deleted loses its record
    merged.update((e["file"], e) for e in entries)
    sources = [{"file": "assets/marketing/source/" + p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(SOURCE.glob("*.png"))]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "about": "U1 Control marketing images. Sources are the native originals, kept unchanged; exports are made by "
                 "scripts/render_images.py. The screenshots inside are mock previews of the built page with fake data, "
                 "not captures from OrcaSlicer.",
        "sources": sources, "exports": sorted(merged.values(), key=lambda e: e["file"])}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Spooler integration diagrams

def frame_of(svg_text):
    """Geometry of the logo square: the largest stroked, rounded square."""
    best = None
    for r in ET.fromstring(svg_text).iter(SVG_NS + "rect"):
        a = r.attrib
        if "stroke" not in a or float(a.get("rx", 0)) == 0 or a["width"] != a["height"]:
            continue
        g = {k: float(a[k]) for k in ("x", "y", "width", "height", "rx")}
        g["attrs"] = dict(a)
        if best is None or g["width"] > best["width"]:
            best = g
    if best is None:
        raise SystemExit("no frame found")
    return best


def inline_spooler(svg_text):
    """Put Spooler's icon into the empty logo square (rect-7); the icon's own rounded background
    is set to the square's corner radius."""
    g = frame_of(svg_text)
    icon = SPOOLER_ICON.read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1)
    inner = re.sub(r"<title.*?</title>|<desc.*?</desc>", "", inner, flags=re.S).strip()
    inner = inner.replace('rx="56"', 'rx="%g"' % (g["rx"] * 256 / g["width"]), 1)
    border = "<rect %s fill=\"none\"/>" % " ".join('%s="%s"' % (k, v) for k, v in g["attrs"].items() if k != "fill")
    logo = ('<!--spooler-logo--><svg x="%g" y="%g" width="%g" height="%g" viewBox="0 0 256 256">%s</svg>%s<!--/spooler-logo-->'
            % (g["x"], g["y"], g["width"], g["height"], inner, border))
    if "<!--spooler-logo-->" in svg_text:
        return re.sub(r"<!--spooler-logo-->.*?<!--/spooler-logo-->", lambda m: logo, svg_text, flags=re.S)
    pattern = r'(<g id="rect-7">)<rect [^>]*/>(</g>)'
    if not re.search(pattern, svg_text):
        raise SystemExit("spooler logo square not found")
    return re.sub(pattern, lambda m: m.group(1) + logo + m.group(2), svg_text, count=1)


def export_integration(name):
    text = inline_spooler((ASSETS / (name + ".svg")).read_text(encoding="utf-8"))
    svg, png = OUT / (name + ".svg"), OUT / (name + ".png")
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text(text, encoding="utf-8")
    root = ET.fromstring(text)
    chrome(svg.as_uri(), str(png), int(float(root.get("width"))), int(float(root.get("height"))), 1)
    print("%-58s %5.0f kB" % (name + ".png", png.stat().st_size / 1024))


def main(argv):
    want = argv[1:]
    pick = lambda name: not want or any(w in name for w in want)
    if not Path(CHROME).exists():
        raise SystemExit("Chrome not found at %s (set CHROME=...)" % CHROME)
    for theme in ("dark", "light"):   # only when asked for by name: needs the Spooler repo
        name = "integration/u1control-works-with-spooler-" + theme
        if want and pick(name):
            export_integration(name)
    # English only: the Portuguese images are no longer exported (README.pt-BR.md keeps the last ones made)
    sources = [p for p in sorted(SOURCE.glob("*.png")) if not p.stem.endswith("pt-BR") and pick(artwork(p)[0])]
    plain = [(n, s, v, theme, "en") for n, s, v in PLAIN for theme in ("light", "dark")
             if pick("readme/u1control-screenshot-%s-%s-en.png" % (n, theme))]
    if not sources and not plain:
        return
    with tempfile.TemporaryDirectory() as tmp:
        fakes, ns = load_plugin(Path(tmp) / "wheel")
        env = {"fakes": fakes, "ns": ns, "mods": {**{n: sys.modules["u1control." + n] for n in ("u1", "spoolman", "settings")}, "version": ns["VERSION"]},
               "tmp": Path(tmp), "n": 0, "frame": camera_frame()}
        entries = [export_artwork(env, p) for p in sources] + [export_plain(env, *p) for p in plain]
    write_manifest(entries)


if __name__ == "__main__":
    main(sys.argv)
