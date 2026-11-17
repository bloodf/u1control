# Builds the Dashboard's printer photo (ui/src/assets/printer): u1.webp, the printer cut out with the filament on its
# four side spools in grey, and t1..t4.webp, one grey light map per spool whose alpha is the filament's outline.
# PrinterFigure.vue paints each map in the spool's colour (hard-light), so nothing here holds a colour.
#   uvx --from "rembg[cpu,cli]" rembg i -m isnet-general-use photo.png cut.png
#   uv run --with pillow --with numpy python ui/scripts/printer-photo.py photo.png cut.png ui/src/assets/printer
# It prints where each map sits on the photo (%), which goes into REELS in PrinterFigure.vue.
# The spool boxes and colour rules fit the Snapmaker U1 product photo (1920x1222) credited in NOTICE.md.
import json, sys
import numpy as np
from PIL import Image, ImageFilter

SRC, CUT, OUT = sys.argv[1:4]
OUT_W = 520
src = np.asarray(Image.open(SRC).convert('RGB')).astype(int)
cut = np.asarray(Image.open(CUT).convert('RGBA')).astype(float)
r, g, b = src[..., 0], src[..., 1], src[..., 2]
L = 0.299 * r + 0.587 * g + 0.114 * b


def box(x0, y0, x1, y1):
    m = np.zeros(L.shape, bool)
    m[y0:y1, x0:x1] = True
    return m


def close(m, bx, n=7):
    im = Image.fromarray((m * 255).astype('uint8'))
    im = im.filter(ImageFilter.MaxFilter(n)).filter(ImageFilter.MinFilter(n))
    im = im.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    return (np.asarray(im) > 127) & bx


# T1 left top (blue), T2 left bottom (orange), T3 right top (black), T4 right bottom (green).
B = [box(508, 495, 590, 762), box(465, 742, 582, 1042), box(1338, 500, 1392, 760), box(1342, 752, 1450, 1046)]
raw = [B[0] & (b > r + 18) & (b > g + 8) & ~((L > 150) & (b - r < 60)),
       B[1] & (r > g + 30) & (r > b + 50),
       B[2] & (cut[..., 3] > 200) & (L < 125) & ~((b > r + 12) & (L > 90)),
       B[3] & (g > r + 30) & (g > b + 30)]
masks = [close(m, B[i]) for i, m in enumerate(raw)]

ys, xs = np.where(cut[..., 3] > 40)
x0, y0, x1, y1 = xs.min() - 6, ys.min() - 6, xs.max() + 7, ys.max() + 7
W, H = x1 - x0, y1 - y0
s = OUT_W / W
CL = 0.299 * cut[..., 0] + 0.587 * cut[..., 1] + 0.114 * cut[..., 2]
union = np.logical_or.reduce(masks)
near = np.asarray(Image.fromarray((union * 255).astype('uint8')).filter(ImageFilter.MaxFilter(7))) > 0
base = cut.copy()
for c in range(3):
    base[..., c] = np.where(near, CL, cut[..., c])
Image.fromarray(base.clip(0, 255).astype('uint8')).crop((x0, y0, x1, y1)).resize((OUT_W, round(H * s)), Image.LANCZOS) \
    .save(f'{OUT}/u1.webp', quality=86, method=6)

pct = lambda v, t: round(v / t * 100, 3)
boxes = []
for i, m in enumerate(masks):
    my, mx = np.where(m)
    bx0, by0, bx1, by1 = mx.min() - 2, my.min() - 2, mx.max() + 3, my.max() + 3
    vals = L[m]
    # Mid-grey is the spool's exact colour under hard-light; keep the strands' relief at about the same contrast.
    grey = (128 + (L - np.median(vals)) * min(3.0, 30 / max(vals.std(), 1))).clip(0, 255)
    soft = np.asarray(Image.fromarray((m * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(0.8))).astype(float)
    tile = Image.fromarray(np.dstack([grey, grey, grey, soft]).astype('uint8')).crop((bx0, by0, bx1, by1))
    tile.resize((round((bx1 - bx0) * s), round((by1 - by0) * s)), Image.LANCZOS).save(f'{OUT}/t{i + 1}.webp', quality=88, method=6)
    boxes.append({'left': pct(bx0 - x0, W), 'top': pct(by0 - y0, H), 'width': pct(bx1 - bx0, W), 'height': pct(by1 - by0, H)})
print(json.dumps(boxes))
