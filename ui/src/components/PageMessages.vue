<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiIcon } from '../../shared/src/components';
import { refresh, settings } from '../../shared/src/icons';
import { s, tracker, hello, printerName, statusAge, controlsOff, busy, STALE_STATUS_S } from '../app/store';
import { t, fmt } from '../core/i18n';
import { split } from '../core/tracker';
import { since } from '../core/since';

// What the whole page has to say, once, under the app bar on every tab: why the printer's controls are off (no
// printer, offline, still connecting, busy) and which commands are still waiting for an answer. What a command
// answered is a toast (App.vue's OuiToastHost). Controls that are off for one of these reasons point at it
// (#heads-why) instead of repeating it.
// Every banner can be closed; its dismissKey names the moment its condition started (since()), so a closed banner
// stays closed through every poll and comes back the next time the printer goes offline, gets busy, and so on.
// Live regions are the persistent wrappers below (polite, assertive, status): they are in the page before anything
// is added, so additions are announced. Each banner inside drops its own role (role="none") so nothing is announced
// twice.
// foundation-gap: OuiBanner (4.2.0) still always sets role alert/status; it should take `live: false` (and use
// role="note" for static banners itself). Until then the role is overridden here and on static banners (role="note").
const offline = computed(() => s.phase === 'unreachable' || !!s.offline);
const firstRun = computed(() => s.phase === 'noTarget' && s.tab === 'dash');   // the Dashboard says it itself, with the way out
const waiting = computed(() => [...tracker.pending.values()].filter(p => p.key !== 'spools'));
const at = {
  offline: since(() => offline.value), none: since(() => s.phase === 'noTarget'), connecting: since(() => s.phase === 'connecting'),
  noStatus: since(() => s.phase === 'connected' && !s.status), stale: since(() => !!s.status && statusAge.value > STALE_STATUS_S),
  busy: since(() => !controlsOff.value && busy.value),
};
const close = computed(() => t('common.close'));
</script>
<template>
  <div class="u1-top">
    <!-- Why the controls are off. Offline and unreachable are announced at once (assertive), as before 0.9.0; the
         other reasons politely. Both regions stay in the page so what appears in them is announced. -->
    <div class="u1-live" aria-live="assertive" data-test="target-alert">
      <OuiBanner v-if="offline" id="heads-why" role="none" data-test="heads-why" tone="error" dismissible :dismiss-key="`offline:${at.offline.value}`" :close-label="close" :title="t('target.offline.title')">
        {{ t('target.offline.body', { printer: printerName, error: s.offline || s.error }) }}
        <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
      </OuiBanner>
    </div>
    <div class="u1-live" aria-live="polite" :data-test="firstRun ? undefined : 'target-banner'">
      <OuiBanner v-if="s.phase === 'noTarget' && !firstRun" id="heads-why" role="none" tone="warn" dismissible :dismiss-key="`no-target:${at.none.value}`" :close-label="close" :title="t('target.none.title')">
        {{ t('target.none.body') }}
        <template #actions>
          <Button v-if="s.tab !== 'settings'" size="small" severity="secondary" :label="t('common.openSettings')" @click="s.tab = 'settings'"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiBanner>
      <template v-else-if="!offline">
        <OuiBanner v-if="s.phase === 'connecting'" id="heads-why" role="none" tone="neutral" :title="t('target.connecting')"
                   dismissible :dismiss-key="`connecting:${at.connecting.value}`" :close-label="close" />
        <OuiBanner v-else-if="s.phase === 'connected' && !s.status" id="heads-why" role="none" tone="neutral" :title="t('reason.waiting')"
                   dismissible :dismiss-key="`no-status:${at.noStatus.value}`" :close-label="close" />
        <!-- The age ticks every second: it is kept out of the announcement (the app bar's state says it too). -->
        <OuiBanner v-else-if="s.status && statusAge > STALE_STATUS_S" role="none" tone="warn" :title="t('target.staleTitle')" data-test="stale"
                   dismissible :dismiss-key="`stale:${at.stale.value}`" :close-label="close">
          <span class="u1-stale-age" aria-hidden="true">{{ t('target.staleAge', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }) }}</span></OuiBanner>
        <OuiBanner v-if="!controlsOff && busy" id="heads-why" role="none" data-test="heads-why" tone="info" dismissible :dismiss-key="`busy:${at.busy.value}`" :close-label="close" :title="t('reason.busy') + t('common.period')">{{ t('busy.body') }}</OuiBanner>
      </template>
    </div>
    <section class="notices" :aria-label="t('msg.region')">
      <!-- Commands still waiting for the printer; what they answer is a toast. -->
      <div role="status" aria-live="polite" class="u1-live">
        <OuiBanner v-for="p in waiting" :key="'p-' + p.key" role="none" tone="neutral" :title="split(t('msg.waiting', { action: p.label }))[0]"
                   dismissible :dismiss-key="`waiting:${p.key}:${p.startedAt}`" :close-label="close">{{ split(t('msg.waiting', { action: p.label }))[1] }}</OuiBanner>
      </div>
    </section>
  </div>
</template>
