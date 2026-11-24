"""The print setup's small top-down preview and job facts, read from the sliced G-code only (never the printer).
Free of the `orca` module."""

import base64
import bisect
import math
import re

CELLS = 200          # the top view's longer side, in cells: ~0.5-1.4 mm each on a U1 bed
MAX_LAYERS = 150     # layers rasterized at most: all of a short print, else the top TOP_LAYERS and the rest sampled
TOP_LAYERS = 40      # always all of them: the top surface the view shows comes from there
SKIPPED = ("prime tower", "wipe tower", "skirt", "brim", "custom")   # not the print itself: the view zooms on the parts
MOVE_RE = re.compile(r"^G[0-3](?:\s|$)")
WORD_RE = re.compile(r"([XYE])(-?\d*\.?\d+)")
TOOL_RE = re.compile(r"^T(\d+)\s*(?:;.*)?$")
LAYER_RE = re.compile(r"^\s*;\s*(CHANGE_LAYER|LAYER_CHANGE)\s*$")
TYPE_RE = re.compile(r"^;\s*(?:TYPE|FEATURE):\s*(.*)$")


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


def top_view(lines, cells=CELLS):
    """The print seen from the top as a small map, for the print setup's preview: per cell the filament (G-code tool)
    of the topmost extrusion there, how high that is (1-255, 0 = nothing printed) and which filaments are anywhere
    in that column (a bit per tool), so the page can show a filament hidden under the top surface. Run-length
    encoded: {"w", "h", "bounds": [x0, y0, x1, y1], "runs": base64 of (count, tool, height, tools) quads, row by
    row from the front (y0)}. None when the G-code has no extrusion.

    One cheap pass finds the layers, tool changes and extrusion modes; only up to MAX_LAYERS layers are parsed (a
    12-hour print has millions of moves): the top TOP_LAYERS and an even sample of those below. The page draws it."""
    starts, tool_at, rel_at, typed = [], [], [], False
    for i, line in enumerate(lines):
        c = line[:1]
        if c == "T":
            m = TOOL_RE.match(line)
            if m:
                tool_at.append((i, int(m.group(1))))
        elif c == "M":
            if line.startswith(("M82", "M83")):
                rel_at.append((i, line.startswith("M83")))
        elif c != "G":
            if LAYER_RE.match(line):
                starts.append(i)
            elif not typed:
                typed = bool(TYPE_RE.match(line))
    if not starts:
        return None
    count = len(starts)
    if count <= MAX_LAYERS:
        chosen = list(range(count))
    else:
        below = count - TOP_LAYERS
        step = below / (MAX_LAYERS - TOP_LAYERS)
        chosen = sorted({int(k * step) for k in range(MAX_LAYERS - TOP_LAYERS)}) + list(range(below, count))
    layers = []   # (layer index, [(tool, width, x0, y0, x1, y1)])
    for k in chosen:
        a, b = starts[k], starts[k + 1] if k + 1 < count else len(lines)
        segs = _segments(lines, a, b, tool_at, rel_at, typed)
        if segs:
            layers.append((k, segs))
    if not layers:
        return None
    xs = [v for _, segs in layers for s in segs for v in (s[2], s[4])]
    ys = [v for _, segs in layers for s in segs for v in (s[3], s[5])]
    x0, y0, x1, y1 = min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1
    cell = max(x1 - x0, y1 - y0) / cells
    w, h = max(1, math.ceil((x1 - x0) / cell)), max(1, math.ceil((y1 - y0) / cell))
    tool_of, height, tools = bytearray([255]) * (w * h), bytearray(w * h), bytearray(w * h)
    top = max(k for k, _ in layers)
    for k, segs in layers:   # bottom up: a higher layer paints over a lower one
        level = 1 + round(254 * k / top) if top else 255
        for t, width, ax, ay, bx, by in segs:
            _paint(tool_of, height, tools, w, h, (ax - x0) / cell, (ay - y0) / cell, (bx - x0) / cell, (by - y0) / cell,
                   max(0.5, width / 2 / cell), t, level)
    return {"w": w, "h": h, "bounds": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            "runs": _encode(tool_of, height, tools)}


