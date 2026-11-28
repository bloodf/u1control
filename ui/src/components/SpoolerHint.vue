<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiIcon } from '@orca-plugins/ui-foundation/src/components';
import { external, spoolman } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { config } from '../app/settings';
import { t } from '../core/i18n';

// Spooler (the sibling plugin): on the Dashboard a suggestion until it is installed or closed. Closing it is kept in
// the plugin's settings, so it does not come back. Settings lists Spooler as a requirement (SettingsView).
const sp = computed(() => config.value?.spooler ?? null);
const dismiss = () => bridge.post({ type: 'save_settings', settings: { spooler_hint_dismissed: true } });
</script>
<template>
  <OuiBanner v-if="sp && !sp.installed && !sp.dismissed" role="note" tone="info" :icon="spoolman" :title="t('spooler.title')" data-test="spooler-dash"
             dismissible :close-label="t('spooler.dismiss')" @dismiss="dismiss">
    {{ t('spooler.suggest') }}
    <template v-if="sp.url" #actions>
      <Button as="a" :href="sp.url" target="_blank" rel="noopener noreferrer" size="small" severity="secondary" :label="t('spooler.get')" data-test="spooler-get">
        <template #icon><OuiIcon :icon="external" :size="14" /></template></Button>
    </template>
  </OuiBanner>
</template>
