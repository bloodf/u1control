<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import ProgressBar from 'primevue/progressbar';
import Icon from './Icon.vue';
import { s, run, tracker, controlsOff, estopReason, printing, printerName } from '../app/store';
import { ask } from '../core/dialog';
import { t, tMaybe, fmt } from '../core/i18n';
import { parseTarget, parseSpeed } from '../core/logic';

const st = computed(() => s.status);
const state = computed(() => st.value?.state ?? '');
const stateText = computed(() => {
  if (!st.value) return t('status.noStatus');
  const name = tMaybe(`status.state.${state.value}`, state.value);
  return st.value.message ? `${name} · ${st.value.message}` : name;
});
const pct = computed(() => Math.max(0, Math.min(100, (st.value?.progress ?? 0) * 100)));
const left = computed(() => {
  const d = st.value;
  return d && (d.progress ?? 0) > 0.01 && d.print_duration ? d.print_duration / (d.progress as number) - d.print_duration : null;
});
const machine = computed(() => {
  const m = st.value?.machine_state;
  return m && m !== 'IDLE' ? t('status.machine', { state: m.toLowerCase().replace(/_/g, ' ') }) : '';
});

// ---------------------------------------------------------------- print controls
const pauseWhy = computed(() => controlsOff.value || (state.value !== 'printing' ? t('reason.notPrinting') : tracker.isBusy('pause') ? t('reason.pending') : ''));
const resumeWhy = computed(() => controlsOff.value || (state.value !== 'paused' ? t('reason.notPaused') : tracker.isBusy('resume') ? t('reason.pending') : ''));
const cancelWhy = computed(() => controlsOff.value || (!printing.value ? t('reason.noPrint') : tracker.isBusy('cancel') ? t('reason.pending') : ''));
const pause = () => run({ key: 'pause', label: t('act.pause'), cmd: 'pause', okText: t('ok.pause'), timeoutMs: 15000 });
const resume = () => run({ key: 'resume', label: t('act.resume'), cmd: 'resume', okText: t('ok.resume'), timeoutMs: 15000 });
async function cancel() {
  if (!await ask({ title: t('confirm.cancel.title'), text: t('confirm.cancel.text', { printer: printerName.value }),
    yes: t('confirm.cancel.yes'), no: t('confirm.cancel.no'), danger: true })) return;
  await run({ key: 'cancel', label: t('act.cancel'), cmd: 'cancel', okText: t('ok.cancel'), timeoutMs: 15000 });
}
async function estop() {
  if (!await ask({ title: t('confirm.estop.title'), text: t('confirm.estop.text', { printer: printerName.value }),
    yes: t('confirm.estop.yes'), no: t('common.goBack'), danger: true })) return;
  await run({ key: 'estop', label: t('act.estop'), cmd: 'emergency_stop', okText: t('ok.estop'), timeoutMs: 10000, allowRepeat: true });
}

// ---------------------------------------------------------------- temperatures
// InputNumber commits its model on blur; the typed value is tracked on every input so buttons react at once.
const asNumber = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
type HeaterKey = '0' | '1' | '2' | '3' | 'bed';
const drafts = reactive<Record<string, number | null>>({});
const heaters = computed(() => {
  const d = st.value;
  if (!d) return [];
  const rows = d.extruders.map((e, i) => ({ key: String(i) as HeaterKey, label: `T${i + 1}`, heater: t('temps.heater.head', { n: i + 1 }),
    reading: e, head: d.heads[i], max: s.limits.hotend, badge: `toolhead/t${i + 1}` }));
  return [...rows, { key: 'bed' as HeaterKey, label: t('temps.bed'), heater: t('temps.heater.bed'), reading: d.bed, head: undefined, max: s.limits.bed, badge: 'icon/bed' }];
});
const parsed = (key: string, max: number) => parseTarget(drafts[key], max);
function setWhy(key: string, max: number): string {
  if (controlsOff.value) return controlsOff.value;
  const p = parsed(key, max);
  if (p.kind === 'empty') return t('temps.empty');
  if (p.kind === 'invalid') return t('temps.invalid', { min: 0, max });
  return tracker.isBusy('temp:' + key) ? t('reason.pending') : '';
}
async function turnOff(key: string, heater: string) {
  if (printing.value && !await ask({ title: t('confirm.off.title', { heater }), text: t('confirm.off.text', { heater, printer: printerName.value }),
    yes: t('confirm.off.yes', { heater }), no: t('confirm.off.no'), danger: true })) return;
  await run({ key: 'temp:' + key, label: t('act.temperature', { heater }), cmd: 'temperature', args: { heater: key, target: 0 }, okText: t('ok.off', { heater }) });
}
async function setTemp(key: string, heater: string, max: number) {
  const p = parsed(key, max);
  if (p.kind === 'off') return turnOff(key, heater);
  if (p.kind !== 'heat') return;
  const value = p.value;
  if (!await ask({ title: t('confirm.heat.title', { heater }), text: t('confirm.heat.text', { heater, printer: printerName.value, value }),
    yes: t('confirm.heat.yes', { value }), no: t('common.goBack') })) return;
  const r = await run({ key: 'temp:' + key, label: t('act.temperature', { heater }), cmd: 'temperature', args: { heater: key, target: value },
    okText: t('ok.heat', { heater, value }) });
  if (r.ok) drafts[key] = null;
}

