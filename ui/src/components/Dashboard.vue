<script setup lang="ts">
// The Dashboard, in the family's one order: page header (the printer, its address and firmware), the page's banners,
// the status block, then what you work on (toolheads, controls) beside what you watch (camera, printer screen).
// The spool stock is its own tab (StockView).
import { computed, markRaw, ref, watch } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiDashboard, OuiEmpty, OuiHint, OuiIcon, OuiPageHeader, OuiPanel, validateLayout, replaceRetired, type OuiDashboardLabels, type OuiWidget } from '@orca-plugins/ui-foundation/src/components';
import { ace, camera, check, files, fan, hand, play, printer, refresh, settings, terminal, thermometer, toolhead, trash, zap } from '@orca-plugins/ui-foundation/src/icons';
import JobCard from './JobCard.vue';
import ControlsCard from './ControlsCard.vue';
import TempsFansCard from './TempsFansCard.vue';
import CameraCard from './CameraCard.vue';
import ScreenCard from './ScreenCard.vue';
import ToolheadsCard from './ToolheadsCard.vue';
import ConsoleCard from './ConsoleCard.vue';
import FilesCard from './FilesCard.vue';
import AceCard from './AceCard.vue';
import UsageCard from './UsageCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import { s, openSettings, run, hello, controlsOff, printerName, fwText, stale, syncProject, lease } from '../app/store';
import { exceptionParts, reprintParts } from '../core/logic';
import { config } from '../app/settings';
import { CAMERA_FPS } from '../app/camera';
import * as bridge from '../core/bridge';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import firstRunArt from '../assets/u1-toolheads.webp';

// The modules are widgets the user arranges (OuiDashboard): sizes in columns of 12 and 32 px rows. The default is the
// family's dashboard order: the status across the top, what you work on (toolheads, controls) beside what you watch.
const n = (v: number) => ({ value: v, label: String(v) });
/** Rows on the default, in five columns: what a running print takes in the status block, and the four toolhead cards. */
const JOB_H = 4, HEADS_H = 21;
// A widget that is not `fill` is at least as tall as its content: its rows grow to fit it at any window width, so its
// least height only keeps it from being dragged to nothing. The camera, the screen and the console fill what they get.
const widgets = computed<OuiWidget[]>(() => [
  { id: 'job', narrowOrder: 1, title: t('status.title'), icon: printer, component: markRaw(JobCard), w: 5, h: JOB_H, minW: 4, minH: 2 },
  { id: 'heads', narrowOrder: 2, title: t('heads.title'), icon: toolhead, component: markRaw(ToolheadsCard), w: 5, h: HEADS_H, minW: 5, minH: 4 },
  { id: 'temps', narrowOrder: 4, title: t('tf.title'), icon: fan, component: markRaw(TempsFansCard), w: 3, h: 8, minW: 3, minH: 3,
    settings: [{ key: 'chamber', label: t('tf.chamber'), default: true }, { key: 'drivers', label: t('widget.drivers'), default: true }, { key: 'fans', label: t('tf.fans'), default: true }] },
  { id: 'controls', narrowOrder: 3, title: t('controls.title'), icon: thermometer, component: markRaw(ControlsCard), w: 4, h: 8, minW: 4, minH: 3 },
  { id: 'camera', narrowOrder: 5, title: t('cam.title'), icon: camera, component: markRaw(CameraCard), w: 4, h: 7, minW: 3, minH: 4,
    settings: [{ key: 'aspect', label: t('widget.aspect'), default: '16/9', options: [{ value: '16/9', label: '16:9' }, { value: '4/3', label: '4:3' }, { value: '1/1', label: '1:1' }] },
      { key: 'fps', label: t('cam.fps'), default: config.value?.settings.camera_fps ?? 5, options: CAMERA_FPS.map(v => ({ value: v, label: t('cam.fpsOption', { n: v }) })) }] },
  { id: 'console', narrowOrder: 7, title: t('console.title'), icon: terminal, component: markRaw(ConsoleCard), w: 7, h: 10, minW: 3, minH: 5, fill: true,
    settings: [{ key: 'lines', label: t('widget.lines'), default: 400, options: [100, 400, 1000].map(n) }] },
  { id: 'screen', narrowOrder: 6, title: t('scr.title'), icon: hand, component: markRaw(ScreenCard), w: 3, h: 7, minW: 3, minH: 4, fill: true },
  { id: 'files', title: t('nav.files'), icon: files, component: markRaw(FilesCard), w: 4, h: 3, minW: 3, minH: 3 },
  { id: 'ace', title: t('ace.title'), icon: ace, component: markRaw(AceCard), w: 6, h: 4, minW: 3, minH: 3 },
]);
// The default gives every widget the rows its content takes, so none stretches its neighbours: the print over the
// toolheads on the left; temperatures and controls, then the camera (16:9, the wider cell) and the printer screen
// (3:2) on the right. The G-code console is an expert's tool: it is on the default only in Expert mode (it stays in
// the catalogue), and its rows go to the camera and the screen otherwise. The filament units (multiACE) join under
// the toolheads only when multiACE runs, so a Default never arranged gets them and nothing else moves.
const expert = computed(() => config.value?.mode === 'expert');
const defaults = computed(() => ({ name: t('layout.default'), items: [
  { id: 'job', x: 0, y: 0, w: 5, h: JOB_H }, { id: 'heads', x: 0, y: JOB_H, w: 5, h: HEADS_H },
  { id: 'temps', x: 5, y: 0, w: 3, h: 8 }, { id: 'controls', x: 8, y: 0, w: 4, h: 8 },
  ...(expert.value ? [{ id: 'camera', x: 5, y: 8, w: 4, h: 7 }, { id: 'screen', x: 9, y: 8, w: 3, h: 7 }, { id: 'console', x: 5, y: 15, w: 7, h: 10 }]
    : [{ id: 'camera', x: 5, y: 8, w: 7, h: 10 }, { id: 'screen', x: 5, y: 18, w: 4, h: 7 }]),
  ...(s.status?.ace ? [{ id: 'ace', x: 0, y: JOB_H + HEADS_H, w: 5, h: 6 }] : [])] }));
