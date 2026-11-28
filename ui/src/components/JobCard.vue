<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiJob, OuiPanel, OuiReadout, OuiStatus, type OuiState } from '@orca-plugins/ui-foundation/src/components';
import { calendar, clock, files, hourglass, layers, pause as pauseIcon, play, x } from '@orca-plugins/ui-foundation/src/icons';
import PrinterFigure from './PrinterFigure.vue';
import { s, run, tracker, controlsOff, guidedWhy, printing, printerName, stale } from '../app/store';
import { ask } from '../core/dialog';
import { t, tMaybe, fmt } from '../core/i18n';

// The Dashboard's status block, in three shapes. A print that runs or is paused: the file, the percentage, the times,
// and Pause or Resume and Cancel. A print that ended (finished, cancelled, failed): how long it took and its layers in
// place of the bar, the printer's message in full on a failure, and Print again. An idle printer: what it is doing, and
// the way to the files. Last known values of a printer the page no longer hears from are drawn grey.
const st = computed(() => s.status);
const state = computed(() => st.value?.state ?? '');
const stateName = computed(() => tMaybe(`status.state.${state.value}`, state.value));
const chip = computed<OuiState>(() => (({ printing: 'busy', paused: 'pending', cancelled: 'idle', error: 'error' } as Record<string, OuiState>)[state.value] ?? 'ok'));
const ended = computed(() => !!st.value?.filename && ['complete', 'cancelled', 'error'].includes(state.value));
// A print that reports no fraction is shown as unknown, never as 0 %.
const pct = computed(() => (typeof st.value?.progress === 'number' ? Math.max(0, Math.min(100, st.value.progress * 100)) : null));
// Seconds left, worked out by the plugin (u1.time_left): the slicer's estimate when the file has one.
const left = computed(() => st.value?.left ?? null);
const finishes = computed(() => (state.value === 'printing' && left.value != null ? fmt.time(s.now / 1000 + left.value) : null));
// What the machine is doing besides printing (bed leveling, loading), in words; a state the page has no words for is left out.
const machine = computed(() => tMaybe(`status.machine.${st.value?.machine_state ?? ''}`, ''));
const layer = computed(() => (st.value?.layer ? t('status.layer', { n: st.value.layer, total: st.value.total_layers || '?' }) : ''));
const detail = computed(() => [stale.value ? stateName.value : '', state.value === 'error' ? '' : st.value?.message, layer.value, machine.value].filter(Boolean).join(' · '));
const layersDone = computed(() => st.value?.total_layers || st.value?.layer || null);
const active = computed(() => { const i = st.value?.extruders.findIndex(e => e.active) ?? -1; return printing.value && i >= 0 ? i + 1 : null; });
const lastKnown = computed(() => t('bar.lastKnown', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }));

