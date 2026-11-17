<script setup lang="ts">
// The print seen from the top, each filament (G-code tool T<n>) in the colour of the toolhead it is mapped to.
// The plugin samples the layers and caps the moves (src/u1control/preview.py), so drawing is one cheap pass.
import { onMounted, ref, watch } from 'vue';

export interface PathData { bounds: [number, number, number, number]; tools: Record<string, number[]> }
const props = defineProps<{ paths: PathData; colours: Record<string, string>; label: string }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const SIZE = 160;

function draw() {
  const c = canvas.value;
  const ctx = c?.getContext('2d');
  if (!c || !ctx) return;
  const ratio = window.devicePixelRatio || 1;
  c.width = c.height = SIZE * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, SIZE, SIZE);
  const [x0, y0, x1, y1] = props.paths.bounds;
  const scale = (SIZE - 12) / Math.max(x1 - x0, y1 - y0, 1);
  const ox = (SIZE - (x1 - x0) * scale) / 2, oy = (SIZE - (y1 - y0) * scale) / 2;
  ctx.lineWidth = 1;
  ctx.lineCap = 'round';
  for (const [tool, seg] of Object.entries(props.paths.tools)) {
    ctx.strokeStyle = props.colours[tool] || '#888';
    ctx.beginPath();
    for (let i = 0; i + 3 < seg.length; i += 4) {   // y grows up on the bed, down on the canvas
      ctx.moveTo(ox + (seg[i] - x0) * scale, SIZE - oy - (seg[i + 1] - y0) * scale);
      ctx.lineTo(ox + (seg[i + 2] - x0) * scale, SIZE - oy - (seg[i + 3] - y0) * scale);
    }
    ctx.stroke();
  }
}
onMounted(draw);
watch(() => props.colours, draw, { deep: true });
</script>

<template>
  <canvas ref="canvas" class="pp" role="img" :aria-label="label" :width="SIZE" :height="SIZE" />
</template>

<style>
.pp { width: 160px; height: 160px; border-radius: var(--oui-radius-lg); background: var(--oui-inset); box-shadow: inset 0 0 0 1px var(--oui-border); }
</style>