// Earlier defaults: a layout still exactly as one of them is given today's.
const RETIRED = [[{ id: 'job', x: 0, y: 0, w: 5, h: 4 }, { id: 'heads', x: 0, y: 4, w: 5, h: 14 }, { id: 'temps', x: 5, y: 0, w: 3, h: 7 }, { id: 'controls', x: 8, y: 0, w: 4, h: 7 },
  { id: 'camera', x: 5, y: 7, w: 3, h: 8 }, { id: 'screen', x: 8, y: 7, w: 4, h: 8 }, { id: 'console', x: 5, y: 15, w: 7, h: 6 }],
[{ id: 'job', x: 0, y: 0, w: 6, h: 2 }, { id: 'heads', x: 0, y: 2, w: 6, h: 14 }, { id: 'controls', x: 6, y: 0, w: 6, h: 4 },
  { id: 'temps', x: 6, y: 4, w: 3, h: 8 }, { id: 'camera', x: 9, y: 4, w: 3, h: 8 }, { id: 'screen', x: 6, y: 12, w: 6, h: 4 }, { id: 'console', x: 0, y: 16, w: 12, h: 6 }],[{ id: 'job', x: 0, y: 0, w: 12, h: 3 }, { id: 'heads', x: 0, y: 3, w: 12, h: 10 }, { id: 'controls', x: 0, y: 13, w: 8, h: 6 },
  { id: 'camera', x: 8, y: 13, w: 4, h: 6 }, { id: 'temps', x: 0, y: 19, w: 8, h: 7 }, { id: 'screen', x: 8, y: 19, w: 4, h: 7 }, { id: 'console', x: 0, y: 26, w: 12, h: 7 }],
[{ id: 'job', x: 0, y: 0, w: 12, h: 3 }, { id: 'heads', x: 0, y: 3, w: 12, h: 10 }, { id: 'temps', x: 0, y: 13, w: 8, h: 7 }, { id: 'camera', x: 8, y: 13, w: 4, h: 7 },
  { id: 'controls', x: 0, y: 20, w: 8, h: 6 }, { id: 'screen', x: 8, y: 20, w: 4, h: 6 }, { id: 'console', x: 0, y: 26, w: 12, h: 6 }]];
