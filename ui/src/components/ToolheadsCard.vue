<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { download, toolhead, upload } from '@orca-plugins/ui-foundation/src/icons';
import HeadCard from './HeadCard.vue';
import { s, run, tracker, guidedWhy } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import { loadable, unloadable } from '../core/spool-level';

// One visible spool source per screen (X03): when Spooler's stock uses the same Spoolman, say so.
const source = computed(() => {
  if (s.spoolsRetrying) return t('sm.retrying');
  if (s.spoolsError) return t('heads.source.error', { error: s.spoolsError });
  const n = s.spools.length;
  if (s.spoolsStale && n) return t('heads.source.cached', { n });
  if (!s.spoolsLoaded) return '';
  if (s.stock?.spooler.state === 'active' && s.stock.same_spoolman === true) return t('heads.source.same', { n });
  return s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n }) : t('heads.source.direct', { n });
});

// Load or unload several heads in one go, as the printer's screen does (the plugin sends its AUTO_FEEDING_BATCH
// sequence): tick the heads, one confirmation, the heads go one after another, the next one preheating.
type Mode = 'load' | 'unload';
const mode = ref<Mode | null>(null);
const chosen = ref<number[]>([]);
const heads = computed(() => (s.status?.heads ?? []).map((h, i) => {
  const feed = s.status?.feed?.[i];
  return { i, n: i + 1, colour: h?.colour || '', load: loadable(h, feed), unload: unloadable(h, feed?.state) };
}));
const count = (m: Mode) => heads.value.filter(h => h[m]).length;
const can = (h: { load: boolean; unload: boolean }) => !!mode.value && h[mode.value];
const list = computed(() => chosen.value.map(i => `T${i + 1}`).join(', '));
const running = computed(() => tracker.isBusy('feed:many'));
const K = {
  load: { start: 'heads.many.loadStart', pick: 'heads.many.loadPick', go: 'heads.many.loadGo', no: 'heads.many.notAtInlet',
    act: 'act.loadMany', ok: 'ok.loadMany', text: 'confirm.loadMany.text', yes: 'confirm.loadMany.yes', cmd: 'load_many' },
  unload: { start: 'heads.many.start', pick: 'heads.many.pick', go: 'heads.many.go', no: 'heads.many.empty',
    act: 'act.unloadMany', ok: 'ok.unloadMany', text: 'confirm.unloadMany.text', yes: 'confirm.unloadMany.yes', cmd: 'unload_many' },
} as const;

function open(m: Mode) {
  chosen.value = heads.value.filter(h => h[m]).map(h => h.i);
  mode.value = m;
}
function flip(i: number) {
  chosen.value = chosen.value.includes(i) ? chosen.value.filter(x => x !== i) : [...chosen.value, i].sort();
}
async function go() {
  const m = mode.value, names = list.value;
  if (!m || !chosen.value.length) return;
  const k = K[m];
  if (!await ask({ title: t(k.act, { list: names }), text: t(k.text, { list: names }), yes: t(k.yes, { list: names }), no: t('common.goBack') })) return;
  const r = await run({ key: 'feed:many', label: t(k.act, { list: names }), cmd: k.cmd, args: { heads: chosen.value },
    okText: t(k.ok, { list: names }), timeoutMs: 180000 * chosen.value.length + 60000 });
  if (r.ok) mode.value = null;
}
</script>
<template>
  <OuiPanel class="u1-heads" :icon="toolhead" tone="magenta" aria-labelledby="heads-h">
    <template #title><span id="heads-h">{{ t('heads.title') }}</span></template>
    <template #meta><span data-test="spool-source" :title="source">{{ source }}</span></template>
    <template v-if="s.status && (count('load') > 1 || count('unload') > 1)" #actions>
      <template v-for="m in (['load', 'unload'] as const)" :key="m">
        <Button v-if="mode === m || (!mode && count(m) > 1)" size="small" severity="secondary" :label="mode === m ? t('common.cancel') : t(K[m].start)"
                :disabled="running || (!mode && !!guidedWhy)" :aria-describedby="!mode && guidedWhy ? 'heads-why' : undefined" :aria-expanded="mode === m"
                aria-controls="heads-many" :data-test="m + '-many'" @click="mode === m ? (mode = null) : open(m)">
          <template #icon><OuiIcon :icon="m === 'load' ? download : upload" :size="14" /></template></Button>
      </template>
    </template>
    <div v-if="s.status && mode" id="heads-many" class="u1-many" role="group" :aria-label="t(K[mode].pick)" data-test="many-bar">
      <span class="u1-many-label">{{ t(K[mode].pick) }}</span>
      <button v-for="h in heads" :key="h.i" type="button" class="u1-many-head" :aria-pressed="chosen.includes(h.i)" :disabled="!can(h) || running"
              :title="can(h) ? '' : t(K[mode].no, { n: h.n })" :data-many="h.i" @click="flip(h.i)">
        <span class="u1-many-dot" :style="{ background: h.colour || 'transparent' }" />T{{ h.n }}</button>
      <Button size="small" :label="t(K[mode].go, { n: chosen.length })" :disabled="!chosen.length || !!guidedWhy || running" :loading="running"
              data-test="many-go" @click="go" />
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
