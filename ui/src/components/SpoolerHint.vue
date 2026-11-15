<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiBanner } from '../../shared/src/components';
import { spoolman } from '../../shared/src/icons';
import * as bridge from '../core/bridge';
import { config } from '../app/settings';
import { t } from '../core/i18n';

// Spooler (the sibling plugin): on the Dashboard a suggestion until it is installed or dismissed; in Settings
// always, saying whether it was found.
const props = defineProps<{ where: 'dash' | 'settings' }>();
const sp = computed(() => config.value?.spooler ?? null);
const show = computed(() => !!sp.value && (props.where === 'settings' || (!sp.value.installed && !sp.value.dismissed)));
const dismiss = () => bridge.post({ type: 'save_settings', settings: { spooler_hint_dismissed: true } });
</script>
<template>
  <OuiBanner v-if="show && sp" role="note" :tone="sp.installed ? 'success' : 'info'" :icon="sp.installed ? undefined : spoolman" :title="t('spooler.title')" :data-test="`spooler-${where}`">
    <template v-if="sp.installed">{{ t('spooler.installed') }}</template>
    <template v-else>{{ t('spooler.suggest') }} <a :href="sp.url">{{ sp.url }}</a></template>
    <template v-if="!sp.installed && !sp.dismissed" #actions><Button severity="secondary" size="small" :label="t('spooler.dismiss')" @click="dismiss" /></template>
  </OuiBanner>
</template>