const labels = computed<OuiDashboardLabels>(() => ({
  toolbar: t('layout.toolbar'), layout: t('layout.layout'), edit: t('layout.edit'), save: t('layout.save'), cancel: t('layout.cancel'), add: t('layout.add'),
  addTitle: t('layout.addTitle'), added: t('layout.added'), close: t('layout.close'), newLayout: t('layout.new'), rename: t('layout.rename'), remove: t('layout.remove'),
  reset: t('layout.reset'), create: t('layout.create'), apply: t('layout.apply'), keep: t('layout.keep'), removeAsk: name => t('layout.removeAsk', { name }),
  nameEmpty: t('layout.nameEmpty'), nameTaken: t('layout.nameTaken'), settings: widget => t('layout.settings', { widget }), removeWidget: widget => t('layout.removeWidget', { widget }),
  widget: widget => t('layout.widget', { widget }), place: (widget, x, y, w, h) => t('layout.place', { widget, x, y, w, h }), removed: widget => t('layout.removed', { widget }),
  hint: t('layout.hint'), narrow: t('layout.narrow'), empty: t('layout.empty'), maximize: t('layout.maximize'), restore: t('layout.restore'),
}));
// Stored with the plugin's settings (settings "dashboard"); what the user saved here wins over a config that is older.
const saved = ref<unknown>(undefined);
const layout = computed({
  get: () => replaceRetired(saved.value !== undefined ? saved.value : config.value?.settings.dashboard, RETIRED, defaults.value.items),
  set: (v: unknown) => { saved.value = v; bridge.post({ type: 'dashboard', value: v }); },
});
// The camera and the screen are streamed only while their widget is on the open layout.
watch(() => { const st = validateLayout(layout.value, widgets.value, defaults.value); return st.layouts[st.active].items.map(i => i.id).join(); },
  ids => { s.widgets = ids.split(','); lease(); }, { immediate: true });

