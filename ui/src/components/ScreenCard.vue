<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel, OuiWidgetMaximize } from '@orca-plugins/ui-foundation/src/components';
import { hand, x } from '@orca-plugins/ui-foundation/src/icons';
import { s, lease, run, tracker } from '../app/store';
import { t } from '../core/i18n';

/** The remote screen is the Extended Firmware's: on other firmware the card stays, off, and says why. */
const off = computed(() => (s.info?.firmware.kind === 'extended' ? '' : s.info?.firmware.kind === 'stock' ? t('scr.needsExt') : t('reason.waiting')));

/** The picture's own size (the U1 sends 480 x 320): the frame takes its proportions, so nothing is cut off. */
const dim = ref({ w: 480, h: 320 });
function sized(e: Event) { const i = e.currentTarget as HTMLImageElement; if (i.naturalWidth && i.naturalHeight) dim.value = { w: i.naturalWidth, h: i.naturalHeight }; }
function toggle() { s.scrOn = !s.scrOn; if (!s.scrOn) { s.screen = ''; s.screenError = ''; } lease(); }
/** A client position as the screen's own pixel (the picture is object-fit: contain); clamped to the picture, or null outside it. */
function toScreen(img: HTMLImageElement, cx: number, cy: number, clamp: boolean): [number, number] | null {
  const r = img.getBoundingClientRect(), w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return null;
  const k = Math.min(r.width / w, r.height / h), ox = (r.width - w * k) / 2, oy = (r.height - h * k) / 2;
  const px = Math.round((cx - r.left - ox) / k), py = Math.round((cy - r.top - oy) / k);
  if (clamp) return [Math.min(Math.max(px, 0), w - 1), Math.min(Math.max(py, 0), h - 1)];
  return px >= 0 && py >= 0 && px < w && py < h ? [px, py] : null;
}
const TAP_SLOP = 6, STEP = 3, MAX_POINTS = 5000;   // CSS px: under TAP_SLOP is a tap; a point is kept every STEP
let drag: { id: number; x: number; y: number; lx: number; ly: number; far: boolean; points: [number, number][] } | null = null;
function down(e: PointerEvent) {
  if (!e.isPrimary || (e.pointerType === 'mouse' && e.button !== 0)) return;
  drag = null;   // a press the picture never saw the end of (it was swapped out) doesn't block this one
  const img = e.currentTarget as HTMLImageElement, p = toScreen(img, e.clientX, e.clientY, true);
  if (!p) return;
  img.setPointerCapture(e.pointerId);
  drag = { id: e.pointerId, x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, far: false, points: [p] };
}
function move(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  if (!drag.far && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < TAP_SLOP) return;
  drag.far = true;
  if (Math.hypot(e.clientX - drag.lx, e.clientY - drag.ly) < STEP || drag.points.length >= MAX_POINTS - 1) return;
  const p = toScreen(e.currentTarget as HTMLImageElement, e.clientX, e.clientY, true);
  if (p) { drag.points.push(p); drag.lx = e.clientX; drag.ly = e.clientY; }
}
function up(e: PointerEvent) {
  const d = drag;
  if (!d || e.pointerId !== d.id) return;
  drag = null;
  const img = e.currentTarget as HTMLImageElement;
  if (e.type === 'pointercancel') return;
  if (!d.far && Math.hypot(e.clientX - d.x, e.clientY - d.y) < TAP_SLOP) {
    const p = toScreen(img, e.clientX, e.clientY, false);
    if (p) void run({ key: 'screen', label: t('act.screen'), cmd: 'screen_touch', args: { x: p[0], y: p[1] }, allowRepeat: true });
    return;
  }
  const points = d.points, end = toScreen(img, e.clientX, e.clientY, true);
  if (end) points.push(end);
  if (points.length < 2) points.push(points[0]);
  void run({ key: 'screen', label: t('act.screen'), cmd: 'screen_swipe', args: { points }, allowRepeat: true });
}
</script>
<template>
  <OuiPanel :icon="hand" flush aria-labelledby="scr-h" :hint="t('scr.hint')" :hint-label="t('scr.about')">
    <template #title><span id="scr-h">{{ t('scr.title') }}</span></template>
    <template #actions>
      <Button severity="secondary" size="small" :label="s.scrOn && !off ? t('scr.hide') : t('scr.show')" :disabled="!!off" data-focus-key="screen" data-test="screen-show" @click="toggle">
        <template #icon><OuiIcon :icon="s.scrOn && !off ? x : hand" :size="14" /></template></Button>
      <OuiWidgetMaximize />
    </template>
    <OuiEmpty v-if="!s.scrOn || off" compact :icon="hand" :title="t('scr.off')" :text="off || undefined" data-test="screen-card" />
    <div v-else class="u1-view-screen" :style="{ '--u1-scr-w': dim.w, '--u1-scr-h': dim.h }" :role="s.screen ? undefined : 'status'" :aria-busy="tracker.isBusy('screen')" :data-busy="tracker.isBusy('screen') || undefined">
      <img v-if="s.screen" :src="s.screen" :alt="t('scr.alt')" @load="sized" draggable="false" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
      <OuiEmpty v-else :state="s.screenError ? 'error' : 'loading'" :title="s.screenError || t('scr.connecting')" />
    </div>
  </OuiPanel>
</template>
<style>
/* The touchscreen at its own proportions, on the neutral track every picture sits on. The picture is fitted, never
   cropped: a click is mapped back to the screen's pixels. */
.u1-view-screen { display: grid; grid-template: minmax(0, 1fr) / minmax(0, 1fr); place-items: center; overflow: hidden; aspect-ratio: var(--u1-scr-w) / var(--u1-scr-h); background: var(--oui-inset); border-radius: 0 0 var(--oui-radius-lg) var(--oui-radius-lg); }
/* On the dashboard grid the screen fits the widget both ways and keeps its proportions. */
.oui-dash-grid:not([data-narrow]) .u1-view-screen { width: min(100%, 100cqh * var(--u1-scr-w) / var(--u1-scr-h)); margin-inline: auto; border-radius: 0; }
.u1-view-screen img { width: 100%; height: 100%; min-height: 0; object-fit: contain; cursor: pointer; }
/* A tap waiting for the printer: said by the cursor, never by anything that takes room. Taps stay allowed. */
.u1-view-screen[data-busy] img { cursor: progress; }
/* A drag on the picture is the printer's scroll, not the page's: no panning, selecting or image dragging. */
.u1-view-screen img { touch-action: none; user-select: none; -webkit-user-drag: none; }
</style>
