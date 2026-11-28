<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import { OuiEmpty, OuiPanel, OuiReadout, OuiStatus } from '@orca-plugins/ui-foundation/src/components';
import { fan as fanIcon, thermometer } from '@orca-plugins/ui-foundation/src/icons';
import { s, run, tracker, controlsOff, guidedWhy } from '../app/store';
import { t } from '../core/i18n';

// What the U1 reads besides the heaters: the chamber, the stepper drivers that report, and its four fans. Every fan
// says what it runs at now, beside the field that sets it. Part cooling and auxiliary are set only on an idle U1, like
// Load and Park (the plugin checks again). The two top-cover fans are set whenever the printer answers, where its
// firmware has the command; the exhaust stays off while the cover recirculates, and says so.
// Its settings say which readings show. In a small widget it is compact: the readings only, without the setters
// (container query on the widget, below).
const props = withDefaults(defineProps<{ config?: { chamber?: boolean; drivers?: boolean; fans?: boolean } }>(), { config: () => ({}) });
const show = (k: 'chamber' | 'drivers' | 'fans') => props.config[k] !== false;
const st = computed(() => s.status);
const pct = (v: unknown) => (typeof v === 'number' ? `${Math.round(v * 100)} %` : null);
const deg = (v: unknown) => (typeof v === 'number' ? `${Math.round(v)} °C` : null);
// A driver reports only while its motor is on: the ones that read a temperature or warn are listed. "OK" without a
// temperature is not a reading; with none to list, one line says the motors are off.
const drivers = computed(() => (st.value?.drivers ?? []).filter(d => d.temp != null || d.state === 'otpw' || d.state === 'ot'));

interface FanRow { id: string; label: string; now: string | null; input: string; key: string; cmd: string; act: string; done: string; off: boolean; why?: string }
const blocked = computed(() => !!st.value?.purifier?.recirculating);
const fans = computed<FanRow[]>(() => {
  const p = st.value?.purifier;
  // Set here only when the printer has SET_PURIFIER; without it the two cover fans are readings.
  const live = (st.value?.features ?? []).includes('cover_fan');
  const guided = (id: 'part' | 'aux', speed: unknown): FanRow => ({ id, label: t(`tf.${id}`), now: pct(speed), input: `tf-${id}`, key: `tf:${id}`, cmd: 'fan', act: t('tf.act'), done: t('tf.done'),
    off: !!guidedWhy.value, why: guidedWhy.value ? 'heads-why' : undefined });
  const cover = (id: 'exhaust' | 'inner', speed: unknown): FanRow => {
    const held = id === 'exhaust' && blocked.value;
    return { id, label: t(`tf.${id}`), now: pct(speed), input: `fan-${id}`, key: `fan:${id}`, cmd: live ? 'cover_fan' : '', act: t('act.purifier'), done: t('ok.fan'),
      off: !!controlsOff.value || held, why: controlsOff.value ? 'heads-why' : held ? 'fan-exhaust-why' : undefined };
  };
  return [guided('part', st.value?.fan), guided('aux', st.value?.aux_fan), ...(p?.fitted === false ? [] : [cover('exhaust', p?.exhaust), cover('inner', p?.inner)])];
});
const draft = ref<Record<string, number | null>>({});
async function setFan(f: FanRow) {
  const v = draft.value[f.id];
  if (v == null || f.off || !f.cmd) return;
  const r = await run({ key: f.key, label: f.act, cmd: f.cmd, args: { fan: f.id, percent: v }, okText: f.done });
  if (r.ok) draft.value = { ...draft.value, [f.id]: null };
}
</script>

