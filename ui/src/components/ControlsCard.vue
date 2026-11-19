<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import Select from 'primevue/select';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiControlRow, OuiEmpty, OuiPanel } from '../../shared/src/components';
import { light, speed as speedIcon, thermometer, wind } from '../../shared/src/icons';
import HeaterControl from './HeaterControl.vue';
import { s, run, tracker, controlsOff } from '../app/store';
import { locale, t } from '../core/i18n';
import { acceptDot } from '../core/decimal-input';
import { parseSpeed } from '../core/logic';

// The Dashboard's one Controls module, a group per task: Temperature (the bed heater; the four nozzle heaters are in
// their toolhead cards) and Machine (print speed, the top cover and its fans, the chamber light). Each row says what it
// reads now; a refused value or a fan that is held off says so in that place.
const dot = computed(() => acceptDot(locale.value));
const st = computed(() => s.status);
const why = computed(() => (controlsOff.value ? 'heads-why' : undefined));
const asNumber = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const speedDraft = ref<number | null>(null);
const speedNow = computed(() => Math.round((st.value?.speed_factor ?? 1) * 100));
const speedValue = computed(() => parseSpeed(speedDraft.value));
async function setSpeed() {
  const v = speedValue.value;
  if (v == null || controlsOff.value) return;
  const r = await run({ key: 'speed', label: t('act.speed'), cmd: 'speed', args: { percent: v }, okText: t('ok.speed', { value: v }) });
  if (r.ok) speedDraft.value = null;
}
const purMode = ref<string | null>(null);
const purOptions = computed(() => ['strong', 'weak', 'keep-warm', 'idle'].map(v => ({ value: v, label: t(`purifier.${v}` as any) })));
const setPurifier = () => purMode.value && run({ key: 'purifier', label: t('act.purifier'), cmd: 'purifier', args: { mode: purMode.value }, okText: t('ok.purifier') });
// Top-cover fans, live: only when the printer has SET_PURIFIER. Recirculation (keep warm) keeps the exhaust off.
const fansShown = computed(() => st.value?.purifier?.fitted !== false && (st.value?.features ?? []).includes('cover_fan'));
const exhaustBlocked = computed(() => !!st.value?.purifier?.recirculating);
const fans = [{ id: 'exhaust', label: 'pref.exhaust_fan' }, { id: 'inner', label: 'pref.inner_fan' }] as const;
const fanDraft = ref<Record<string, number | null>>({ exhaust: null, inner: null });
const fanOff = (id: string) => !!controlsOff.value || (id === 'exhaust' && exhaustBlocked.value);
async function setFan(id: string) {
  const v = fanDraft.value[id];
  if (v == null || fanOff(id)) return;
  const r = await run({ key: `fan:${id}`, label: t('act.purifier'), cmd: 'cover_fan', args: { fan: id, percent: v }, okText: t('ok.fan') });
  if (r.ok) fanDraft.value = { ...fanDraft.value, [id]: null };
}
async function setLight(on: boolean) {
  await run({ key: 'light', label: t('act.light'), cmd: 'light', args: { on } });
}
</script>

