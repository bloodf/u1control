<script setup lang="ts">
import { computed } from 'vue';
import { OuiBanner } from '../../shared/src/components';
import { spoolman } from '../../shared/src/icons';
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
    {{ t('spooler.suggest') }} <a :href="sp.url">{{ sp.url }}</a>
  </OuiBanner>
</template>
