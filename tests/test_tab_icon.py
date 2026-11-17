"""The tab icon OrcaSlicer shows is the brand tile, scaled to 64x64, and the wheel carries exactly that file."""

import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402

ICON = ROOT / "src" / "u1control" / "ui" / "icon.png"
TILE = ROOT / "assets" / "orca-cloud" / "u1control-tile.png"


def read_png(path):
    """(width, height, rows of RGBA tuples) for an 8-bit, non-interlaced RGB or RGBA PNG (stdlib only)."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat = 8, b""
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and colour in (2, 6) and not interlace, (depth, colour, interlace)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    bpp = 4 if colour == 6 else 3
    raw, stride, prev, rows = zlib.decompress(idat), width * bpp, bytearray(width * bpp), []
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + a) & 255
            elif kind == 2:
                line[i] = (line[i] + b) & 255
            elif kind == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x:x + bpp]) + ((255,) if bpp == 3 else ()) for x in range(0, stride, bpp)])
        prev = line
    return width, height, rows


class TabIcon(unittest.TestCase):
    def test_icon_is_a_small_64px_rgba_png(self):
        width, height, rows = read_png(ICON)
        self.assertEqual((width, height), (64, 64))
        self.assertLess(ICON.stat().st_size, 100_000)
        self.assertEqual(rows[0][0][3], 0, "the corners outside the rounded tile are transparent")

    def test_icon_is_the_brand_tile(self):
        """Each icon pixel matches the average of the 8x8 block of the 512x512 tile it was scaled from."""
        tw, th, tile = read_png(TILE)
        self.assertEqual((tw, th), (512, 512))
        _, _, icon = read_png(ICON)
        diffs = []
        for y in range(2, 62):
            for x in range(2, 62):
                if icon[y][x][3] < 255:
                    continue
                block = [tile[y * 8 + j][x * 8 + i] for j in range(8) for i in range(8)]
                mean = [sum(p[k] for p in block) / 64 for k in range(3)]
                diffs.append(sum(abs(mean[k] - icon[y][x][k]) for k in range(3)) / 3)
        self.assertGreater(len(diffs), 3000)
        self.assertLess(sum(diffs) / len(diffs), 6)

    def test_wheel_carries_the_icon(self):
        artifact = build.build(out_dir=Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(artifact) as z:
            text = z.read("u1control/_assets.py").decode("utf-8")
        self.assertIn("ICON_PNG = %r\n" % ICON.read_bytes(), text)
        self.assertNotIn("ICON_SVG", text)


if __name__ == "__main__":
    unittest.main()