<template>
  <OuiPanel :icon="thermometer" tone="orange" aria-labelledby="bed-h">
    <template #title><span id="bed-h">{{ t('controls.title') }}</span></template>
    <div v-if="st" class="oui-controls">
      <div class="oui-controls-group">
        <p class="oui-label">{{ t('controls.temperature') }}</p>
        <HeaterControl id="bed" />
      </div>
      <div class="oui-controls-group">
        <p class="oui-label">{{ t('controls.machine') }}</p>
        <OuiControlRow :label="t('speed.label')" :icon="speedIcon" tone="cobalt" for="speed">
          <template #value><span id="speed-why" role="status" class="u1-row-note" :class="{ 'u1-refused': speedDraft != null && speedValue == null }">{{ speedDraft != null && speedValue == null ? t('speed.invalid') : `${speedNow} %` }}</span></template>
          <InputNumber v-bind="dot" :locale="locale" :max-fraction-digits="1" :model-value="speedDraft" input-id="speed" :min="10" :max="300" :step="5" suffix=" %" placeholder="10–300" :use-grouping="false" size="small"
                       :input-style="{ width: '72px' }" :invalid="speedDraft != null && speedValue == null" :disabled="!!controlsOff"
                       :pt="{ pcInputText: { root: { 'aria-describedby': why ?? 'speed-why' } } }"
                       @input="e => (speedDraft = asNumber(e.value))" @update:model-value="v => (speedDraft = v)" @keydown.enter="setSpeed" />
          <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('speed.set')" :disabled="!!controlsOff || speedValue == null" :aria-describedby="why"
                  :loading="tracker.isBusy('speed')" data-focus-key="speed" @click="setSpeed" />
        </OuiControlRow>
        <OuiControlRow :label="t('purifier.label')" :icon="wind" tone="sky" :value="st.purifier?.fitted === false ? t('purifier.notFitted') : undefined">
          <Select v-model="purMode" :options="purOptions" option-label="label" option-value="value" :placeholder="t('purifier.choose')" size="small"
                  :aria-label="t('purifier.label')" :disabled="!!controlsOff" :pt="{ label: { 'aria-describedby': why } }" />
          <Button severity="secondary" size="small" :label="t('common.apply')" :disabled="!!controlsOff || !purMode" :aria-describedby="why" :loading="tracker.isBusy('purifier')"
                  data-focus-key="purifier" @click="setPurifier" />
        </OuiControlRow>
        <template v-if="fansShown">
          <OuiControlRow v-for="f in fans" :key="f.id" :label="t(f.label)" :icon="wind" tone="sky" :for="`fan-${f.id}`">
            <template #value><span :id="`fan-${f.id}-why`" role="status" class="u1-row-note">{{ f.id === 'exhaust' && exhaustBlocked ? t('fan.exhaustBlocked') : '' }}</span></template>
            <InputNumber :model-value="fanDraft[f.id]" :input-id="`fan-${f.id}`" :min="0" :max="100" :step="5" suffix=" %" placeholder="%" :use-grouping="false" size="small"
                         :input-style="{ width: '72px' }" :disabled="fanOff(f.id)" :pt="{ pcInputText: { root: { 'aria-describedby': why ?? `fan-${f.id}-why` } } }"
                         @update:model-value="v => (fanDraft = { ...fanDraft, [f.id]: v })" @keydown.enter="setFan(f.id)" />
            <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('fan.set', { fan: t(f.label) })" :disabled="fanOff(f.id) || fanDraft[f.id] == null"
                    :aria-describedby="why ?? `fan-${f.id}-why`" :loading="tracker.isBusy(`fan:${f.id}`)" :data-focus-key="`fan-${f.id}`" @click="setFan(f.id)" />
          </OuiControlRow>
        </template>
        <OuiControlRow :label="t('light.label')" :icon="light" tone="lime" for="light" :value="st.light == null ? t('common.unknown') : t(st.light ? 'mode.on' : 'mode.off')">
          <ToggleSwitch input-id="light" :model-value="!!st.light" :disabled="!!controlsOff || tracker.isBusy('light')" :aria-describedby="why" @update:model-value="setLight" />
        </OuiControlRow>
      </div>
    </div>
    <OuiEmpty v-else-if="s.phase === 'unreachable'" compact state="offline" :title="t('status.noStatus')" />
    <div v-else class="oui-stack u1-skel" aria-busy="true"><span class="oui-skeleton" /><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
  </OuiPanel>
</template>
<style>
/* A value the row refused (a speed outside 10 to 300 %) is said in the row, in the error colour. */
.u1-refused { color: var(--oui-danger); font-weight: 600; }
/* A reason in a row (speed refused, exhaust held off) is a sentence: it wraps instead of being cut. */
.u1-row-note { display: block; white-space: normal; }
</style>
