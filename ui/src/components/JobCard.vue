<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiJob, OuiPanel, OuiReadout, OuiStatus, type OuiState } from '../../shared/src/components';
import { calendar, clock, hourglass, pause as pauseIcon, play, x } from '../../shared/src/icons';
import PrinterFigure from './PrinterFigure.vue';
import { s, run, tracker, controlsOff, printing, printerName, stale } from '../app/store';
import { ask } from '../core/dialog';
import { t, tMaybe, fmt } from '../core/i18n';

// The Dashboard's status block: the printer picture in the job's 72 px box, the print (file, percentage, times) or the
// idle printer, and the print's own actions at its right: Pause while printing, Resume while paused, Cancel for both.
// Last known values of a printer the page no longer hears from are drawn grey.
const st = computed(() => s.status);
const state = computed(() => st.value?.state ?? '');
const stateName = computed(() => tMaybe(`status.state.${state.value}`, state.value));
const chip = computed<OuiState>(() => (({ printing: 'busy', paused: 'pending', cancelled: 'idle', error: 'error' } as Record<string, OuiState>)[state.value] ?? 'ok'));
const job = computed(() => printing.value || (!!st.value?.filename && ['complete', 'cancelled', 'error'].includes(state.value)));
// A print that reports no fraction is shown as unknown, never as 0 %.
const pct = computed(() => (typeof st.value?.progress === 'number' ? Math.max(0, Math.min(100, st.value.progress * 100)) : null));
const left = computed(() => {
  const d = st.value;
  return d && (d.progress ?? 0) > 0.01 && d.print_duration ? d.print_duration / (d.progress as number) - d.print_duration : null;
});
const finishes = computed(() => (state.value === 'printing' && left.value != null ? fmt.time(s.now / 1000 + left.value) : null));
const machine = computed(() => {
  const m = st.value?.machine_state;
  return m && m !== 'IDLE' ? t('status.machine', { state: m.toLowerCase().replace(/_/g, ' ') }) : '';
});
const detail = computed(() => [stale.value ? stateName.value : '', st.value?.message, st.value?.layer ? t('status.layer', { n: st.value.layer, total: st.value.total_layers || '?' }) : '',
  machine.value].filter(Boolean).join(' · '));
const active = computed(() => { const i = st.value?.extruders.findIndex(e => e.active) ?? -1; return printing.value && i >= 0 ? i + 1 : null; });
const lastKnown = computed(() => t('bar.lastKnown', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }));

const pauseWhy = computed(() => controlsOff.value || (tracker.isBusy('pause') ? t('reason.pending') : ''));
const resumeWhy = computed(() => controlsOff.value || (tracker.isBusy('resume') ? t('reason.pending') : ''));
const cancelWhy = computed(() => controlsOff.value || (tracker.isBusy('cancel') ? t('reason.pending') : ''));
const why = computed(() => (controlsOff.value ? 'heads-why' : undefined));
const pause = () => run({ key: 'pause', label: t('act.pause'), cmd: 'pause', okText: t('ok.pause'), timeoutMs: 15000 });
const resume = () => run({ key: 'resume', label: t('act.resume'), cmd: 'resume', okText: t('ok.resume'), timeoutMs: 15000 });
async function cancel() {
  if (!await ask({ title: t('confirm.cancel.title'), text: t('confirm.cancel.text', { printer: printerName.value }),
    yes: t('confirm.cancel.yes'), no: t('confirm.cancel.no'), danger: true })) return;
  await run({ key: 'cancel', label: t('act.cancel'), cmd: 'cancel', okText: t('ok.cancel'), timeoutMs: 15000 });
}
</script>

<template>
  <OuiPanel class="oui-dash-top u1-job" :aria-label="t('status.title')" data-test="job-card">
    <div v-if="!st && s.phase !== 'unreachable'" class="u1-job-skel" aria-busy="true" :aria-label="t('status.noStatus')">
      <span class="oui-skeleton" /><div class="oui-stack"><span class="oui-skeleton" /><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
    </div>
    <OuiEmpty v-else-if="!st" compact state="offline" :title="t('status.noStatus')" />
    <OuiJob v-else-if="job" :stale="stale" :name="st.filename || stateName" :progress="pct" :progress-label="t('status.progress')" :detail="detail">
      <template #thumb><PrinterFigure :active="active" :stale="stale" /></template>
      <template #status>
        <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
        <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
      </template>
      <template v-if="printing">
        <OuiReadout :icon="clock" :label="t('status.elapsed')" :value="fmt.duration(st.total_duration)" size="sm" :stale="stale" />
        <OuiReadout :icon="hourglass" :label="t('status.left')" :value="left == null ? null : fmt.duration(left)" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
        <OuiReadout :icon="calendar" :label="t('status.finishes')" :value="finishes" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
      </template>
      <!-- One button per choice: Pause while it prints, Resume while it is paused. Cancel is the destructive one: red
           outline, last, and it asks first. Emergency stop is in the app bar. -->
      <template v-if="printing" #actions>
        <Button v-if="state === 'paused'" severity="secondary" :label="t('act.resume')" :disabled="!!resumeWhy" :aria-describedby="why" :loading="tracker.isBusy('resume')" data-focus-key="resume" data-test="resume" @click="resume">
          <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
        <Button v-else severity="secondary" :label="t('act.pause')" :disabled="!!pauseWhy" :aria-describedby="why" :loading="tracker.isBusy('pause')" data-focus-key="pause" data-test="pause" @click="pause">
          <template #icon><OuiIcon :icon="pauseIcon" :size="14" /></template></Button>
        <Button severity="danger" outlined :label="t('act.cancel')" :disabled="!!cancelWhy" :aria-describedby="why" :loading="tracker.isBusy('cancel')" data-focus-key="cancel" data-test="cancel" @click="cancel">
          <template #icon><OuiIcon :icon="x" :size="14" /></template></Button>
      </template>
    </OuiJob>
    <!-- Idle: the job block's own parts without a percentage (OuiJob always draws one). -->
    <div v-else class="oui-job" :data-stale="stale || undefined"><div class="oui-job-block" data-thumb>
      <div class="oui-job-thumb"><PrinterFigure :stale="stale" /></div>
      <div class="oui-job-id">
        <div class="oui-job-status">
          <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
          <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
        </div>
        <p class="oui-job-name" :title="printerName">{{ printerName }}</p>
        <p class="oui-job-detail oui-truncate">{{ detail || t('reason.noPrint') }}</p>
      </div>
    </div></div>
  </OuiPanel>
</template>

<style>
/* The printer photo in the job's 72 px picture box: as high as the box allows, never sized by the photo. */
.oui-job-thumb > .pf { width: auto; height: 64px; }
.u1-job-skel { display: grid; grid-template-columns: 72px minmax(0, 1fr); align-items: center; gap: var(--oui-s4); }
.u1-job-skel > .oui-skeleton { height: 72px; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(1) { width: 30%; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(2) { width: 60%; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(3) { height: 8px; }
</style>
