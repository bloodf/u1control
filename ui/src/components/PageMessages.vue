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
// Live regions are the persistent wrappers below (polite, alert, status): they are in the page before anything is
// added, so additions are announced. Each banner inside drops its own role (role="none") so nothing is announced twice.
// foundation-gap: OuiBanner (4.0.1) always sets role alert/status; 4.0.2 should add `live: false` (and use role="note"
// for static banners itself). Until then the role is overridden here and on static banners (role="note").
const offline = computed(() => s.phase === 'unreachable' || !!s.offline);
const firstRun = computed(() => s.phase === 'noTarget' && s.tab === 'dash');   // the Dashboard says it itself, with the way out
const TONE = { error: 'error', unknown: 'warn', success: 'success', info: 'info' } as const;
const lasting = computed(() => tracker.notices.filter(n => n.kind === 'error' || n.kind === 'unknown'));
const passing = computed(() => tracker.notices.filter(n => n.kind === 'success' || n.kind === 'info'));
const waiting = computed(() => [...tracker.pending.values()].filter(p => p.key !== 'spools'));
/** "Pause failed: timeout" reads as a title and its detail (Chinese writes the colon as "："). */
const split = (text: string) => { const m = /: |：/.exec(text); return m ? [text.slice(0, m.index + 1), text.slice(m.index + m[0].length)] : [text, '']; };
</script>
<template>
  <div class="u1-top">
    <!-- Why the controls are off. Offline and unreachable are announced at once (assertive), as before 0.9.0; the
         other reasons politely. Both regions stay in the page so what appears in them is announced. -->
    <div class="u1-live" aria-live="assertive" data-test="target-alert">
      <OuiBanner v-if="offline" id="heads-why" role="none" data-test="heads-why" tone="error" :title="t('target.offline.title')">
        {{ t('target.offline.body', { printer: printerName, error: s.offline || s.error }) }}
        <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
      </OuiBanner>
    </div>
    <div class="u1-live" aria-live="polite" :data-test="firstRun ? undefined : 'target-banner'">
      <OuiBanner v-if="s.phase === 'noTarget' && !firstRun" id="heads-why" role="none" tone="warn" :title="t('target.none.title')">
        {{ t('target.none.body') }}
        <template #actions>
          <Button v-if="s.tab !== 'settings'" size="small" severity="secondary" :label="t('common.openSettings')" @click="s.tab = 'settings'"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiBanner>
      <template v-else-if="!offline">
        <OuiBanner v-if="s.phase === 'connecting'" id="heads-why" role="none" tone="neutral" :title="t('target.connecting')" />
        <OuiBanner v-else-if="s.phase === 'connected' && !s.status" id="heads-why" role="none" tone="neutral" :title="t('reason.waiting')" />
        <!-- The age ticks every second: it is kept out of the announcement (the app bar's state says it too). -->
        <OuiBanner v-else-if="s.status && statusAge > STALE_STATUS_S" role="none" tone="warn" :title="t('target.staleTitle')" data-test="stale">
          <span class="u1-stale-age" aria-hidden="true">{{ t('target.staleAge', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }) }}</span></OuiBanner>
        <OuiBanner v-if="!controlsOff && busy" id="heads-why" role="none" data-test="heads-why" tone="info" :title="t('reason.busy') + t('common.stop')">{{ t('busy.body') }}</OuiBanner>
      </template>
    </div>
    <section class="notices" :aria-label="t('msg.region')">
      <!-- Errors and unknown outcomes stay until dismissed and are announced at once. -->
      <div role="alert" class="u1-live">
        <OuiBanner v-for="n in lasting" :key="n.id" role="none" :tone="TONE[n.kind]" :title="split(n.text)[0]">
          {{ split(n.text)[1] }} <span class="oui-meta">{{ fmt.time(n.at / 1000) }}</span>
          <template #actions><Button text severity="secondary" size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)"><template #icon><OuiIcon :icon="x" :size="14" /></template></Button></template>
        </OuiBanner>
      </div>
      <div role="status" aria-live="polite" class="u1-live">
        <OuiBanner v-for="p in waiting" :key="'p-' + p.key" role="none" tone="neutral" :title="split(t('msg.waiting', { action: p.label }))[0]">{{ split(t('msg.waiting', { action: p.label }))[1] }}</OuiBanner>
        <OuiBanner v-for="n in passing" :key="n.id" role="none" :tone="TONE[n.kind]" :title="split(n.text)[0]">
          {{ split(n.text)[1] }}
          <template #actions><Button text severity="secondary" size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)"><template #icon><OuiIcon :icon="x" :size="14" /></template></Button></template>
        </OuiBanner>
      </div>
    </section>
  </div>
</template>
