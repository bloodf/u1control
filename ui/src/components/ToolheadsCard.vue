<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { toolhead, upload } from '@orca-plugins/ui-foundation/src/icons';
import HeadCard from './HeadCard.vue';
import { s, run, tracker, guidedWhy } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import { unloadable } from '../core/spool-level';

// One visible spool source per screen (X03): when Spooler's stock uses the same Spoolman, say so.
const source = computed(() => {
  if (s.spoolsRetrying) return t('sm.retrying');
  if (s.spoolsError) return t('heads.source.error', { error: s.spoolsError });
  if (!s.spoolsLoaded) return '';
  const n = s.spools.length;
  if (s.stock?.spooler.state === 'active' && s.stock.same_spoolman === true) return t('heads.source.same', { n });
  return s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n }) : t('heads.source.direct', { n });
});

// Unload several heads in one go, as the printer's screen does (the plugin sends its AUTO_FEEDING_BATCH sequence):
// tick the heads with filament in them, one confirmation, the heads go one after another.
const picking = ref(false);
const chosen = ref<number[]>([]);
const heads = computed(() => (s.status?.heads ?? []).map((h, i) => ({
  i, n: i + 1, colour: h?.colour || '', can: unloadable(h, s.status?.feed?.[i]?.state),
})));
const loadedCount = computed(() => heads.value.filter(h => h.can).length);
const list = computed(() => chosen.value.map(i => `T${i + 1}`).join(', '));
const running = computed(() => tracker.isBusy('unload:many'));

function startPicking() {
  chosen.value = heads.value.filter(h => h.can).map(h => h.i);
  picking.value = true;
}
function flip(i: number) {
  chosen.value = chosen.value.includes(i) ? chosen.value.filter(x => x !== i) : [...chosen.value, i].sort();
}
async function unloadChosen() {
  const names = list.value;
  if (!chosen.value.length || !await ask({ title: t('act.unloadMany', { list: names }), text: t('confirm.unloadMany.text', { list: names }),
    yes: t('confirm.unloadMany.yes', { list: names }), no: t('common.goBack') })) return;
  const r = await run({ key: 'unload:many', label: t('act.unloadMany', { list: names }), cmd: 'unload_many', args: { heads: chosen.value },
    okText: t('ok.unloadMany', { list: names }), timeoutMs: 180000 * chosen.value.length + 60000 });
  if (r.ok) picking.value = false;
}
</script>
<template>
  <OuiPanel class="u1-heads" :icon="toolhead" tone="magenta" aria-labelledby="heads-h">
    <template #title><span id="heads-h">{{ t('heads.title') }}</span></template>
    <template #meta><span data-test="spool-source" :title="source">{{ source }}</span></template>
    <template v-if="s.status && loadedCount > 1" #actions>
      <Button size="small" severity="secondary" :label="picking ? t('common.cancel') : t('heads.many.start')" :disabled="running || (!picking && !!guidedWhy)"
              :aria-describedby="!picking && guidedWhy ? 'heads-why' : undefined" :aria-expanded="picking" aria-controls="heads-many"
              data-test="unload-many" @click="picking ? (picking = false) : startPicking()">
        <template #icon><OuiIcon :icon="upload" :size="14" /></template></Button>
    </template>
    <!-- Why Edit, Load and Unload are off is said once for the page (#heads-why, under the page header), not in each card. -->
    <div v-if="s.status && picking" id="heads-many" class="u1-many" role="group" :aria-label="t('heads.many.pick')" data-test="unload-many-bar">
      <span class="u1-many-label">{{ t('heads.many.pick') }}</span>
      <button v-for="h in heads" :key="h.i" type="button" class="u1-many-head" :aria-pressed="chosen.includes(h.i)" :disabled="!h.can || running"
              :title="h.can ? '' : t('heads.many.empty', { n: h.n })" :data-many="h.i" @click="flip(h.i)">
        <span class="u1-many-dot" :style="{ background: h.colour || 'transparent' }" />T{{ h.n }}</button>
      <Button size="small" :label="t('heads.many.go', { n: chosen.length })" :disabled="!chosen.length || !!guidedWhy || running" :loading="running"
              data-test="unload-many-go" @click="unloadChosen" />
    </div>
    <div v-if="s.status" class="oui-cards">
      <HeadCard v-for="(h, i) in s.status.heads" :key="i" :index="i" />
    </div>
    <OuiEmpty v-else-if="s.phase === 'unreachable'" compact state="offline" :title="t('heads.noStatus')" />
    <div v-else class="oui-cards" aria-busy="true" :aria-label="t('heads.noStatus')">
      <div v-for="n in 4" :key="n" class="u1-skelcard"><span class="oui-skeleton" /><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
    </div>
  </OuiPanel>
</template>
<style>
/* Unload several: the heads as toggles, then the one button. */
.u1-many { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s2); margin-bottom: var(--oui-s3); padding: var(--oui-s2) var(--oui-s3);
  border-radius: var(--oui-radius-lg); background: var(--oui-raised); }
.u1-many-label { margin-right: var(--oui-s2); }
.u1-many-head { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; cursor: pointer; font: inherit;
  color: inherit; background: transparent; border: 1px solid var(--oui-border); }
.u1-many-head[aria-pressed="true"] { border-color: var(--oui-accent); background: color-mix(in srgb, var(--oui-accent) 18%, transparent); font-weight: 600; }
.u1-many-head:disabled { opacity: .45; cursor: not-allowed; }
.u1-many-dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid var(--oui-border); }
.u1-many > .p-button { margin-left: auto; }
/* Two cards a row in half the dashboard, four only when the widget is really wide. */
.u1-heads .oui-cards { --oui-cards-4: 1300px; }
/* The cards are as tall as their content: when the dashboard row is taller (the other half needs more), the room left is
   under the cards, never a blank band inside each card between its content and its actions. */

.u1-skelcard { display: grid; gap: var(--oui-s3); align-content: start; min-height: 180px; padding: var(--oui-s3); border-radius: var(--oui-radius-lg); background: var(--oui-raised); }
.u1-skelcard > .oui-skeleton:nth-child(1) { width: 30%; }
.u1-skelcard > .oui-skeleton:nth-child(2) { width: 80%; }
.u1-skelcard > .oui-skeleton:nth-child(3) { width: 55%; }
</style>