const pauseWhy = computed(() => controlsOff.value || (tracker.isBusy('pause') ? t('reason.pending') : ''));
const resumeWhy = computed(() => controlsOff.value || (tracker.isBusy('resume') ? t('reason.pending') : ''));
const cancelWhy = computed(() => controlsOff.value || (tracker.isBusy('cancel') ? t('reason.pending') : ''));
const why = computed(() => (controlsOff.value ? 'heads-why' : undefined));
const pause = () => run({ key: 'pause', label: t('act.pause'), cmd: 'pause', okText: t('ok.pause'), timeoutMs: 15000 });
const resume = () => run({ key: 'resume', label: t('act.resume'), cmd: 'resume', okText: t('ok.resume'), timeoutMs: 15000 });
// Print again: the same command, question and idle rule as Print on the Files tab.
const againWhy = computed(() => guidedWhy.value || (tracker.isBusy('print') ? t('reason.pending') : ''));
async function again() {
  const name = st.value?.filename;
  if (!name || againWhy.value) return;
  if (!await ask({ title: t('act.printAgain'), text: t('confirm.print.text', { name: name.split('/').pop(), printer: printerName.value }), yes: t('confirm.print.yes'), no: t('common.goBack') })) return;
  await run({ key: 'print', label: t('act.printAgain'), cmd: 'print_file', args: { path: `gcodes/${name}` }, okText: t('ok.print'), timeoutMs: 60000 });
}
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
    <OuiJob v-else-if="printing" :stale="stale" :name="st.filename || stateName" :progress="pct" :progress-label="t('status.progress')" :detail="detail">
      <template #thumb><PrinterFigure :active="active" :stale="stale" /></template>
      <template #status>
        <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
        <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
      </template>
      <OuiReadout :icon="clock" :label="t('status.elapsed')" :value="fmt.duration(st.total_duration)" size="sm" :stale="stale" />
      <OuiReadout :icon="hourglass" :label="t('status.left')" :value="left == null ? null : fmt.duration(left)" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
      <OuiReadout :icon="calendar" :label="t('status.finishes')" :value="finishes" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
      <!-- One button per choice: Pause while it prints, Resume while it is paused. Cancel is the destructive one: red
           outline, last, and it asks first. Emergency stop is in the app bar. -->
      <template #actions>
        <Button v-if="state === 'paused'" severity="secondary" :label="t('act.resume')" :disabled="!!resumeWhy" :aria-describedby="why" :loading="tracker.isBusy('resume')" data-focus-key="resume" data-test="resume" @click="resume">
          <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
        <Button v-else severity="secondary" :label="t('act.pause')" :disabled="!!pauseWhy" :aria-describedby="why" :loading="tracker.isBusy('pause')" data-focus-key="pause" data-test="pause" @click="pause">
          <template #icon><OuiIcon :icon="pauseIcon" :size="14" /></template></Button>
        <Button severity="danger" outlined :label="t('act.cancel')" :disabled="!!cancelWhy" :aria-describedby="why" :loading="tracker.isBusy('cancel')" data-focus-key="cancel" data-test="cancel" @click="cancel">
          <template #icon><OuiIcon :icon="x" :size="14" /></template></Button>
      </template>
    </OuiJob>
    <!-- Not printing: the job block's own parts without a percentage (OuiJob always draws one), and one thing to do. -->
    <div v-else class="oui-job" :data-stale="stale || undefined"><div class="oui-job-block u1-job-rest" :data-ended="ended || undefined">
      <div class="oui-job-thumb"><PrinterFigure :stale="stale" /></div>
      <div class="u1-job-main"><div class="oui-job-id">
        <div class="oui-job-status">
          <OuiStatus v-if="stale" state="stale">{{ lastKnown }}</OuiStatus>
          <OuiStatus v-else :state="chip" data-test="state">{{ stateName }}</OuiStatus>
        </div>
        <template v-if="ended">
          <p class="oui-job-name" :title="st.filename" data-test="job-name">{{ st.filename }}</p>
          <p v-if="state === 'error' && st.message" class="u1-job-error" data-test="job-error">{{ st.message }}</p>
          <p v-else-if="detail && stale" class="oui-job-detail oui-truncate">{{ detail }}</p>
        </template>
        <template v-else>
          <p class="oui-job-name" data-test="job-name">{{ machine || t('status.ready') }}</p>
          <p v-if="stale || st.message" class="oui-job-detail oui-truncate">{{ [stale ? stateName : '', st.message].filter(Boolean).join(' · ') }}</p>
        </template>
      </div>
      <div v-if="ended" class="oui-job-stats">
        <OuiReadout :icon="clock" :label="t('status.took')" :value="st.total_duration ? fmt.duration(st.total_duration) : null" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
        <OuiReadout :icon="layers" :label="t('status.layers')" :value="layersDone" size="sm" :stale="stale" :unknown-label="t('common.unknown')" />
      </div></div>
      <div class="oui-job-actions">
        <Button v-if="ended" severity="secondary" :label="t('act.printAgain')" :disabled="!!againWhy" :aria-describedby="guidedWhy ? 'heads-why' : undefined" :loading="tracker.isBusy('print')" data-focus-key="print-again" data-test="print-again" @click="again">
          <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
        <Button v-else severity="secondary" :label="t('status.chooseFile')" data-focus-key="choose-file" data-test="choose-file" @click="s.tab = 'files'">
          <template #icon><OuiIcon :icon="files" :size="14" /></template></Button>
      </div>
    </div></div>
  </OuiPanel>
</template>

<style>
/* The printer photo in the job's 72 px picture box: as high as the box allows, never sized by the photo. */
.oui-job-thumb > .pf { width: auto; height: 64px; }
/* A running print in a card of middling width (five columns of a 1400 px window): Pause and Cancel go beside the file
   name, one over the other, so the block is three bands (name, bar, times) and not four. */
@container oui-job (min-width: 420px) and (max-width: 639.98px) {
  .u1-job .oui-job > .oui-job-block[data-thumb] { grid-template-columns: auto minmax(0, 1fr) auto; }
  .u1-job .oui-job > .oui-job-block[data-thumb] > .oui-job-actions { grid-column: 3; grid-row: 1; flex-direction: column; align-items: stretch; }
}
/* Not printing: the picture, what it is (and, for a print that ended, what it took), and the one action at the right;
   the action goes under the text when the card is narrow. */
.u1-job .oui-job > .oui-job-block.u1-job-rest { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s3) var(--oui-s4); }
.u1-job-main { flex: 1 1 200px; display: grid; gap: var(--oui-s2); min-width: 0; }
.u1-job-rest > .oui-job-actions { flex: none; margin-inline-start: auto; }
/* A failed print: what the printer said, whole (two lines before an ellipsis), in the error colour. */
.u1-job-error { font-size: var(--oui-text-sm); font-weight: 600; color: var(--oui-danger); overflow: hidden; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }
.u1-job-skel { display: grid; grid-template-columns: 72px minmax(0, 1fr); align-items: center; gap: var(--oui-s4); }
.u1-job-skel > .oui-skeleton { height: 72px; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(1) { width: 30%; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(2) { width: 60%; }
.u1-job-skel > .oui-stack > .oui-skeleton:nth-child(3) { height: 8px; }
</style>
