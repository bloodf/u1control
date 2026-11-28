<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import { OuiControlRow, OuiEmpty, OuiHint, OuiKeyValue, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { fan as fanIcon } from '@orca-plugins/ui-foundation/src/icons';
import { s, run, tracker, guidedWhy } from '../app/store';
import type { Driver } from '../app/types';
import { t } from '../core/i18n';

// What the U1 reads besides the heaters: the chamber, the stepper drivers and every fan. The part cooling and
// auxiliary fans can be set here, only on an idle U1 like Load and Park (the plugin checks again); the top-cover fans
// are set in Controls.
// Its settings say which readings show. In a small widget it is compact: the readings only, without the fan setters
// (container query on the widget, below).
const props = withDefaults(defineProps<{ config?: { chamber?: boolean; drivers?: boolean; fans?: boolean } }>(), { config: () => ({}) });
const show = (k: 'chamber' | 'drivers' | 'fans') => props.config[k] !== false;
const st = computed(() => s.status);
const why = computed(() => (guidedWhy.value ? 'heads-why' : undefined));
const pct = (v: unknown) => (typeof v === 'number' ? `${Math.round(v * 100)} %` : null);
const deg = (v: unknown) => (typeof v === 'number' ? `${Math.round(v)} °C` : null);
const stateText = { ok: 'tf.ok', otpw: 'tf.otpw', ot: 'tf.ot' } as const;
function driverText(d: Driver): string | null {
  const parts = [deg(d.temp), d.state && (d.temp == null || d.state !== 'ok') ? t(stateText[d.state]) : null].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}
const temps = computed(() => [
  ...(show('chamber') ? [{ label: t('tf.chamber'), value: deg(st.value?.chamber) }] : []),
  ...(show('drivers') ? (st.value?.drivers ?? []).map(d => ({ label: t('tf.driver', { axis: d.name }), value: driverText(d) })) : []),
]);
const coverFans = computed(() => [
  { label: t('pref.exhaust_fan'), value: pct(st.value?.purifier?.exhaust) },
  { label: t('pref.inner_fan'), value: pct(st.value?.purifier?.inner) },
]);
const fans = [{ id: 'part', label: 'tf.part', speed: 'fan' }, { id: 'aux', label: 'tf.aux', speed: 'aux_fan' }] as const;
const draft = ref<Record<string, number | null>>({ part: null, aux: null });
async function setFan(id: string) {
  const v = draft.value[id];
  if (v == null || guidedWhy.value) return;
  const r = await run({ key: `tf:${id}`, label: t('tf.act'), cmd: 'fan', args: { fan: id, percent: v }, okText: t('tf.done') });
  if (r.ok) draft.value = { ...draft.value, [id]: null };
}
</script>

<template>
  <OuiPanel :icon="fanIcon" tone="sky" aria-labelledby="tf-h" data-test="temps-fans">
    <template #title><span id="tf-h">{{ t('tf.title') }}</span></template>
    <div v-if="st" class="oui-controls">
      <div v-if="temps.length" class="oui-controls-group">
        <p class="oui-label">{{ t('tf.temps') }} <OuiHint id="tf-help" :label="t('tf.driversAbout')" :text="t('tf.driversHelp')" /></p>
        <OuiKeyValue class="tf-temps" :items="temps" />
      </div>
      <div v-if="show('fans')" class="oui-controls-group">
        <p class="oui-label">{{ t('tf.fans') }}</p>
        <div class="tf-fans">
          <OuiControlRow v-for="f in fans" :key="f.id" :label="t(f.label)" :for="`tf-${f.id}`" :value="pct(st[f.speed]) ?? '—'">
          <InputNumber :model-value="draft[f.id]" :input-id="`tf-${f.id}`" :min="0" :max="100" :step="5" suffix=" %" placeholder="%" :use-grouping="false" size="small"
                       :input-style="{ width: '72px' }" :disabled="!!guidedWhy" :pt="{ pcInputText: { root: { 'aria-describedby': why } } }"
                       @input="e => (draft = { ...draft, [f.id]: typeof e.value === 'number' ? e.value : null })"
                       @update:model-value="v => (draft = { ...draft, [f.id]: v })" @keydown.enter="setFan(f.id)" />
          <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('fan.set', { fan: t(f.label) })" :disabled="!!guidedWhy || draft[f.id] == null"
                  :aria-describedby="why" :loading="tracker.isBusy(`tf:${f.id}`)" :data-focus-key="`tf-${f.id}`" @click="setFan(f.id)" />
        </OuiControlRow>
        </div>
        <dl class="tf-cover">
          <div v-for="f in coverFans" :key="f.label"><dt>{{ f.label }}</dt><dd class="oui-num">{{ f.value ?? '—' }}</dd></div>
        </dl>
      </div>
    </div>
    <OuiEmpty v-else-if="s.phase === 'unreachable'" compact state="offline" :title="t('status.noStatus')" />
    <div v-else class="oui-stack u1-skel" aria-busy="true"><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
  </OuiPanel>
</template>
<style>
/* Dense: the readings two pairs a row where there is room, and shorter rows. */
@container oui-widget (min-width: 300px) { [data-test="temps-fans"] .tf-temps { grid-template-columns: max-content minmax(0, 1fr) max-content minmax(0, 1fr); gap: 4px var(--oui-s3); } }
[data-test="temps-fans"] .oui-control-row { min-height: 36px; }
/* Part cooling and auxiliary side by side, the top-cover readouts side by side under them; one column when narrow. The
   default widget is about 300-430 px wide, so a column is as narrow as 140 px: no icon tile on these rows (the panel has
   the fan icon) and the name may wrap. */
[data-test="temps-fans"] .tf-fans { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: var(--oui-s2) var(--oui-s4); }
[data-test="temps-fans"] .tf-fans > * { min-width: 0; }
[data-test="temps-fans"] .tf-cover { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: var(--oui-s2) var(--oui-s4); margin: var(--oui-s2) 0 0; }
[data-test="temps-fans"] .tf-cover > div { display: grid; gap: 2px; min-width: 0; }
[data-test="temps-fans"] .tf-cover dt { font-size: var(--oui-text-sm); color: var(--oui-muted); }
[data-test="temps-fans"] .tf-cover dd { margin: 0; font-weight: 600; }
/* A narrow widget sets a fan on the line under it. */
@container oui-widget (max-width: 520px) { [data-test="temps-fans"] .oui-control-row { grid-template-columns: minmax(0, 1fr) auto; }
  [data-test="temps-fans"] .oui-control-row-control { grid-column: 1 / -1; justify-content: flex-start; } }
[data-test="temps-fans"] .oui-controls { gap: var(--oui-s2) var(--oui-s6); }

/* Compact in a small widget: the readings, not the setters. */
@container oui-widget (max-width: 220px) { [data-test="temps-fans"] .oui-control-row-control { display: none; } }
</style>
