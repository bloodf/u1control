<script setup lang="ts">
import Message from 'primevue/message';
import Button from 'primevue/button';
import { s, hello, printerName, statusAge, STALE_STATUS_S } from '../app/store';
import { t, fmt } from '../core/i18n';
</script>
<template>
  <div role="status" aria-live="polite" data-test="target-banner">
    <Message v-if="s.phase === 'noTarget'" severity="warn">
      <strong>{{ t('target.none.title') }}</strong>
      <p class="tb-p">{{ t('target.none.body') }}</p>
      <p class="tb-p oui-meta">{{ t('target.detail', { error: s.error }) }}</p>
      <div class="u1-row"><Button size="small" :label="t('common.openSettings')" @click="s.tab = 'settings'" />
        <Button size="small" severity="secondary" outlined :label="t('common.retry')" @click="hello()" /></div>
    </Message>
    <Message v-else-if="s.phase === 'unreachable' || s.offline" severity="error">
      <strong>{{ t('target.offline.title') }}</strong>
      <p class="tb-p">{{ t('target.offline.body', { printer: printerName, error: s.offline || s.error }) }}</p>
      <Button size="small" severity="secondary" outlined :label="t('common.retry')" @click="hello()" />
    </Message>
    <Message v-else-if="s.phase === 'connecting'" severity="secondary">{{ t('target.connecting') }}</Message>
    <Message v-else-if="s.status && statusAge > STALE_STATUS_S" severity="warn">{{ t('target.stale', { age: fmt.ago(s.statusAt / 1000, s.now / 1000) }) }}</Message>
  </div>
</template>
<style scoped>.tb-p { margin: 4px 0 8px; }</style>
