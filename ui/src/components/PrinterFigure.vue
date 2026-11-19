<script setup lang="ts">
import { computed } from 'vue';
import { s } from '../app/store';
import { t } from '../core/i18n';
import type { MessageKey } from '../core/messages';
import { figureSpools, type FigureSpool } from '../core/figure';
import photo from '../assets/printer/u1.webp';
import map1 from '../assets/printer/t1.webp';
import map2 from '../assets/printer/t2.webp';
import map3 from '../assets/printer/t3.webp';
import map4 from '../assets/printer/t4.webp';

/*
 * The U1, as a photo, with its four side spools in their live colours: T1 and T2 on the left (top, bottom), T3 and
 * T4 on the right. The filament on each reel is a grey light map (assets/printer/tN.webp, its alpha the filament's
 * outline) painted with the colour of the Spoolman spool linked to that toolhead, else the printer's filament colour,
 * and mixed with hard-light the way OuiSpool tints its "fio" layer: mid-grey gives the exact colour, shadows and the
 * wound strands stay. The photo itself has the filament in grey, so an empty holder shows a faded grey reel.
 * Its label says what each toolhead holds; the grams are in the toolhead cards. Shown in the status block's 72 px box.
 */
const props = defineProps<{ /** Active toolhead 1..4 while printing. */ active?: number | null; stale?: boolean }>();

// Where each light map sits on the photo, in % of the photo (from the asset build, see ui/scripts/printer-photo.py).
const REELS = [
  { map: map1, left: 5.3, top: 37.963, width: 8.1, height: 24.167 },
  { map: map2, left: 1.7, top: 61.574, width: 10.8, height: 26.667 },
  { map: map3, left: 87.9, top: 39.537, width: 5.0, height: 23.241 },
  { map: map4, left: 88.3, top: 62.037, width: 10.7, height: 26.944 },
];
const pct = (v: number) => `${v}%`;

const state = computed(() => s.status?.state ?? '');
const spools = computed(() => figureSpools(s.status?.heads, s.bindings, s.spools));
// Last known values (stale) light nothing and say nothing is in use.
const working = computed(() => !props.stale && !!props.active && (state.value === 'printing' || state.value === 'paused'));

/** The paint under a reel's light map: one colour, or the colours of a multi-colour spool side by side. */
function paint(sp: FigureSpool): string {
  if (sp.empty) return '#8e9398';
  const cs = sp.colours;
  if (!cs) return sp.colour || '#9a9a9a';
  return 'linear-gradient(90deg, ' + cs.map((c, i) => `${c} ${(i * 100) / cs.length}% ${((i + 1) * 100) / cs.length}%`).join(', ') + ')';
}
const reels = computed(() => spools.value.map((sp, i) => ({ sp, ...REELS[i], paint: paint(sp) })));
const halo = computed(() => (working.value && props.active ? REELS[props.active - 1] : null));

const label = computed(() => t('figure.label', { heads: spools.value.map(sp => {
  const colour = sp.name ? t(`figure.colour.${sp.name}` as MessageKey) : '';
  const text = sp.empty ? t('figure.empty', { n: sp.n }) : colour || sp.material
    ? t('figure.loaded', { n: sp.n, colour, material: sp.material }).replace(/\s+/g, ' ').trim() : t('figure.unknown', { n: sp.n });
  return working.value && sp.n === props.active ? t('figure.activeHead', { head: text }) : text;
}).join(', ') }));
</script>

<template>
  <div class="pf" role="img" :aria-label="label" :data-stale="stale || undefined" :data-state="state || undefined" data-test="printer-figure">
    <span v-if="halo" class="pf-halo" :style="{ left: pct(halo.left - halo.width * .9), top: pct(halo.top - halo.height * .25), width: pct(halo.width * 2.8), height: pct(halo.height * 1.5) }" />
    <img class="pf-photo" :src="photo" alt="" width="520" height="562" draggable="false" />
    <span v-for="r in reels" :key="r.sp.n" class="pf-reel" :data-head="r.sp.n" :data-empty="r.sp.empty || undefined" :data-colour="r.sp.empty ? undefined : r.sp.colour || undefined"
          :data-active="working && active === r.sp.n || undefined"
          :style="{ left: pct(r.left), top: pct(r.top), width: pct(r.width), height: pct(r.height), '--pf-paint': r.paint, '--pf-map': `url(${r.map})` }">
      <img :src="r.map" alt="" draggable="false" />
    </span>
  </div>
</template>

<style>
/* The photo scales with its box; each reel's paint is masked by its light map and the map is mixed over it. */
.pf { position: relative; isolation: isolate; width: 100%; aspect-ratio: 520 / 562; user-select: none; }
.pf-photo { position: relative; display: block; width: 100%; height: 100%; }
.pf-reel { position: absolute; background: var(--pf-paint); -webkit-mask: var(--pf-map) center / 100% 100% no-repeat; mask: var(--pf-map) center / 100% 100% no-repeat; }
.pf-reel img { display: block; width: 100%; height: 100%; mix-blend-mode: hard-light; }
/* An empty holder: the bare grey reel, faded. */
.pf-reel[data-empty] { opacity: .5; }
/* The active toolhead's spool: marked in OrcaSlicer's teal, as every selected thing is. */
.pf-halo { position: absolute; z-index: -1; border-radius: 30%; background: var(--oui-primary-soft); box-shadow: 0 0 0 1px var(--oui-primary-mark); }
.pf[data-stale] { filter: grayscale(1); opacity: .7; }
</style>
