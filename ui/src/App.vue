<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue';
import Button from 'primevue/button';
import { OuiAppBar, OuiIcon, OuiStatus, OuiToastHost, type OuiState } from '@orca-plugins/ui-foundation/src/components';
import { dashboard, files, power, settings, spool } from '@orca-plugins/ui-foundation/src/icons';
import ConfirmDialog from './components/ConfirmDialog.vue';
import PageMessages from './components/PageMessages.vue';
import Dashboard from './components/Dashboard.vue';
import StockView from './components/StockView.vue';
import FilesView from './components/FilesView.vue';
import SettingsView from './components/SettingsView.vue';
import { s, start, lease, estop, estopReason, controlsOff, busy, statusAge, stockCount, STALE_STATUS_S } from './app/store';
import { installSettings } from './app/settings';
import { t, tMaybe, fmt } from './core/i18n';

const stop = start();
const stopSettings = installSettings();
onBeforeUnmount(stopSettings);
onBeforeUnmount(stop);
watch(() => s.tab, () => lease());

// The page's one connection state. What the printer is doing is only said while the page still hears from it.
const state = computed<{ state: OuiState; label: string }>(() => {
  if (s.phase === 'noTarget') return { state: 'idle', label: t('bar.none') };
  if (s.phase === 'unreachable' || s.offline) return { state: 'offline', label: t('status.state.offline') };
  if (s.phase === 'connecting' || !s.status) return { state: 'connecting', label: t('fw.connecting') };
  if (statusAge.value > STALE_STATUS_S) return { state: 'stale', label: t('bar.lastKnown', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }) };
  const name = s.status.state;
  const label = tMaybe(`status.state.${name}`, name);
  if (name === 'error') return { state: 'error', label };
  if (name === 'printing') return { state: 'busy', label };
  if (name === 'paused') return { state: 'pending', label };
  return busy.value ? { state: 'busy', label: t('bar.busy') } : { state: 'ok', label };
});
const tabs = computed(() => [
  { value: 'dash', icon: dashboard, label: t('nav.dash') },
  { value: 'stock', icon: spool, label: t('nav.stock'), ...(stockCount.value == null ? {} : { count: stockCount.value }) },
  { value: 'files', icon: files, label: t('nav.files') },
  { value: 'settings', icon: settings, label: t('nav.settings') },
]);
const VIEWS = [['dash', Dashboard], ['stock', StockView], ['files', FilesView]] as const;
</script>

<template>
  <OuiAppBar v-model="s.tab" :name="t('app.brand')" :tabs="tabs" :tabs-label="t('nav.label')">
    <template #mark>
      <svg viewBox="0 0 256 256" fill="currentColor"><path d="M40 96H72V160A32 32 0 0 0 104 192H152A32 32 0 0 0 184 160V96H216V160A64 64 0 0 1 152 224H104A64 64 0 0 1 40 160Z" /><rect x="40" y="40" width="32" height="64" rx="8" /><rect x="88" y="40" width="32" height="64" rx="8" /><rect x="136" y="40" width="32" height="64" rx="8" /><rect x="184" y="40" width="32" height="64" rx="8" /></svg>
    </template>
    <!-- The page's one state. The printer's name, address and firmware are the Dashboard's page header. -->
    <template #status><OuiStatus :state="state.state" data-test="conn-state">{{ state.label }}</OuiStatus></template>
    <!-- Emergency stop: one press away on every tab, apart from every other control, with its own rule (a known
         printer, even one that is offline or late). It always asks first. -->
    <template v-if="s.phase !== 'noTarget'" #actions>
      <Button severity="danger" size="small" :label="t('act.estop')" :disabled="!!estopReason" :aria-describedby="estopReason && controlsOff ? 'heads-why' : undefined"
              data-focus-key="estop" data-test="estop" @click="estop"><template #icon><OuiIcon :icon="power" :size="14" /></template></Button>
    </template>
  </OuiAppBar>

  <!-- Every tab is the same four things in the same order: app bar, page header, the page's banners, content. Each view
       leaves a place for the banners under its header (#u1-banner-<tab>); the one PageMessages moves to the open tab's,
       so its live regions and what was dismissed stay as they are. -->
  <main v-for="[name, view] in VIEWS" v-show="s.tab === name" :key="name" class="oui-page" role="tabpanel" :aria-labelledby="'oui-tab-' + name">
    <component :is="view" />
  </main>
  <main v-show="s.tab === 'settings'" role="tabpanel" aria-labelledby="oui-tab-settings">
    <div id="u1-banner-settings" class="u1-head u1-head-settings" />
    <SettingsView />
  </main>
  <Teleport defer :to="'#u1-banner-' + s.tab"><PageMessages /></Teleport>
  <ConfirmDialog />
  <OuiToastHost :close-label="t('common.close')" :label="t('msg.region')" />
</template>
