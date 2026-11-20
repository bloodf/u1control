<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import { OuiIcon, OuiSpark, type OuiTone } from '@orca-plugins/ui-foundation/src/components';
import { bed as bedIcon, nozzle } from '@orca-plugins/ui-foundation/src/icons';
import { s, run, tracker, controlsOff, printing, printerName, stale } from '../app/store';
import { ask } from '../core/dialog';
import { locale, t, fmt } from '../core/i18n';
import { acceptDot } from '../core/decimal-input';
import { heaterPhase, parseTarget } from '../core/logic';

// One heater: what it reads, what it is set to, and the field to change it. `id` is the printer's key ("0".."3", "bed").
// The bed is a row of its panel; a toolhead's heater sits inside its toolhead card (`card`).
// Safety rules kept here: a blank field never sends 0, an out-of-range value is refused with the limit (not clamped),
// heating always asks first, Off asks during a print, and Off stays available whatever target the page last saw.
// This is OuiSetpoint's row (same columns, same phase colours) with those rules. OuiSetpoint 5.0.6 can carry them now
// (v-model:draft, invalid, error-id, validate, input-props, off-always): moving to it is a later change, with the
// page tests of these rules (B-01, U02, the decimal input ones) as its check.
const dot = computed(() => acceptDot(locale.value));
const props = defineProps<{ id: string; card?: boolean }>();
const isBed = props.id === 'bed';
const name = computed(() => (isBed ? t('temps.heater.bed') : t('temps.heater.head', { n: Number(props.id) + 1 })));
const reading = computed(() => (isBed ? s.status?.bed : s.status?.extruders[Number(props.id)]));
const max = computed(() => (isBed ? s.limits.bed : s.limits.hotend));
const key = 'temp:' + props.id;

// InputNumber commits its model on blur; the typed value is tracked on every input so the buttons react at once.
const draft = ref<number | null>(null);
const asNumber = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const parsed = computed(() => parseTarget(draft.value, max.value));
const invalid = computed(() => parsed.value.kind === 'invalid');
const setOff = computed(() => !!controlsOff.value || parsed.value.kind === 'empty' || invalid.value || tracker.isBusy(key));

const phase = computed(() => (stale.value ? null : heaterPhase(reading.value?.temp, reading.value?.target)));
const tone = computed<OuiTone>(() => (phase.value ? ({ heating: 'orange', target: 'success', cooling: 'sky', off: 'neutral' } as const)[phase.value] : 'neutral'));
const temp = computed(() => (reading.value?.temp == null ? '—' : fmt.number(reading.value.temp, 1)));
const targetText = computed(() => (reading.value?.target ? t('temps.targetIs', { target: fmt.number(reading.value.target) }) : ''));

async function turnOff() {
  if (printing.value && !await ask({ title: t('confirm.off.title', { heater: name.value }), text: t('confirm.off.text', { heater: name.value, printer: printerName.value }),
    yes: t('confirm.off.yes', { heater: name.value }), no: t('confirm.off.no'), danger: true })) return;
  await run({ key, label: t('act.temperature', { heater: name.value }), cmd: 'temperature', args: { heater: props.id, target: 0 }, okText: t('ok.off', { heater: name.value }) });
}
async function setTemp() {
  const p = parsed.value;
  if (controlsOff.value) return;
  if (p.kind === 'off') return turnOff();
  if (p.kind !== 'heat') return;
  const value = p.value;
  if (!await ask({ title: t('confirm.heat.title', { heater: name.value }), text: t('confirm.heat.text', { heater: name.value, printer: printerName.value, value }),
    yes: t('confirm.heat.yes', { value }), no: t('common.goBack') })) return;
  const r = await run({ key, label: t('act.temperature', { heater: name.value }), cmd: 'temperature', args: { heater: props.id, target: value },
    okText: t('ok.heat', { heater: name.value, value }) });
  if (r.ok) draft.value = null;
}
</script>

