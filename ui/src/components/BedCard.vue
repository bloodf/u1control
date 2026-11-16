<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import Select from 'primevue/select';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiIcon, OuiPanel } from '../../shared/src/components';
import { bed, light, speed as speedIcon, wind } from '../../shared/src/icons';
import HeaterControl from './HeaterControl.vue';
import { s, run, tracker, controlsOff } from '../app/store';
import { locale, t } from '../core/i18n';
import { acceptDot } from '../core/decimal-input';
import { parseSpeed } from '../core/logic';

// What belongs to the machine as a whole: the bed heater, print speed, the top cover and the chamber light.
// The four nozzle heaters are in their toolhead cards.
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
async function setLight(on: boolean) {
  await run({ key: 'light', label: t('act.light'), cmd: 'light', args: { on } });
}
</script>

<template>
  <OuiPanel v-if="st" :icon="bed" tone="orange" aria-labelledby="bed-h">
    <template #title><span id="bed-h">{{ t('bed.title') }}</span></template>
    <div class="u1-rows">
      <HeaterControl id="bed" />
      <div class="u1-line">
        <label for="speed" class="u1-line-label"><OuiIcon :icon="speedIcon" :size="14" tile tone="cobalt" />{{ t('speed.label') }}</label>
        <span id="speed-why" class="u1-note" data-tone="danger" role="status">{{ speedDraft != null && speedValue == null ? t('speed.invalid') : '' }}</span>
        <InputNumber v-bind="dot" :locale="locale" :max-fraction-digits="1" :model-value="speedDraft" input-id="speed" :min="10" :max="300" :step="5" suffix=" %" :placeholder="`${speedNow} %`" :use-grouping="false" size="small"
                     :input-style="{ width: '72px' }" :invalid="speedDraft != null && speedValue == null" :disabled="!!controlsOff"
                     :pt="{ pcInputText: { root: { 'aria-describedby': why ?? 'speed-why' } } }"
                     @input="e => (speedDraft = asNumber(e.value))" @update:model-value="v => (speedDraft = v)" @keydown.enter="setSpeed" />
        <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('speed.set')" :disabled="!!controlsOff || speedValue == null" :aria-describedby="why"
                :loading="tracker.isBusy('speed')" data-focus-key="speed" @click="setSpeed" />
      </div>
      <div class="u1-line">
        <span id="pur-l" class="u1-line-label"><OuiIcon :icon="wind" :size="14" tile tone="sky" />{{ t('purifier.label') }}</span>
        <span v-if="st.purifier?.fitted === false" class="u1-note">{{ t('purifier.notFitted') }}</span>
        <Select v-model="purMode" :options="purOptions" option-label="label" option-value="value" :placeholder="t('purifier.choose')" size="small"
                aria-labelledby="pur-l" :disabled="!!controlsOff" :pt="{ label: { 'aria-describedby': why } }" />
        <Button severity="secondary" size="small" :label="t('common.apply')" :disabled="!!controlsOff || !purMode" :aria-describedby="why" :loading="tracker.isBusy('purifier')"
                data-focus-key="purifier" @click="setPurifier" />
      </div>
      <div class="u1-line">
        <label for="light" class="u1-line-label"><OuiIcon :icon="light" :size="14" tile tone="lime" />{{ t('light.label') }}</label>
        <span v-if="st.light == null" class="u1-note">{{ t('common.unknown') }}</span>
        <ToggleSwitch input-id="light" :model-value="!!st.light" :disabled="!!controlsOff || tracker.isBusy('light')" :aria-describedby="why" @update:model-value="setLight" />
      </div>
    </div>
  </OuiPanel>
</template>
