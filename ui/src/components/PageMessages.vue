<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiIcon } from '../../shared/src/components';
import { refresh, settings, x } from '../../shared/src/icons';
import { s, tracker, hello, printerName, statusAge, controlsOff, busy, STALE_STATUS_S } from '../app/store';
import { t, fmt } from '../core/i18n';

// What the whole page has to say, once, under the app bar on every tab: why the printer's controls are off (no
// printer, offline, still connecting, busy) and what each command answered. Controls that are off for one of
// these reasons point at it (#heads-why) instead of repeating it.
const firstRun = computed(() => s.phase === 'noTarget' && s.tab === 'dash');   // the Dashboard says it itself, with the way out
const TONE = { error: 'error', unknown: 'warn', success: 'success', info: 'info' } as const;
const lasting = computed(() => tracker.notices.filter(n => n.kind === 'error' || n.kind === 'unknown'));
const passing = computed(() => tracker.notices.filter(n => n.kind === 'success' || n.kind === 'info'));
const waiting = computed(() => [...tracker.pending.values()].filter(p => p.key !== 'spools'));
/** "Pause failed: timeout" reads as a title and its detail. */
const split = (text: string) => { const i = text.indexOf(': '); return i < 0 ? [text, ''] : [text.slice(0, i + 1), text.slice(i + 2)]; };
</script>
<template>
  <div class="u1-top">
    <div class="u1-live" aria-live="polite" :data-test="firstRun ? undefined : 'target-banner'">
      <OuiBanner v-if="s.phase === 'noTarget' && !firstRun" id="heads-why" tone="warn" :title="t('target.none.title')">
        {{ t('target.none.body') }}
        <template #actions>
          <Button v-if="s.tab !== 'settings'" size="small" severity="secondary" :label="t('common.openSettings')" @click="s.tab = 'settings'"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiBanner>
      <OuiBanner v-else-if="s.phase === 'unreachable' || s.offline" id="heads-why" data-test="heads-why" tone="error" :title="t('target.offline.title')">
        {{ t('target.offline.body', { printer: printerName, error: s.offline || s.error }) }}
        <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
      </OuiBanner>
      <OuiBanner v-else-if="s.phase === 'connecting'" id="heads-why" tone="neutral" :title="t('target.connecting')" />
      <OuiBanner v-else-if="s.phase === 'connected' && !s.status" id="heads-why" tone="neutral" :title="t('reason.waiting')" />
      <OuiBanner v-else-if="s.status && statusAge > STALE_STATUS_S" tone="warn" :title="t('target.stale', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) })" />
    </div>
    <OuiBanner v-if="!controlsOff && busy" id="heads-why" data-test="heads-why" tone="info" :title="t('reason.busy') + '.'">{{ t('busy.body') }}</OuiBanner>

    <section class="notices" :aria-label="t('msg.region')">
      <!-- Errors and unknown outcomes stay until dismissed and are announced at once. -->
      <div role="alert" class="u1-live">
        <OuiBanner v-for="n in lasting" :key="n.id" :tone="TONE[n.kind]" :title="split(n.text)[0]">
          {{ split(n.text)[1] }} <span class="oui-meta">{{ fmt.time(n.at / 1000) }}</span>
          <template #actions><Button text severity="secondary" size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)"><template #icon><OuiIcon :icon="x" :size="14" /></template></Button></template>
        </OuiBanner>
      </div>
      <div role="status" aria-live="polite" class="u1-live">
        <OuiBanner v-for="p in waiting" :key="'p-' + p.key" tone="neutral" :title="split(t('msg.waiting', { action: p.label }))[0]">{{ split(t('msg.waiting', { action: p.label }))[1] }}</OuiBanner>
        <OuiBanner v-for="n in passing" :key="n.id" :tone="TONE[n.kind]" :title="split(n.text)[0]">
          {{ split(n.text)[1] }}
          <template #actions><Button text severity="secondary" size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)"><template #icon><OuiIcon :icon="x" :size="14" /></template></Button></template>
        </OuiBanner>
      </div>
    </section>
  </div>
</template>
