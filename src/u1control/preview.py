"""The print setup's small top-down preview and job facts, read from the sliced G-code only (never the printer).
Free of the `orca` module."""

import bisect
import re

MAX_SEGMENTS = 1200   # ~32 KB of JSON at most. The print setup page already carries ~1.41 MB (seven languages, the
                      # dashboard grid) and has to stay under plugin.SETUP_PAGE_LIMIT with the preview, or the
                      # preview is left out; OrcaSlicer's WebView2 on Windows leaves a much bigger page blank. The
                      # preview is drawn 160 px wide: 1200 segments of joined outlines are more than it can show.
SAMPLED_LAYERS = 12   # layers drawn on top of each other, the first one included: the footprint shows
MOVE_RE = re.compile(r"^G[0-3](?:\s|$)")
WORD_RE = re.compile(r"([XYE])(-?\d*\.?\d+)")
TOOL_RE = re.compile(r"^T(\d+)\s*(?:;.*)?$")
LAYER_RE = re.compile(r"^\s*;\s*(CHANGE_LAYER|LAYER_CHANGE)\s*$")
TYPE_RE = re.compile(r"^;\s*(?:TYPE|FEATURE):\s*(.*)$")
OUTLINE = ("outer wall", "overhang wall")   # the features drawn when the G-code names them


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
    up to SAMPLED_LAYERS layers spread over the whole height from the first layer up (the start G-code before the
    first layer is left out), every k-th one so the total stays under budget segments, seen from the top. Arcs are
    drawn as chords. None when the G-code has no extrusion.

    One cheap pass finds the layers, tool changes and extrusion modes; only the sampled layers are parsed (a
    12-hour print has millions of moves). Sampling the layers by move count alone left a long print with its top
    layer only, a few lines."""
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
    step = -(-len(starts) // SAMPLED_LAYERS)
    picked = [(starts[k], starts[k + 1] if k + 1 < len(starts) else len(lines)) for k in range(0, len(starts), step)]
    runs = [run for a, b in picked for run in _runs(lines, a, b, tool_at, rel_at, typed)]
    if not runs:
        return None
    lo, hi = 1, max(len(points) for _, points in runs)   # the smallest k that keeps every k-th point under budget
    while lo < hi:
        k = (lo + hi) // 2
        if sum(-(-(len(points) - 1) // k) for _, points in runs) <= budget:
            hi = k
        else:
            lo = k + 1
    tools, count = {}, 0
    for tool, points in runs:
        kept = points[::lo] if (len(points) - 1) % lo == 0 else points[::lo] + [points[-1]]
        for (x0, y0), (x1, y1) in zip(kept, kept[1:]):
            if count >= budget:
                break
            tools.setdefault(str(tool), []).extend((x0, y0, x1, y1))
            count += 1
    xs = [v for seg in tools.values() for v in seg[0::2]]
    ys = [v for seg in tools.values() for v in seg[1::2]]
    return {"bounds": [min(xs), min(ys), max(xs), max(ys)], "tools": tools}


def _runs(lines, a, b, tool_at, rel_at, typed):
    """[(tool, [(x, y), ...])]: the unbroken extruding paths of the layer starting at line a (up to line b); only
    its outer walls when the G-code names its features (typed): the outline, not the infill hatching."""
    tool, relative = _last(tool_at, a, 0), _last(rel_at, a, False)
    drawn = not typed
    x, y, e = _position_before(lines, a)
    runs, points = [], None
    for line in lines[a + 1:b]:
        c = line[:4]
        if c.startswith("T"):
            m = TOOL_RE.match(line)
            if m:
                tool, points = int(m.group(1)), None
            continue
        if c.startswith(";"):
            m = TYPE_RE.match(line)
            if m:
                drawn, points = not typed or m.group(1).strip().lower() in OUTLINE, None
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
        nx = float(words["X"]) if "X" in words else x
        ny = float(words["Y"]) if "Y" in words else y
        extruding = False
        if "E" in words:
            value = float(words["E"])
            extruding = value > 0 if relative else e is not None and value > e
            e = e + value if relative and e is not None else value
        if extruding and drawn and None not in (x, y, nx, ny) and (nx, ny) != (x, y):
            if points is None:
                points = [(round(x, 1), round(y, 1))]
                runs.append((tool, points))
            points.append((round(nx, 1), round(ny, 1)))
        else:
            points = None
        x, y = nx, ny
    return runs


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
