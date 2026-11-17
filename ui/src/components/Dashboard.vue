<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiEmpty, OuiIcon, OuiPanel } from '../../shared/src/components';
import { play, refresh, settings, trash, zap } from '../../shared/src/icons';
import JobCard from './JobCard.vue';
import BedCard from './BedCard.vue';
import CameraCard from './CameraCard.vue';
import ScreenCard from './ScreenCard.vue';
import ToolheadsCard from './ToolheadsCard.vue';
import StockCard from './StockCard.vue';
import UsageCard from './UsageCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import { s, run, hello, controlsOff } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import { since } from '../core/since';
import firstRunArt from '../assets/u1-toolheads.webp';

const st = computed(() => s.status);
const exceptions = computed(() => (st.value?.exceptions ?? []).map(x => JSON.stringify(x)).join('\n'));
const powerLoss = since(() => !!st.value?.power_loss);
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
  <OuiBanner v-if="exceptions" tone="error" :title="t('exceptions.title')" dismissible :dismiss-key="`exceptions:${exceptions}`" :close-label="t('common.close')"><span class="oui-error-detail">{{ exceptions }}</span></OuiBanner>
  <OuiBanner v-if="st?.power_loss" role="note" tone="warn" :icon="zap" :title="t('power.title')"
             dismissible :dismiss-key="`power-loss:${powerLoss}`" :close-label="t('common.close')">
    <template v-if="st.reprint">{{ t('power.options', { options: JSON.stringify(st.reprint) }) }}</template>
    <template #actions>
      <Button size="small" severity="secondary" :label="t('power.resume')" :disabled="!!controlsOff" :aria-describedby="controlsOff ? 'heads-why' : undefined" data-focus-key="pl-resume" @click="powerResume">
        <template #icon><OuiIcon :icon="play" :size="14" /></template></Button>
      <Button size="small" severity="danger" outlined :label="t('power.discard')" :disabled="!!controlsOff" :aria-describedby="controlsOff ? 'heads-why' : undefined" data-focus-key="pl-discard" @click="powerDiscard">
        <template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
    </template>
  </OuiBanner>
  <UsageCard />

  <!-- No printer chosen yet: one thing to do. Stock and unconfirmed filament use don't need a printer and stay. -->
  <template v-if="s.phase === 'noTarget'">
    <OuiPanel :id="s.tab === 'dash' ? 'heads-why' : undefined" class="u1-first" flush role="status" :data-test="s.tab === 'dash' ? 'target-banner' : undefined">
      <OuiEmpty :image="firstRunArt" :title="t('target.none.title')" :text="t('target.none.body')">
        <template #actions>
          <Button :label="t('common.openSettings')" @click="s.tab = 'settings'"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiEmpty>
      <template #footer><p class="oui-meta">{{ t('target.detail', { error: s.error }) }}</p></template>
    </OuiPanel>
    <SpoolerHint />
    <StockCard />
  </template>
  <div v-else class="u1-grid">
    <div class="oui-stack">
      <JobCard />
      <BedCard />
      <CameraCard />
      <ScreenCard v-if="s.info?.firmware.kind === 'extended'" />
    </div>
    <div class="oui-stack">
      <SpoolerHint />
      <ToolheadsCard />
      <StockCard />
    </div>
  </div>
</template>
<style>
.u1-first { justify-self: center; width: min(100%, 560px); margin-top: var(--oui-s8); }
.u1-first .oui-empty { padding-block: var(--oui-s8); }
.u1-first .oui-empty-image { width: 176px; height: 176px; }
</style>
