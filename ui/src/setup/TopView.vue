<script setup lang="ts">
// The print seen from the top, each filament (G-code tool T<n>) in the colour of the toolhead it is mapped to.
// The plugin rasterizes the sliced layers into a small map (src/u1control/preview.py: top_view); here each cell is
// shaded by how high its top is, edges between filaments or heights are darkened so the shapes read, and a filament
// that is printed under another one (an inlay, text in the first layers) shows through faintly with its outline.
import { onMounted, ref, watch } from 'vue';
import { decode, NONE, type TopViewData } from './top-view';

const props = defineProps<{ view: TopViewData; colours: Record<string, string>; label: string }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const SIZE = 200;

function rgb(colour: string | undefined): [number, number, number] {
  const m = /^#?([0-9a-f]{6})/i.exec(colour || '') || /^#?([0-9a-f]{3})$/i.exec(colour || '');
  if (!m) return [136, 136, 136];
  const s = m[1].length === 3 ? m[1].split('').map(c => c + c).join('') : m[1];
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

function draw() {
  const c = canvas.value;
  const ctx = c?.getContext('2d');
  if (!c || !ctx) return;
  const { w, h } = props.view;
  const { tool, height, tools } = decode(props.view);
  const colour = (t: number) => rgb(props.colours[String(t)]);
  const palette = new Map<number, [number, number, number]>();
  const of = (t: number) => { let p = palette.get(t); if (!p) palette.set(t, p = colour(t)); return p; };
  const image = new ImageData(w, h);
  const px = image.data;
  const at = (x: number, y: number) => (x < 0 || y < 0 || x >= w || y >= h ? -1 : y * w + x);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, t = tool[i];
      if (t === NONE) continue;
      const [r0, g0, b0] = of(t);
      let shade = 0.72 + 0.28 * height[i] / 255;
      for (const j of [at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1)]) {
        if (j < 0 || tool[j] === NONE || tool[j] !== t || height[i] - height[j] > 6) { shade *= 0.62; break; }
      }
      let r = r0 * shade, g = g0 * shade, b = b0 * shade;
      const hidden = tools[i] & ~(1 << Math.min(t, 7));
      if (hidden) {   // another filament under the top: show it through, stronger on its outline
        const u = 31 - Math.clz32(hidden & -hidden), bit = 1 << u;
        let edge = false;
        for (const j of [at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1)]) {
          if (j < 0 || !(tools[j] & bit)) { edge = true; break; }
        }
        const a = edge ? 0.85 : 0.45, [r1, g1, b1] = of(u);
        r = r * (1 - a) + r1 * a; g = g * (1 - a) + g1 * a; b = b * (1 - a) + b1 * a;
      }
      const o = ((h - 1 - y) * w + x) * 4;   // y grows up on the bed, down on the canvas
      px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = 255;
    }
  }
  const ratio = window.devicePixelRatio || 1;
  c.width = c.height = SIZE * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, SIZE, SIZE);
  const cells = document.createElement('canvas');
  cells.width = w; cells.height = h;
  cells.getContext('2d')?.putImageData(image, 0, 0);
  const scale = (SIZE - 12) / Math.max(w, h, 1);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(cells, (SIZE - w * scale) / 2, (SIZE - h * scale) / 2, w * scale, h * scale);
}
onMounted(draw);
watch(() => [props.colours, props.view], draw, { deep: true });
</script>

<template>
  <canvas ref="canvas" class="tv" role="img" :aria-label="label" :width="SIZE" :height="SIZE" />
</template>

<style>
.tv { width: 200px; height: 200px; border-radius: var(--oui-radius-lg); background: var(--oui-inset); box-shadow: inset 0 0 0 1px var(--oui-border); }
</style>
