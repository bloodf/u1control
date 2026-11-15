<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel } from '../../shared/src/components';
import { check, toolhead } from '../../shared/src/icons';
import HeadCard from './HeadCard.vue';
import * as bridge from '../core/bridge';
import { s, controlsOff } from '../app/store';
import { t } from '../core/i18n';

// One visible spool source per screen (X03): when Spooler's stock uses the same Spoolman, say so.
const source = computed(() => {
  if (s.spoolsError) return t('heads.source.error', { error: s.spoolsError });
  if (!s.spoolsLoaded) return '';
  const n = s.spools.length;
  if (s.stock?.spooler.state === 'active' && s.stock.same_spoolman === true) return t('heads.source.same', { n });
  return s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n }) : t('heads.source.direct', { n });
});
</script>
<template>
  <OuiPanel :icon="toolhead" tone="magenta" :flush="!s.status" aria-labelledby="heads-h">
    <template #title><span id="heads-h">{{ t('heads.title') }}</span></template>
    <template #meta><span data-test="spool-source" :title="source">{{ source }}</span></template>
    <template #actions>
      <Button size="small" :label="t('heads.sync')" :disabled="!!controlsOff" data-focus-key="sync" :aria-describedby="controlsOff ? 'heads-why' : 'sync-help'" @click="bridge.post({ type: 'sync_project' })">
        <template #icon><OuiIcon :icon="check" :size="14" /></template></Button>
    </template>
    <!-- Why Edit, Load and Unload are off is said once for the page (#heads-why, under the app bar), not in each card. -->
    <div v-if="s.status" class="oui-cards">
      <HeadCard v-for="(h, i) in s.status.heads" :key="i" :index="i" />
    </div>
    <OuiEmpty v-else compact tone="magenta" :icon="toolhead" :title="t('heads.noStatus')" />
    <template #footer><p id="sync-help" class="oui-meta">{{ t('heads.syncHelp') }}</p></template>
  </OuiPanel>
</template>
