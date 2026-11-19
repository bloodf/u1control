<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiIcon } from '../../shared/src/components';
import { refresh, settings } from '../../shared/src/icons';
import { s, openSettings, tracker, hello, printerName, statusAge, controlsOff, busy, STALE_STATUS_S } from '../app/store';
import { t, fmt } from '../core/i18n';
import { split } from '../core/tracker';

// What the whole page has to say, once, under the page header of the open tab (App.vue moves it there): why the printer's controls are off (no
// printer, offline, still connecting, busy) and which commands are still waiting for an answer. What a command
// answered is a toast (App.vue's OuiToastHost). Controls that are off for one of these reasons point at it
// (#heads-why) instead of repeating it.
// Every banner can be closed. Each is bound to its condition (`show`, never v-if) and keyed on the printer it is about,
// so a closed banner stays closed through every poll and a reload, and OuiBanner forgets the dismissal once the
// condition clears: it comes back the next time the printer goes offline, gets busy, and so on.
// Live regions are the persistent wrappers below (polite, assertive, status): they are in the page before anything
// is added, so additions are announced. Each banner inside drops its own role (role="none") so nothing is announced
// twice.
// foundation-gap: OuiBanner (5.0.0) still always sets role alert/status; it should take `live: false` (and use
// role="note" for static banners itself). Until then the role is overridden here and on static banners (role="note").
const offline = computed(() => s.phase === 'unreachable' || !!s.offline);
const firstRun = computed(() => s.phase === 'noTarget' && s.tab === 'dash');   // the Dashboard says it itself, with the way out
const waiting = computed(() => [...tracker.pending.values()].filter(p => p.key !== 'spools'));
const addr = computed(() => s.info?.address ?? '');
// One reason at a time, in this order (offline, no printer, connecting, no status yet, stale); busy can join stale.
const show = computed(() => ({
  offline: offline.value,
  none: s.phase === 'noTarget',
  connecting: !offline.value && s.phase === 'connecting',
  noStatus: !offline.value && s.phase === 'connected' && !s.status,
  stale: !offline.value && s.phase === 'connected' && !!s.status && statusAge.value > STALE_STATUS_S,
  busy: !controlsOff.value && busy.value,
}));
const close = computed(() => t('common.close'));
</script>
<template>
  <div class="u1-top">
    <!-- Why the controls are off. Offline and unreachable are announced at once (assertive), as before 0.9.0; the
         other reasons politely. Both regions stay in the page so what appears in them is announced. -->
    <div class="u1-live" aria-live="assertive" data-test="target-alert">
      <OuiBanner :show="show.offline" id="heads-why" role="none" data-test="heads-why" tone="error" dismissible :dismiss-key="`offline:${addr}`" :close-label="close" :title="t('target.offline.title')">
        {{ t('target.offline.body', { printer: printerName, error: s.offline || s.error }) }}
        <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
      </OuiBanner>
    </div>
    <div class="u1-live" aria-live="polite" :data-test="firstRun ? undefined : 'target-banner'">
      <!-- On the Dashboard's first run the Dashboard says it itself: hidden there, kept mounted so a dismissal holds. -->
      <OuiBanner :show="show.none" :id="firstRun ? undefined : 'heads-why'" :style="firstRun ? 'display: none' : undefined" role="none" tone="warn" dismissible dismiss-key="no-target" :close-label="close" :title="t('target.none.title')">
        {{ t('target.none.body') }}
        <template #actions>
          <Button v-if="s.tab !== 'settings'" size="small" severity="secondary" :label="t('common.openSettings')" @click="openSettings('connection')"><template #icon><OuiIcon :icon="settings" :size="14" /></template></Button>
          <Button size="small" severity="secondary" :label="t('common.retry')" @click="hello()"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
      </OuiBanner>
        <OuiBanner :show="show.connecting" id="heads-why" role="none" tone="neutral" :title="t('target.connecting')"
                   dismissible :dismiss-key="`connecting:${addr}`" :close-label="close" />
        <OuiBanner :show="show.noStatus" id="heads-why" role="none" tone="neutral" :title="t('reason.waiting')"
                   dismissible :dismiss-key="`no-status:${addr}`" :close-label="close" />
        <!-- The age ticks every second: it is kept out of the announcement (the app bar's state says it too). -->
        <OuiBanner :show="show.stale" role="none" tone="warn" :title="t('target.staleTitle')" data-test="stale"
                   dismissible :dismiss-key="`stale:${addr}`" :close-label="close">
          <span class="u1-stale-age" aria-hidden="true">{{ t('target.staleAge', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }) }}</span></OuiBanner>
        <OuiBanner :show="show.busy" id="heads-why" role="none" data-test="heads-why" tone="info" dismissible :dismiss-key="`busy:${addr}`" :close-label="close" :title="t('reason.busy') + t('common.period')">{{ t('busy.body') }}</OuiBanner>
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