// ---------------------------------------------------------------- speed, cover, light
const speedDraft = ref<number | null>(null);
const speedNow = computed(() => Math.round((st.value?.speed_factor ?? 1) * 100));
const speedValue = computed(() => parseSpeed(speedDraft.value));
async function setSpeed() {
  const v = speedValue.value;
  if (v == null) return;
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
  <section class="u1-card" aria-labelledby="status-h">
    <h2 id="status-h">{{ t('status.title') }}</h2>
    <div class="u1-row">
      <strong data-test="state">{{ stateText }}</strong><span class="u1-spacer" />
      <span v-if="st?.layer" class="oui-meta">{{ t('status.layer', { n: st.layer, total: st.total_layers || '?' }) }}</span>
    </div>
    <ProgressBar :value="pct" :show-value="false" style="height: 8px; margin: 8px 0" :aria-label="t('status.progress')" />
    <div v-if="st?.filename" class="oui-meta st-file">{{ st.filename }}<template v-if="printing"> · {{ fmt.number(pct) }}%</template></div>
    <dl v-if="printing" class="st-kv">
      <dt>{{ t('status.elapsed') }}</dt><dd>{{ fmt.duration(st?.total_duration) }}</dd>
      <dt>{{ t('status.left') }}</dt><dd>{{ fmt.duration(left) }}</dd>
    </dl>
    <p v-if="machine" class="oui-meta">{{ machine }}</p>

    <div class="st-controls" role="group" :aria-label="t('status.controls')">
      <div class="u1-row">
        <Button severity="secondary" outlined :disabled="!!pauseWhy" :loading="tracker.isBusy('pause')" data-focus-key="pause" data-test="pause" @click="pause">
          <Icon name="icon/pause" /><span>{{ t('act.pause') }}</span></Button>
        <Button severity="secondary" outlined :disabled="!!resumeWhy" :loading="tracker.isBusy('resume')" data-focus-key="resume" data-test="resume" @click="resume">
          <Icon name="icon/resume" /><span>{{ t('act.resume') }}</span></Button>
        <Button severity="danger" outlined :disabled="!!cancelWhy" :loading="tracker.isBusy('cancel')" data-focus-key="cancel" data-test="cancel" @click="cancel">
          <Icon name="icon/cancel" /><span>{{ t('act.cancel') }}</span></Button>
      </div>
      <p v-if="controlsOff" class="u1-why" data-test="controls-why">{{ t('reason.controlsOff', { reason: controlsOff }) }}</p>
      <!-- Kept apart from Cancel (U12): its own group, its own rule (known target, even offline). -->
      <div class="st-urgent u1-row">
        <span class="oui-meta">{{ t('status.urgent') }}</span>
        <Button severity="danger" :disabled="!!estopReason" data-focus-key="estop" data-test="estop" @click="estop">
          <Icon name="icon/emergency-stop" /><span>{{ t('act.estop') }}</span></Button>
        <span v-if="tracker.isBusy('estop')" class="u1-why" role="status">{{ t('msg.waiting', { action: t('act.estop') }) }}</span>
        <span v-else-if="estopReason" class="u1-why">{{ estopReason }}</span>
      </div>
    </div>

    <h3 class="st-h3"><Icon name="icon/temperature" /> {{ t('temps.title') }}</h3>
    <div class="st-temps">
      <div v-for="h in heaters" :key="h.key" class="st-temp" :data-heater-row="h.key">
        <span class="st-tlabel"><Icon :name="h.badge" :size="20" /> {{ h.label }}</span>
        <span v-if="h.head" class="st-fil" :title="[h.head.vendor, h.head.type, h.head.sub_type].filter(Boolean).join(' ')">
          <span class="u1-sw" :style="{ background: h.head.colour || 'transparent' }" />
          <template v-if="h.head.loaded">{{ h.head.type }} <span class="oui-muted">{{ h.head.sub_type }}</span></template>
          <span v-else class="oui-muted">{{ t('heads.empty') }}</span>
        </span><span v-else class="st-fil" />
        <span class="u1-num st-read">{{ t('temps.reading', { temp: h.reading.temp == null ? '—' : fmt.number(h.reading.temp, 1), target: fmt.number(h.reading.target ?? 0) }) }}</span>
        <InputNumber :model-value="drafts[h.key]" :input-id="'temp-' + h.key" :min="0" :max="h.max" :use-grouping="false" :allow-empty="true"
                     input-class="st-input" :placeholder="t('temps.range', { min: 0, max: h.max })" :aria-label="t('temps.target', { heater: h.heater })"
                     :aria-describedby="'temp-why-' + h.key" :invalid="parsed(h.key, h.max).kind === 'invalid'" :disabled="!!controlsOff"
                     @input="e => (drafts[h.key] = asNumber(e.value))" @update:model-value="v => (drafts[h.key] = v)"
                     @keydown.enter="setTemp(h.key, h.heater, h.max)" />
        <Button severity="secondary" outlined :label="t('temps.set')" :aria-label="t('temps.setFor', { heater: h.heater })" :disabled="!!setWhy(h.key, h.max)"
                :loading="tracker.isBusy('temp:' + h.key)" :data-focus-key="'set-' + h.key" :data-set="h.key" @click="setTemp(h.key, h.heater, h.max)" />
        <Button severity="secondary" outlined :label="t('temps.off')" :aria-label="t('temps.offFor', { heater: h.heater })"
                :disabled="!!controlsOff || tracker.isBusy('temp:' + h.key)" :data-focus-key="'off-' + h.key" :data-off="h.key" @click="turnOff(h.key, h.heater)" />
        <span :id="'temp-why-' + h.key" class="u1-why st-why" :class="{ 'u1-err': parsed(h.key, h.max).kind === 'invalid' }">
          {{ parsed(h.key, h.max).kind === 'invalid' ? t('temps.invalid', { min: 0, max: h.max }) : '' }}</span>
      </div>
    </div>

    <div class="u1-row st-line">
      <label for="speed">{{ t('speed.label') }}</label>
      <InputNumber :model-value="speedDraft" input-id="speed" @input="e => (speedDraft = asNumber(e.value))" @update:model-value="v => (speedDraft = v)" :min="10" :max="300" :step="5" suffix=" %" :placeholder="`${speedNow} %`"
                   :use-grouping="false" :disabled="!!controlsOff" input-class="st-input" aria-describedby="speed-why" />
      <Button severity="secondary" outlined :label="t('speed.set')" :disabled="!!controlsOff || speedValue == null"
              :loading="tracker.isBusy('speed')" data-focus-key="speed" @click="setSpeed" />
      <span id="speed-why" class="u1-why">{{ speedDraft != null && speedValue == null ? t('speed.invalid') : '' }}</span>
    </div>
    <div class="u1-row st-line">
      <Icon name="icon/fan" /><label id="pur-l">{{ t('purifier.label') }}</label>
      <Select v-model="purMode" :options="purOptions" option-label="label" option-value="value" :placeholder="t('purifier.choose')"
              aria-labelledby="pur-l" :disabled="!!controlsOff" class="st-select" />
      <Button severity="secondary" outlined :label="t('common.apply')" :disabled="!!controlsOff || !purMode" :loading="tracker.isBusy('purifier')"
              data-focus-key="purifier" @click="setPurifier" />
      <span v-if="st?.purifier?.fitted === false" class="u1-why">{{ t('purifier.notFitted') }}</span>
    </div>
    <div class="u1-row st-line">
      <Checkbox input-id="light" binary :model-value="!!st?.light" :disabled="!!controlsOff || tracker.isBusy('light')" @update:model-value="setLight" />
      <label for="light"><Icon name="icon/chamber-light" /> {{ t('light.label') }}</label>
    </div>
  </section>
</template>

<style scoped>
.st-file { overflow-wrap: anywhere; }
.st-kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin: 8px 0; }
.st-kv dt { color: var(--oui-muted); } .st-kv dd { margin: 0; }
.st-controls { margin: 12px 0; display: grid; gap: 8px; }
.st-urgent { padding-top: 8px; border-top: 1px dashed var(--oui-border); }
.st-h3 { display: flex; align-items: center; gap: 6px; margin: 16px 0 8px; }
.st-temps { display: grid; gap: 8px; }
.st-temp { display: grid; grid-template-columns: 56px minmax(0, 140px) minmax(96px, auto) 110px auto auto; align-items: center; gap: 8px; }
.st-why { grid-column: 1 / -1; }
.st-why:empty { display: none; }
.st-tlabel { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; }
.st-fil { display: inline-flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.st-line { margin-top: 12px; }
.st-select { min-width: 180px; }
:deep(.st-input) { width: 110px; }
@media (max-width: 560px) {
  .st-temp { grid-template-columns: minmax(0, 1fr) auto auto; }
  .st-fil { grid-column: 2 / -1; }
  .st-read { grid-column: 1 / -1; }
  :deep(.st-input), :deep(.st-input input) { width: 100%; min-width: 0; }
}
</style>