def _paint(tool_of, height, tools, w, h, ax, ay, bx, by, radius, tool, level):
    """A line `radius` cells thick from (ax, ay) to (bx, by): the cells it covers get tool at level."""
    bit = 1 << min(tool, 7)
    steps = max(1, int(math.hypot(bx - ax, by - ay) * 2))
    reach = int(math.ceil(radius))
    near = radius * radius + 0.25
    for n in range(steps + 1):
        px, py = ax + (bx - ax) * n / steps, ay + (by - ay) * n / steps
        cx, cy = int(px), int(py)
        for yy in range(max(0, cy - reach), min(h, cy + reach + 1)):
            row = yy * w
            for xx in range(max(0, cx - reach), min(w, cx + reach + 1)):
                if reach and (xx + 0.5 - px) ** 2 + (yy + 0.5 - py) ** 2 > near:
                    continue
                i = row + xx
                tools[i] |= bit
                if level >= height[i]:
                    height[i], tool_of[i] = level, tool


def _encode(tool_of, height, tools):
    out, n = bytearray(), len(tool_of)
    i = 0
    while i < n:
        j = i + 1
        while j < n and j - i < 255 and tool_of[j] == tool_of[i] and height[j] == height[i] and tools[j] == tools[i]:
            j += 1
        out += bytes((j - i, tool_of[i], height[i], tools[i]))
        i = j
    return base64.b64encode(bytes(out)).decode("ascii")


def _segments(lines, a, b, tool_at, rel_at, typed):
    """[(tool, width, x0, y0, x1, y1)]: the extruding XY moves of the layer from line a to b, all features but
    SKIPPED ones (the prime tower, skirt...), with the line width the G-code gives (;WIDTH:, else 0.45 mm)."""
    tool, relative = _last(tool_at, a, 0), _last(rel_at, a, False)
    x, y, e = _position_before(lines, a)
    width, drawn, out = 0.45, True, []
    for line in lines[a + 1:b]:
        c = line[:1]
        if c == "T":
            m = TOOL_RE.match(line)
            if m:
                tool = int(m.group(1))
            continue
        if c == ";":
            m = TYPE_RE.match(line)
            if m:
                drawn = not m.group(1).strip().lower().startswith(SKIPPED)
            elif line.startswith(";WIDTH:"):
                try:
                    width = float(line[7:]) or width
                except ValueError:
                    pass
            continue
        if line.startswith("M83"):
            relative = True
            continue
        if line.startswith("M82"):
            relative = False
            continue
        if line.startswith("G92"):
            m = re.search(r"E(-?\d*\.?\d+)", line)
            if m:
                e = float(m.group(1))
            continue
        if c != "G" or not MOVE_RE.match(line):
            continue
        words = dict(WORD_RE.findall(line.split(";", 1)[0]))
        nx = float(words["X"]) if "X" in words else x
        ny = float(words["Y"]) if "Y" in words else y
        extruding = False
        if "E" in words:
            value = float(words["E"])
            extruding = value > 0 if relative else e is not None and value > e
            e = e + value if relative and e is not None else value
        if extruding and drawn and None not in (x, y, nx, ny) and (nx, ny) != (x, y):
            out.append((tool, width, x, y, nx, ny))
        x, y = nx, ny
    return out


def _last(marks, index, default):
    """The value of the last (line, value) mark before line index."""
    i = bisect.bisect_left(marks, (index,)) - 1
    return marks[i][1] if i >= 0 else default


def _position_before(lines, index, lookback=2000):
    """(x, y, e) the head is at when line index runs, from the moves just before it (None when not found)."""
    x = y = e = None
    for line in reversed(lines[max(0, index - lookback):index]):
        if e is None and line.startswith("G92"):   # absolute E counts from the last reset
            m = re.search(r"E(-?\d*\.?\d+)", line)
            e = float(m.group(1)) if m else None
        if not MOVE_RE.match(line):
            continue
        words = dict(WORD_RE.findall(line.split(";", 1)[0]))
        x = float(words["X"]) if x is None and "X" in words else x
        y = float(words["Y"]) if y is None and "Y" in words else y
        e = float(words["E"]) if e is None and "E" in words else e
        if None not in (x, y, e):
            break
    return x, y, e
