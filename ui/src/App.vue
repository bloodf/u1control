<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue';
import Tabs from 'primevue/tabs';
import TabList from 'primevue/tablist';
import Tab from 'primevue/tab';
import TabPanels from 'primevue/tabpanels';
import TabPanel from 'primevue/tabpanel';
import Icon from './components/Icon.vue';
import ConfirmDialog from './components/ConfirmDialog.vue';
import NoticeArea from './components/NoticeArea.vue';
import TargetBanner from './components/TargetBanner.vue';
import Dashboard from './components/Dashboard.vue';
import FilesView from './components/FilesView.vue';
import ConsoleView from './components/ConsoleView.vue';
import SettingsView from './components/SettingsView.vue';
import { s, start, lease } from './app/store';
import { installSettings } from './app/settings';
import { t } from './core/i18n';

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
const sections = [
  { value: 'dash', icon: 'icon/dashboard', label: 'nav.dash' },
  { value: 'files', icon: 'icon/files', label: 'nav.files' },
  { value: 'console', icon: 'icon/terminal', label: 'nav.console' },
  { value: 'settings', icon: 'icon/settings', label: 'nav.settings' },
] as const;
</script>

<template>
  <Tabs v-model:value="s.tab" class="u1-shell">
    <header class="oui-header u1-head">
      <span class="u1-brand">
        <svg viewBox="0 0 256 256" aria-hidden="true" width="24" height="24"><path fill="currentColor" d="M40 96H72V160A32 32 0 0 0 104 192H152A32 32 0 0 0 184 160V96H216V160A64 64 0 0 1 152 224H104A64 64 0 0 1 40 160Z"/><rect x="40" y="40" width="32" height="64" rx="8" fill="#FF997D"/><rect x="88" y="40" width="32" height="64" rx="8" fill="#F4CF78"/><rect x="136" y="40" width="32" height="64" rx="8" fill="#A99BFF"/><rect x="184" y="40" width="32" height="64" rx="8" fill="#78CFD5"/></svg>
        <h1>{{ t('app.brand') }}</h1>
      </span>
      <span class="u1-pill" :class="{ ext: s.info?.firmware.kind === 'extended' }" data-test="firmware">{{ fwText }}</span>
      <span v-if="s.info" class="oui-meta u1-addr">{{ s.info.printer }} · {{ s.info.address }}</span>
      <TabList class="u1-nav" :aria-label="t('nav.label')">
        <Tab v-for="sec in sections" :key="sec.value" :value="sec.value" :data-tab="sec.value">
          <Icon :name="sec.icon" /> <span>{{ t(sec.label) }}</span>
        </Tab>
      </TabList>
    </header>
    <main class="u1-main">
      <TargetBanner />
      <NoticeArea />
      <TabPanels class="u1-panels">
        <TabPanel value="dash"><Dashboard /></TabPanel>
        <TabPanel value="files"><FilesView /></TabPanel>
        <TabPanel value="console"><ConsoleView /></TabPanel>
        <TabPanel value="settings"><SettingsView /></TabPanel>
      </TabPanels>
    </main>
    <ConfirmDialog />
  </Tabs>
</template>

<style>
html, body, #app { min-height: 100%; }
body { background: var(--oui-background); }
.u1-shell { display: flex; flex-direction: column; min-height: 100vh; background: var(--oui-background); }
.u1-head { position: sticky; top: 0; z-index: 5; }
.u1-brand { display: inline-flex; align-items: center; gap: 8px; }
.u1-brand h1 { margin: 0; font-size: 20px; }
.u1-pill { white-space: nowrap; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--oui-border); font-size: 12px; }
.u1-pill.ext { border-color: var(--p-primary-color); color: var(--p-primary-color); }
.u1-addr { overflow-wrap: anywhere; }
.u1-nav { margin-left: auto; min-width: 0; }
.u1-nav .p-tab { display: inline-flex; gap: 6px; align-items: center; }
.u1-main { flex: 1; padding: 16px; display: flex; flex-direction: column; min-width: 0; }
.u1-main > * { margin-bottom: 16px; }
.u1-main > :empty { margin-bottom: 0; }   /* live regions stay in the DOM, without leaving a gap */
.u1-panels.p-tabpanels { padding: 0; background: transparent; }
.u1-card { padding: 16px; background: var(--oui-surface); border: 1px solid var(--oui-border); border-radius: 12px; min-width: 0; }
.u1-card > h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; }
.u1-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.u1-spacer { flex: 1; }
.u1-sw { display: inline-block; flex: none; width: 16px; height: 16px; border-radius: 50%; border: 1px solid var(--oui-control-border, var(--oui-border)); }
.u1-why { color: var(--oui-muted); font-size: 12px; }
.u1-table { width: 100%; border-collapse: collapse; }
.u1-table th, .u1-table td { padding: 8px; border-bottom: 1px solid var(--oui-border); text-align: left; vertical-align: middle; }
.u1-table th { color: var(--oui-muted); font-size: 12px; font-weight: 600; }
.u1-warn { color: var(--oui-warning); }
.u1-err { color: var(--oui-danger); }
.u1-num { font-variant-numeric: tabular-nums; white-space: nowrap; }
@media (max-width: 720px) { .u1-main { padding: 12px; } .u1-nav { margin-left: 0; width: 100%; overflow-x: auto; } }
</style>
