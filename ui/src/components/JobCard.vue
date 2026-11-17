<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiJob, OuiPanel, OuiReadout, OuiStatus, type OuiState } from '../../shared/src/components';
import { calendar, clock, hourglass, pause as pauseIcon, play, x } from '../../shared/src/icons';
import PrinterFigure from './PrinterFigure.vue';
import { s, run, tracker, controlsOff, printing, printerName, stale } from '../app/store';
import { ask } from '../core/dialog';
import { t, tMaybe, fmt } from '../core/i18n';

// The page's hero: the print (file, percentage, times) on the plugin's colour, or the idle printer. Last known
// values of a printer the page no longer hears from are drawn grey. Pause, Resume and Cancel sit under it.
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

const pauseWhy = computed(() => controlsOff.value || (state.value !== 'printing' ? t('reason.notPrinting') : tracker.isBusy('pause') ? t('reason.pending') : ''));
const resumeWhy = computed(() => controlsOff.value || (state.value !== 'paused' ? t('reason.notPaused') : tracker.isBusy('resume') ? t('reason.pending') : ''));
const cancelWhy = computed(() => controlsOff.value || (!printing.value ? t('reason.noPrint') : tracker.isBusy('cancel') ? t('reason.pending') : ''));
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
  <OuiPanel class="u1-job" flush :aria-label="t('status.title')" data-test="job-card">
    <OuiEmpty v-if="!st" compact :state="s.phase === 'unreachable' ? 'offline' : 'loading'" :title="t('status.noStatus')" />
    <OuiJob v-else-if="job" hero :stale="stale" :name="st.filename || stateName" :progress="pct" :progress-label="t('status.progress')" :detail="detail">
      <template #thumb><div class="u1-figure"><PrinterFigure :active="active" :stale="stale" /></div></template>
      <template #status>
        <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
        <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
      </template>
      <template v-if="printing">
        <OuiReadout :icon="clock" :label="t('status.elapsed')" :value="fmt.duration(st.total_duration)" size="sm" :stale="stale" />
        <OuiReadout :icon="hourglass" :label="t('status.left')" :value="left == null ? null : fmt.duration(left)" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
        <OuiReadout :icon="calendar" :label="t('status.finishes')" :value="finishes" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
      </template>
    </OuiJob>
    <div v-else class="oui-hero u1-idle" :class="{ 'oui-on-band': !stale }" :data-tone="stale ? 'neutral' : undefined">
      <div class="u1-figure"><PrinterFigure :stale="stale" /></div>
      <div class="u1-idle-id">
        <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
        <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
        <p class="u1-idle-name oui-truncate" :title="printerName">{{ printerName }}</p>
        <p class="u1-idle-detail">{{ detail || t('reason.noPrint') }}</p>
      </div>
    </div>
    <!-- Cancel is the destructive one: solid red, at the far end, and it asks first. Emergency stop is in the app bar. -->
    <div class="u1-job-actions" role="group" :aria-label="t('status.controls')">
      <Button severity="secondary" :label="t('act.pause')" :disabled="!!pauseWhy" :aria-describedby="why" :loading="tracker.isBusy('pause')" data-focus-key="pause" data-test="pause" @click="pause">
        <template #icon><OuiIcon :icon="pauseIcon" :size="14" /></template></Button>
      <Button severity="secondary" :label="t('act.resume')" :disabled="!!resumeWhy" :aria-describedby="why" :loading="tracker.isBusy('resume')" data-focus-key="resume" data-test="resume" @click="resume">
        <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
      <span class="oui-spacer" />
      <Button severity="danger" :label="t('act.cancel')" :disabled="!!cancelWhy" :aria-describedby="why" :loading="tracker.isBusy('cancel')" data-focus-key="cancel" data-test="cancel" @click="cancel">
        <template #icon><OuiIcon :icon="x" :size="14" /></template></Button>
    </div>
  </OuiPanel>
</template>

<style>
.u1-idle { display: flex; flex-direction: column; gap: var(--oui-s3); border-radius: var(--oui-radius-lg) var(--oui-radius-lg) 0 0; }
.u1-figure { width: min(100%, 248px); margin-inline: auto; padding-block: var(--oui-s1) var(--oui-s2); }
/* The printer photo gets its own row over the job's name and figure. */
.u1-job .oui-job-head { flex-wrap: wrap; }
.u1-job .oui-job-thumb { flex: 1 0 100%; }
.u1-idle-id { display: grid; gap: 2px; min-width: 0; }
.u1-idle-id > .oui-status { margin-bottom: 4px; }
.u1-idle-name { font-size: var(--oui-text-lg); font-weight: 700; line-height: 1.3; }
.u1-idle-detail { font-size: var(--oui-text-sm); }
.u1-job-actions { display: flex; flex-wrap: wrap; gap: var(--oui-s2); padding: var(--oui-s3) var(--oui-s4); }
</style>
