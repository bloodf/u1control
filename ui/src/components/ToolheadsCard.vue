<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import Icon from './Icon.vue';
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
  <section class="u1-card" aria-labelledby="heads-h">
    <div class="u1-row th-head">
      <h2 id="heads-h"><Icon name="icon/toolheads-rfid" /> {{ t('heads.title') }}</h2>
      <span class="oui-meta" data-test="spool-source">{{ source }}</span><span class="u1-spacer" />
      <Button :disabled="!!controlsOff" data-focus-key="sync" :aria-describedby="'sync-help'" @click="bridge.post({ type: 'sync_project' })">
        <Icon name="icon/filament-spool" /><span>{{ t('heads.sync') }}</span></Button>
    </div>
    <p id="sync-help" class="oui-meta th-help">{{ t('heads.syncHelp') }}</p>
    <div v-if="s.status" class="th-grid">
      <HeadCard v-for="(h, i) in s.status.heads" :key="i" :index="i" />
    </div>
    <p v-else class="oui-muted">{{ t('heads.noStatus') }}</p>
  </section>
</template>
<style scoped>
.th-head h2 { margin: 0; display: flex; gap: 8px; align-items: center; }
.th-help { margin: 4px 0 12px; }
.th-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; --u1-t1: #FF997D; --u1-t2: #F4CF78; --u1-t3: #A99BFF; --u1-t4: #78CFD5; }
@media (max-width: 1100px) { .th-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .th-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