const st = computed(() => s.status);
// What the printer reports is said in words: its own short text and code, never the record it sent.
const exceptions = computed(() => [...new Set((st.value?.exceptions ?? []).map(x => {
  const { name, code } = exceptionParts(x);
  return name && code ? t('exceptions.named', { text: name, code }) : name || (code ? t('exceptions.code', { code }) : t('exceptions.unnamed'));
}))]);
const interrupted = computed(() => {
  const { file, layer } = reprintParts(st.value?.reprint);
  return file && layer != null ? t('power.at', { file, layer }) : file ? t('power.file', { file }) : layer != null ? t('power.layer', { layer }) : '';
});
/** A printer that never answered has nothing to show: one panel says so, in place of a dashboard of empty cards. */
const unreachable = computed(() => s.phase === 'unreachable' && !s.status);
async function powerResume() {
  if (!await ask({ title: t('act.powerResume'), text: t('confirm.powerResume.text'), yes: t('confirm.powerResume.yes'), no: t('common.goBack') })) return;
  await run({ key: 'power', label: t('act.powerResume'), cmd: 'power_loss', args: { action: 'resume' }, okText: t('ok.powerResume'), timeoutMs: 60000 });
}
async function powerDiscard() {
  if (!await ask({ title: t('act.powerDiscard'), text: t('confirm.powerDiscard.text'), yes: t('confirm.powerDiscard.yes'), no: t('common.goBack'), danger: true })) return;
  await run({ key: 'power', label: t('act.powerDiscard'), cmd: 'power_loss', args: { action: 'discard' }, okText: t('ok.powerDiscard') });
}
</script>
<template>
  <div class="u1-head">
  <OuiPageHeader v-if="s.phase !== 'noTarget'" :title="printerName">
    <template #meta>
      <span v-if="s.phase === 'connecting'" class="oui-skeleton u1-head-skel" :aria-label="fwText" />
      <span v-else :class="{ 'u1-stale': stale }"><template v-if="s.info">{{ s.info.address }} · </template><span data-test="firmware">{{ fwText }}</span></span>
    </template>
    <template #actions>
      <OuiHint id="sync-help" end :label="t('heads.syncAbout')" :text="t('heads.syncHelp')" />
      <Button severity="secondary" :label="t('heads.sync')" :loading="s.syncing" :disabled="!!controlsOff || s.syncing" data-focus-key="sync" data-test="sync" :aria-describedby="controlsOff ? 'heads-why' : 'sync-help'" @click="syncProject">
        <template #icon><OuiIcon :icon="check" :size="14" /></template></Button>
    </template>
  </OuiPageHeader>
  <!-- Always in the page, whatever is shown around it: the page's banners are moved here (App.vue). -->
  <div id="u1-banner-dash" />
  </div>
  <OuiBanner :show="!!exceptions.length" tone="error" :title="t('exceptions.title')" dismissible :dismiss-key="`exceptions:${exceptions.join('|')}`" :close-label="t('common.close')" data-test="exceptions">
    <ul class="u1-plain-list"><li v-for="e in exceptions" :key="e">{{ e }}</li></ul></OuiBanner>
  <!-- Not dismissible: it holds the only Resume and Discard controls. -->
  <OuiBanner v-if="st?.power_loss" role="note" tone="warn" :icon="zap" :title="t('power.title')" data-test="power-loss">
    <template v-if="interrupted">{{ interrupted }}</template>
    <template #actions>
      <Button size="small" severity="secondary" :label="t('power.resume')" :disabled="!!controlsOff" :aria-describedby="controlsOff ? 'heads-why' : undefined" data-focus-key="pl-resume" @click="powerResume">
        <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
      <Button size="small" severity="danger" outlined :label="t('power.discard')" :disabled="!!controlsOff" :aria-describedby="controlsOff ? 'heads-why' : undefined" data-focus-key="pl-discard" @click="powerDiscard">
        <template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
    </template>
  </OuiBanner>
  <UsageCard />
  <!-- No printer chosen yet: one thing to do, and nothing else on the page. -->
  <template v-if="s.phase === 'noTarget'">
    <OuiPanel :id="s.tab === 'dash' ? 'heads-why' : undefined" class="u1-first" flush role="status" :data-test="s.tab === 'dash' ? 'target-banner' : undefined">
      <OuiEmpty :image="firstRunArt" :title="t('target.none.title')" :text="t('target.none.body')">
        <template #actions>
          <Button :label="t('common.openSettings')" @click="openSettings('connection')"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiEmpty>
    </OuiPanel>
    <SpoolerHint />
  </template>
  <!-- A printer that never answered: the same single panel, with what to do. The reason the controls point at. -->
  <OuiPanel v-else-if="unreachable" :id="s.tab === 'dash' ? 'heads-why' : undefined" class="u1-first" flush role="alert" data-test="unreachable">
    <OuiEmpty state="offline" :title="t('target.offline.title')" :text="t('target.offline.body', { printer: printerName, error: s.error })">
      <template #actions>
        <Button :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        <Button severity="secondary" :label="t('common.openSettings')" @click="openSettings('connection')"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
      </template>
    </OuiEmpty>
  </OuiPanel>
  <template v-else>
    <SpoolerHint />
    <OuiDashboard v-model="layout" :widgets="widgets" :defaults="defaults" :labels="labels" :narrow-at="1000" />
  </template>
</template>
<style>
.u1-first { justify-self: center; width: min(100%, 560px); margin-top: var(--oui-s8); }
.u1-first .oui-empty { padding-block: var(--oui-s8); }
.u1-first .oui-empty-image { width: 176px; height: 176px; }
.u1-plain-list { margin: 0; padding: 0; list-style: none; }
.u1-head-skel { display: inline-block; width: 220px; vertical-align: middle; }
/* Last known address and firmware of a printer the page no longer hears from. */
.u1-stale { opacity: .75; }
</style>
