<script setup lang="ts">
// The Dashboard, in the family's one order: page header (the printer, its address and firmware), the page's banners,
// the status block, then what you work on (toolheads, controls) beside what you watch (camera, printer screen).
// The spool stock is its own tab (StockView).
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiEmpty, OuiHint, OuiIcon, OuiPageHeader, OuiPanel } from '../../shared/src/components';
import { check, play, refresh, settings, trash, zap } from '../../shared/src/icons';
import JobCard from './JobCard.vue';
import ControlsCard from './ControlsCard.vue';
import CameraCard from './CameraCard.vue';
import ScreenCard from './ScreenCard.vue';
import ToolheadsCard from './ToolheadsCard.vue';
import UsageCard from './UsageCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import * as bridge from '../core/bridge';
import { s, openSettings, run, hello, controlsOff, printerName, fwText, stale } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import firstRunArt from '../assets/u1-toolheads.webp';

const st = computed(() => s.status);
const exceptions = computed(() => (st.value?.exceptions ?? []).map(x => JSON.stringify(x)).join('\n'));
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
      <Button severity="secondary" :label="t('heads.sync')" :disabled="!!controlsOff" data-focus-key="sync" data-test="sync" :aria-describedby="controlsOff ? 'heads-why' : 'sync-help'" @click="bridge.post({ type: 'sync_project' })">
        <template #icon><OuiIcon :icon="check" :size="14" /></template></Button>
    </template>
  </OuiPageHeader>
  <!-- Always in the page, whatever is shown around it: the page's banners are moved here (App.vue). -->
  <div id="u1-banner-dash" />
  </div>
  <OuiBanner :show="!!exceptions" tone="error" :title="t('exceptions.title')" dismissible :dismiss-key="`exceptions:${exceptions}`" :close-label="t('common.close')"><span class="oui-error-detail">{{ exceptions }}</span></OuiBanner>
  <!-- Not dismissible: it holds the only Resume and Discard controls. -->
  <OuiBanner v-if="st?.power_loss" role="note" tone="warn" :icon="zap" :title="t('power.title')" data-test="power-loss">
    <template v-if="st.reprint">{{ t('power.options', { options: JSON.stringify(st.reprint) }) }}</template>
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
      <template #footer><p class="oui-meta">{{ t('target.detail', { error: s.error }) }}</p></template>
    </OuiPanel>
    <SpoolerHint />
  </template>
  <template v-else>
    <SpoolerHint />
    <div class="oui-dash">
      <JobCard />
      <div class="oui-dash-main">
        <ToolheadsCard />
        <ControlsCard />
      </div>
      <div class="oui-dash-side">
        <CameraCard />
        <ScreenCard />
      </div>
    </div>
  </template>
</template>
<style>
.u1-first { justify-self: center; width: min(100%, 560px); margin-top: var(--oui-s8); }
.u1-first .oui-empty { padding-block: var(--oui-s8); }
.u1-first .oui-empty-image { width: 176px; height: 176px; }
.u1-head-skel { display: inline-block; width: 220px; vertical-align: middle; }
/* Last known address and firmware of a printer the page no longer hears from. */
.u1-stale { opacity: .75; }
</style>
