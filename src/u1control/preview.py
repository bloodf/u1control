"""The print setup's small top-down preview and job facts, read from the sliced G-code only (never the printer).
Free of the `orca` module."""

import re

MAX_SEGMENTS = 4000   # ~108 KB of JSON at most: layers are sampled to stay under it. The print setup page
                      # already carries ~1.36 MB (seven languages) and has to stay under plugin.SETUP_PAGE_LIMIT with the preview, or
                      # the preview is left out; OrcaSlicer's WebView2 on Windows leaves a much bigger page blank.
                      # The preview is drawn 160 px wide: 4000 segments are still more than it can show.
MOVE_RE = re.compile(r"^G[0-3](?:\s|$)")
WORD_RE = re.compile(r"([XYE])(-?\d*\.?\d+)")
TOOL_RE = re.compile(r"^T(\d+)\s*(?:;.*)?$")
LAYER_RE = re.compile(r"^\s*;\s*(CHANGE_LAYER|LAYER_CHANGE)\s*$")


def tool_changes(lines):
    """How often the print switches filament: T<n> lines that name another tool than the one before."""
    count, current = 0, None
    for line in lines:
        m = TOOL_RE.match(line)
        if m:
            t = int(m.group(1))
            if current is not None and t != current:
                count += 1
            current = t
    return count


def paths(lines, budget=MAX_SEGMENTS):
    """{"bounds": [x0, y0, x1, y1], "tools": {"<T index>": [x0, y0, x1, y1, ...]}}: the extruding XY moves of
    every k-th layer (k keeps the total under budget segments; the start G-code before the first layer is left
    out), seen from the top. Arcs are drawn as chords. None when the G-code has no extrusion."""
    layers = sum(1 for line in lines if LAYER_RE.match(line)) or 1
    moves = sum(1 for line in lines if MOVE_RE.match(line))
    step = max(1, -(-moves // budget))   # ceil: keep about one layer in `step`
    step = min(step, layers)
    tools, x, y, e, tool, layer, relative = {}, None, None, 0.0, 0, 0, False
    count = 0
    for line in lines:
        if LAYER_RE.match(line):
            layer += 1
            continue
        c = line[:4]
        if c.startswith("T"):
            m = TOOL_RE.match(line)
            if m:
                tool = int(m.group(1))
            continue
        if c.startswith("M83"):
            relative = True
        elif c.startswith("M82"):
            relative = False
        elif c.startswith("G92"):
            m = re.search(r"E(-?\d*\.?\d+)", line)
            if m:
                e = float(m.group(1))
        if not MOVE_RE.match(line):
            continue
        words = dict(WORD_RE.findall(line.split(";", 1)[0]))
        nx, ny = float(words.get("X", x if x is not None else 0)), float(words.get("Y", y if y is not None else 0))
        extruding = False
        if "E" in words:
            de = float(words["E"]) if relative else float(words["E"]) - e
            e = e + de if relative else float(words["E"])
            extruding = de > 0
        if extruding and x is not None and (nx, ny) != (x, y) and layer and layer % step == 0 and count < budget:
            tools.setdefault(str(tool), []).extend((round(x, 1), round(y, 1), round(nx, 1), round(ny, 1)))
            count += 1
        x, y = nx, ny
    if not tools:
        return None
    xs = [v for seg in tools.values() for v in seg[0::2]]
    ys = [v for seg in tools.values() for v in seg[1::2]]
    return {"bounds": [min(xs), min(ys), max(xs), max(ys)], "tools": tools}
