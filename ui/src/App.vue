<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue';
import Button from 'primevue/button';
import { OuiAppBar, OuiIcon, OuiStatus, OuiToastHost, type OuiState } from '../shared/src/components';
import { dashboard, files, power, settings, terminal } from '../shared/src/icons';
import ConfirmDialog from './components/ConfirmDialog.vue';
import PageMessages from './components/PageMessages.vue';
import Dashboard from './components/Dashboard.vue';
import FilesView from './components/FilesView.vue';
import ConsoleView from './components/ConsoleView.vue';
import SettingsView from './components/SettingsView.vue';
import { s, start, lease, estop, estopReason, controlsOff, busy, stale, statusAge, STALE_STATUS_S } from './app/store';
import { installSettings } from './app/settings';
import { t, tMaybe, fmt } from './core/i18n';

const stop = start();
const stopSettings = installSettings();
onBeforeUnmount(stopSettings);
onBeforeUnmount(stop);
watch(() => s.tab, () => lease());

const fwText = computed(() => {
  if (s.phase === 'connecting') return t('fw.connecting');
  if (!s.info) return t('fw.none');
  const v = s.info.firmware.version ?? '';
  return s.info.firmware.kind === 'extended' ? t('fw.extended', { version: v })
    : s.info.firmware.kind === 'stock' ? t('fw.stock', { version: v }) : t('fw.unknown');
});
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
  { value: 'files', icon: files, label: t('nav.files') },
  { value: 'console', icon: terminal, label: t('nav.console') },
  { value: 'settings', icon: settings, label: t('nav.settings') },
]);
const VIEWS = [['dash', Dashboard], ['files', FilesView], ['console', ConsoleView]] as const;
</script>

<template>
  <OuiAppBar v-model="s.tab" :name="t('app.brand')" :tabs="tabs" :tabs-label="t('nav.label')">
    <template #mark>
      <svg viewBox="0 0 256 256" fill="currentColor"><path d="M40 96H72V160A32 32 0 0 0 104 192H152A32 32 0 0 0 184 160V96H216V160A64 64 0 0 1 152 224H104A64 64 0 0 1 40 160Z" /><rect x="40" y="40" width="32" height="64" rx="8" /><rect x="88" y="40" width="32" height="64" rx="8" /><rect x="136" y="40" width="32" height="64" rx="8" /><rect x="184" y="40" width="32" height="64" rx="8" /></svg>
    </template>
    <template #status>
      <OuiStatus :state="state.state" data-test="conn-state">{{ state.label }}</OuiStatus>
      <span v-if="s.info" class="oui-truncate" :title="`${s.info.printer} · ${s.info.address} · ${fwText}`" :class="{ 'u1-bar-stale': stale }">{{ s.info.printer }} · {{ s.info.address }} · <span data-test="firmware">{{ fwText }}</span></span>
    </template>
    <!-- Emergency stop: one press away on every tab, apart from every other control, with its own rule (a known
         printer, even one that is offline or late). It always asks first. -->
    <template v-if="s.phase !== 'noTarget'" #actions>
      <Button severity="danger" size="small" :label="t('act.estop')" :disabled="!!estopReason" :aria-describedby="estopReason && controlsOff ? 'heads-why' : undefined"
              data-focus-key="estop" data-test="estop" @click="estop"><template #icon><OuiIcon :icon="power" :size="14" /></template></Button>
    </template>
  </OuiAppBar>

  <PageMessages />
  <main v-for="[name, view] in VIEWS" v-show="s.tab === name" :key="name" class="oui-page" role="tabpanel" :aria-labelledby="'oui-tab-' + name">
    <component :is="view" />
  </main>
  <main v-show="s.tab === 'settings'" role="tabpanel" aria-labelledby="oui-tab-settings"><SettingsView /></main>
  <ConfirmDialog />
  <OuiToastHost :close-label="t('common.close')" :label="t('msg.region')" />
</template>

<style>
.u1-bar-stale { opacity: .75; }
</style>