<template>
  <OuiPanel :icon="fanIcon" tone="sky" aria-labelledby="tf-h" data-test="temps-fans">
    <template #title><span id="tf-h">{{ t('tf.title') }}</span></template>
    <div v-if="st" class="tf">
      <OuiReadout v-if="show('chamber')" :icon="thermometer" :label="t('tf.chamber')" :value="deg(st.chamber)" size="sm" :unknown-label="t('common.unknown')" data-test="tf-chamber" />
      <div v-if="show('drivers')" class="tf-group" data-test="tf-drivers">
        <p class="oui-label">{{ t('widget.drivers') }}</p>
        <dl v-if="drivers.length" class="tf-drivers">
          <div v-for="d in drivers" :key="d.name" :data-driver="d.name">
            <dt>{{ d.name }}</dt>
            <dd class="oui-num">{{ deg(d.temp) }} <OuiStatus v-if="d.state === 'otpw' || d.state === 'ot'" :state="d.state === 'ot' ? 'error' : 'warn'">{{ t(d.state === 'ot' ? 'tf.ot' : 'tf.otpw') }}</OuiStatus></dd>
          </div>
        </dl>
        <p v-else class="oui-meta">{{ t('tf.driversIdle') }}</p>
      </div>
      <div v-if="show('fans')" class="tf-group">
        <p class="oui-label">{{ t('tf.fans') }}</p>
        <div class="tf-fans">
          <div v-for="f in fans" :key="f.id" class="tf-fan" :data-fan="f.id">
            <component :is="f.cmd ? 'label' : 'span'" :for="f.cmd ? f.input : undefined" class="oui-strong">{{ f.label }}</component>
            <span v-if="f.now" class="tf-fan-now oui-num">{{ f.now }}</span>
            <span v-else class="tf-fan-now" :aria-label="t('common.unknown')">—</span>
            <div v-if="f.cmd" class="tf-fan-set">
              <InputNumber :model-value="draft[f.id] ?? null" :input-id="f.input" :min="0" :max="100" :step="5" suffix=" %" placeholder="%" :use-grouping="false" size="small" fluid
                           :disabled="f.off" :pt="{ pcInputText: { root: { 'aria-describedby': f.why } } }"
                           @input="e => (draft = { ...draft, [f.id]: typeof e.value === 'number' ? e.value : null })"
                           @update:model-value="v => (draft = { ...draft, [f.id]: v })" @keydown.enter="setFan(f)" />
              <Button severity="secondary" size="small" :label="t('temps.set')" :aria-label="t('fan.set', { fan: f.label })" :disabled="f.off || draft[f.id] == null"
                      :aria-describedby="f.why" :loading="tracker.isBusy(f.key)" :data-focus-key="f.input" @click="setFan(f)" />
            </div>
          </div>
        </div>
        <p id="fan-exhaust-why" role="status" class="oui-meta tf-note">{{ blocked && fans.some(f => f.id === 'exhaust' && f.cmd) ? t('fan.exhaustBlocked') : '' }}</p>
      </div>
    </div>
    <OuiEmpty v-else-if="s.phase === 'unreachable'" compact state="offline" :title="t('status.noStatus')" />
    <div v-else class="oui-stack u1-skel" aria-busy="true"><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
  </OuiPanel>
</template>
<style>
.tf { display: grid; gap: var(--oui-s3); min-width: 0; }
.tf-group { display: grid; gap: var(--oui-s1); min-width: 0; }
/* The drivers that report, as many a row as fit: a name and its temperature, a warning beside it. */
.tf-drivers { display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: 2px var(--oui-s3); margin: 0; }
.tf-drivers > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 var(--oui-s2); min-width: 0; }
.tf-drivers dt { color: var(--oui-muted); }
.tf-drivers dd { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s1); margin: 0; font-weight: 600; }
.tf-drivers > div:has(.oui-status) { grid-column: 1 / -1; }
/* Four fans, two a row from a 300 px widget on: the name and what it runs at now, then its field. */
.tf-fans { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 136px), 1fr)); align-items: end; gap: var(--oui-s3) var(--oui-s4); }
.tf-fan { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: baseline; align-content: start; gap: var(--oui-s1) var(--oui-s2); min-width: 0; }
.tf-fan > .oui-strong { overflow-wrap: anywhere; }
.tf-fan-now { font-weight: 700; }
.tf-fan-set { grid-column: 1 / -1; display: flex; align-items: center; gap: var(--oui-s1); min-width: 0; }
.tf-fan-set > .p-inputnumber { flex: 1 1 0; min-width: 0; }
.tf-note:empty { display: none; }
/* Compact in a small widget: the readings, not the setters. */
@container oui-widget (max-width: 220px) { .tf-fan-set { display: none; } }
</style>
