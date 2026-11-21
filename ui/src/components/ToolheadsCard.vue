<script setup lang="ts">
import { computed } from 'vue';
import { OuiEmpty, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { toolhead } from '@orca-plugins/ui-foundation/src/icons';
import HeadCard from './HeadCard.vue';
import { s } from '../app/store';
import { t } from '../core/i18n';

// One visible spool source per screen (X03): when Spooler's stock uses the same Spoolman, say so.
const source = computed(() => {
  if (s.spoolsRetrying) return t('sm.retrying');
  if (s.spoolsError) return t('heads.source.error', { error: s.spoolsError });
  if (!s.spoolsLoaded) return '';
  const n = s.spools.length;
  if (s.stock?.spooler.state === 'active' && s.stock.same_spoolman === true) return t('heads.source.same', { n });
  return s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n }) : t('heads.source.direct', { n });
});
</script>
<template>
  <OuiPanel class="u1-heads" :icon="toolhead" tone="magenta" aria-labelledby="heads-h">
    <template #title><span id="heads-h">{{ t('heads.title') }}</span></template>
    <template #meta><span data-test="spool-source" :title="source">{{ source }}</span></template>
    <!-- Why Edit, Load and Unload are off is said once for the page (#heads-why, under the page header), not in each card. -->
    <div v-if="s.status" class="oui-cards">
      <HeadCard v-for="(h, i) in s.status.heads" :key="i" :index="i" />
    </div>
    <OuiEmpty v-else-if="s.phase === 'unreachable'" compact state="offline" :title="t('heads.noStatus')" />
    <div v-else class="oui-cards" aria-busy="true" :aria-label="t('heads.noStatus')">
      <div v-for="n in 4" :key="n" class="u1-skelcard"><span class="oui-skeleton" /><span class="oui-skeleton" /><span class="oui-skeleton" /></div>
    </div>
  </OuiPanel>
</template>
<style>
/* Two cards a row in half the dashboard, four only when the widget is really wide. */
.u1-heads .oui-cards { --oui-cards-4: 1300px; }
/* The cards are as tall as their content: when the dashboard row is taller (the other half needs more), the room left is
   under the cards, never a blank band inside each card between its content and its actions. */

.u1-skelcard { display: grid; gap: var(--oui-s3); align-content: start; min-height: 180px; padding: var(--oui-s3); border-radius: var(--oui-radius-lg); background: var(--oui-raised); }
.u1-skelcard > .oui-skeleton:nth-child(1) { width: 30%; }
.u1-skelcard > .oui-skeleton:nth-child(2) { width: 80%; }
.u1-skelcard > .oui-skeleton:nth-child(3) { width: 55%; }
</style>