<template>
  <div v-if="reading" class="u1-heat" :data-heater-row="id" :data-card="card || undefined">
    <div class="u1-heat-row">
      <div v-if="!card" class="u1-heat-label"><OuiIcon :icon="bedIcon" :size="14" tile :tone="tone" /><span class="oui-strong">{{ t('temps.bed') }}</span></div>
      <div class="u1-heat-read oui-num" :data-tone="tone">
        <OuiIcon v-if="card" :icon="nozzle" :size="14" tile :tone="tone" />
        <span class="u1-heat-temp"><strong>{{ temp }}<span class="u1-heat-unit">°C</span></strong>
          <span class="oui-meta"><template v-if="targetText">{{ targetText }}<template v-if="phase"> · <span class="u1-heat-phase">{{ t(`temps.phase.${phase}` as any) }}</span></template></template>
            <template v-else-if="phase === 'off'">{{ t('temps.heaterOff') }}</template></span></span>
      </div>
      <OuiSpark v-if="(s.history[id]?.length ?? 0) >= 2" class="u1-heat-spark" :values="s.history[id] ?? []" :tone="tone" :target="reading.target || null" :width="card ? 64 : 88" :height="card ? 22 : 28"
                :label="t('temps.history', { heater: name })" />
      <div class="u1-heat-set">
        <InputNumber v-bind="dot" :locale="locale" :max-fraction-digits="1" :model-value="draft" :input-id="'temp-' + id" :min="0" :max="max" :use-grouping="false" :allow-empty="true" size="small"
                     :input-style="{ width: '72px' }" :placeholder="`0–${max}`" :aria-label="t('temps.target', { heater: name })"
                     :pt="{ pcInputText: { root: { 'aria-describedby': controlsOff ? 'heads-why' : 'temp-why-' + id } } }" :invalid="invalid" :disabled="!!controlsOff"
                     @input="e => (draft = asNumber(e.value))" @update:model-value="v => (draft = v)" @keydown.enter="setTemp" />
        <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('temps.setFor', { heater: name })" :disabled="setOff"
                :aria-describedby="controlsOff ? 'heads-why' : undefined" :loading="tracker.isBusy(key)" :data-focus-key="'set-' + id" :data-set="id" @click="setTemp" />
        <Button severity="secondary" text size="small" :label="t('temps.off')" :aria-label="t('temps.offFor', { heater: name })"
                :disabled="!!controlsOff || tracker.isBusy(key)" :aria-describedby="controlsOff ? 'heads-why' : undefined"
                :data-focus-key="'off-' + id" :data-off="id" @click="turnOff" />
      </div>
    </div>
    <p :id="'temp-why-' + id" class="u1-heat-why" role="status">{{ invalid ? t('temps.invalid', { min: 0, max }) : '' }}</p>
  </div>
</template>

<style>
/* OuiSetpoint's row: label, reading, chart, control; the chart leaves first, then the control drops under. */
.u1-heat { container: u1-heat / inline-size; }
.u1-heat-row { display: grid; grid-template-columns: minmax(84px, 1fr) minmax(96px, auto) minmax(0, 1fr) auto; align-items: center; gap: var(--oui-s2) var(--oui-s3); min-height: 44px; }
.u1-heat-label { display: flex; align-items: center; gap: var(--oui-s2); min-width: 0; }
.u1-heat-read { display: flex; align-items: center; gap: var(--oui-s2); min-width: 0; }
.u1-heat-temp { display: grid; min-width: 0; line-height: 1.25; }
.u1-heat-temp strong { font-size: var(--oui-text-xl); line-height: 1.15; font-weight: 700; letter-spacing: -.01em; color: var(--oui-tone); }
.u1-heat-read[data-tone='neutral'] strong { color: var(--oui-text); }
.u1-heat-unit { margin-inline-start: .2em; font-size: .6em; font-weight: 600; }
.u1-heat-phase { font-weight: 600; color: var(--oui-tone); }
.u1-heat-spark { justify-self: start; }
.u1-heat-set { display: flex; align-items: center; justify-content: flex-end; gap: var(--oui-s1); grid-column: -2 / -1; }
.u1-heat-why { font-size: var(--oui-text-sm); color: var(--oui-danger); text-align: end; }
.u1-heat-why:empty { display: none; }
@container u1-heat (max-width: 520px) { .u1-heat:not([data-card]) .u1-heat-spark { display: none; } .u1-heat:not([data-card]) .u1-heat-row { grid-template-columns: minmax(84px, 1fr) minmax(96px, 1fr) auto; } }
@container u1-heat (max-width: 400px) { .u1-heat:not([data-card]) .u1-heat-row { grid-template-columns: minmax(0, 1fr) auto; } .u1-heat:not([data-card]) .u1-heat-set { grid-column: 1 / -1; } }
/* In a toolhead card: reading and chart on one line, the field under it. */
.u1-heat[data-card] { padding-top: var(--oui-s2); border-top: 1px solid var(--oui-border); }
.u1-heat[data-card] .u1-heat-row { grid-template-columns: minmax(0, 1fr) auto; min-height: 0; }
.u1-heat[data-card] .u1-heat-set { grid-column: 1 / -1; justify-content: flex-start; }
.u1-heat[data-card] .u1-heat-temp strong { font-size: var(--oui-text-lg); line-height: 1.25; letter-spacing: 0; }
.u1-heat[data-card] .u1-heat-unit { font-size: 1em; font-weight: 700; }
.u1-heat[data-card] .u1-heat-why { text-align: start; }
</style>
