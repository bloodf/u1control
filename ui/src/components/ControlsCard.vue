<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import Select from 'primevue/select';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiControlRow, OuiEmpty, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { light, speed as speedIcon, thermometer, wind } from '@orca-plugins/ui-foundation/src/icons';
import HeaterControl from './HeaterControl.vue';
import { s, run, tracker, controlsOff } from '../app/store';
import { locale, t } from '../core/i18n';
import { acceptDot } from '../core/decimal-input';
import { coverMode, parseSpeed } from '../core/logic';

// The Dashboard's one Controls module, a group per task: Temperature (the bed heater; the four nozzle heaters are in
// their toolhead cards) and Machine (print speed, the top cover's mode, the chamber light; the fans are all in
// Temperatures & fans). Each row says what it reads now; a refused value says so in that place. The speed field has no
// min or max of its own: what was typed stays as typed and is refused, never turned into the limit.
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
// The top cover: what it is doing now is the row's value and the choice shown. The printer reports "cooling" without
// saying strong or weak, so that one is known only when this page set it.
const cover = computed(() => coverMode(st.value?.purifier?.mode));
const applied = ref<string | null>(null);
const purNow = computed(() => (cover.value === 'cooling' ? (applied.value === 'strong' || applied.value === 'weak' ? applied.value : null) : cover.value || null));
const purPick = ref<string | null>(null);
const purChoice = computed(() => purPick.value ?? purNow.value);
const purText = computed(() => (cover.value ? t(`purifier.${purNow.value ?? cover.value}` as any) : undefined));
const purOptions = computed(() => ['strong', 'weak', 'keep-warm', 'idle'].map(v => ({ value: v, label: t(`purifier.${v}` as any) })));
async function setPurifier() {
  const mode = purChoice.value;
  if (!mode || mode === purNow.value || controlsOff.value) return;
  const r = await run({ key: 'purifier', label: t('act.purifier'), cmd: 'purifier', args: { mode }, okText: t('ok.purifier') });
  if (r.ok) { applied.value = mode; purPick.value = null; }
}
async function setLight(on: boolean) {
  await run({ key: 'light', label: t('act.light'), cmd: 'light', args: { on } });
}
</script>

<template>
  <OuiPanel :icon="thermometer" tone="orange" aria-labelledby="bed-h" data-test="controls">
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
          <InputNumber v-bind="dot" :locale="locale" :max-fraction-digits="1" :model-value="speedDraft" input-id="speed" :step="5" suffix=" %" placeholder="10–300" :use-grouping="false" size="small"
                       :input-style="{ width: '72px' }" :invalid="speedDraft != null && speedValue == null" :disabled="!!controlsOff"
                       :pt="{ pcInputText: { root: { 'aria-describedby': why ?? 'speed-why' } } }"
                       @input="e => (speedDraft = asNumber(e.value))" @update:model-value="v => (speedDraft = v)" @keydown.enter="setSpeed" />
          <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('speed.set')" :disabled="!!controlsOff || speedValue == null" :aria-describedby="why"
                  :loading="tracker.isBusy('speed')" data-focus-key="speed" @click="setSpeed" />
        </OuiControlRow>
        <!-- A cover that is not fitted has nothing to set: the row says so, without a control that cannot work. -->
        <OuiControlRow v-if="st.purifier?.fitted === false" :label="t('purifier.label')" :icon="wind" tone="sky" :value="t('purifier.notFitted')" data-test="cover-row" />
        <OuiControlRow v-else :label="t('purifier.label')" :icon="wind" tone="sky" :value="purText" data-test="cover-row">
          <Select :model-value="purChoice" :options="purOptions" option-label="label" option-value="value" :placeholder="t('purifier.choose')" size="small"
                  :aria-label="t('purifier.label')" :disabled="!!controlsOff" :pt="{ label: { 'aria-describedby': why } }" data-test="cover-mode" @update:model-value="v => (purPick = v)" />
          <Button severity="secondary" size="small" :label="t('common.apply')" :disabled="!!controlsOff || !purChoice || purChoice === purNow" :aria-describedby="why" :loading="tracker.isBusy('purifier')"
                  data-focus-key="purifier" @click="setPurifier" />
        </OuiControlRow>
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
/* Dense rows on the dashboard. */
[data-test="controls"] .oui-control-row { min-height: 36px; }
/* A narrow widget (4 of 12 columns in a 900 px window) sets a row's field on the line under its name. */
@container oui-widget (max-width: 340px) { [data-test="controls"] .oui-control-row { grid-template-columns: minmax(0, 1fr) auto; }
  [data-test="controls"] .oui-control-row-control { grid-column: 1 / -1; justify-content: flex-start; min-width: 0; flex-wrap: wrap; } }
[data-test="controls"] .oui-controls { gap: var(--oui-s2) var(--oui-s6); }

/* A value the row refused (a speed outside 10 to 300 %) is said in the row, in the error colour. */
.u1-refused { color: var(--oui-danger); font-weight: 600; }
/* A reason in a row (speed refused) is a sentence: it wraps instead of being cut. */
.u1-row-note { display: block; white-space: normal; }
</style>
