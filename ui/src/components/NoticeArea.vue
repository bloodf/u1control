<script setup lang="ts">
import { computed } from 'vue';
import Message from 'primevue/message';
import Button from 'primevue/button';
import { tracker } from '../app/store';
import { t, fmt } from '../core/i18n';

const severity = { error: 'error', unknown: 'warn', success: 'success', info: 'info' } as const;
const lasting = computed(() => tracker.notices.filter(n => n.kind === 'error' || n.kind === 'unknown'));
const passing = computed(() => tracker.notices.filter(n => n.kind === 'success' || n.kind === 'info'));
const waiting = computed(() => [...tracker.pending.values()].filter(p => p.key !== 'spools'));
</script>
<template>
  <section class="notices" :aria-label="t('msg.region')">
    <!-- Errors and unknown outcomes stay until dismissed and are announced at once. -->
    <div role="alert" class="stack">
      <Message v-for="n in lasting" :key="n.id" :severity="severity[n.kind]">
        <div class="row-msg"><span>{{ n.text }} <span class="oui-meta">{{ fmt.time(n.at / 1000) }}</span></span>
          <Button text size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)" /></div>
      </Message>
    </div>
    <div role="status" aria-live="polite" class="stack">
      <Message v-for="p in waiting" :key="'p-' + p.key" severity="secondary">{{ t('msg.waiting', { action: p.label }) }}</Message>
      <Message v-for="n in passing" :key="n.id" :severity="severity[n.kind]">
        <div class="row-msg"><span>{{ n.text }}</span>
          <Button text size="small" :label="t('common.dismiss')" @click="tracker.dismiss(n.id)" /></div>
      </Message>
    </div>
  </section>
</template>
<style scoped>
.notices { display: grid; margin-bottom: 0 !important; }
/* The live regions stay rendered (an empty region announces what is added later); only filled ones take space. */
.stack { display: grid; gap: 8px; }
.stack:not(:empty) { margin-bottom: 16px; }
.row-msg { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
</style>
