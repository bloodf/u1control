<script setup lang="ts">
// One row of Settings > Requirements. Kept alone and small on purpose: ui-foundation 4.2.0's OuiRequirement replaces it.
import { OuiIcon, OuiStatus, type OuiState } from '../../shared/src/components';
import { external } from '../../shared/src/icons';

defineProps<{ id: string; name: string; state: OuiState; status: string; why: string; detail?: string;
  /** How to get it, one line each; shown only while it is not there. */ steps?: string[]; link?: { href: string; label: string } }>();
</script>
<template>
  <div class="u1-req" :data-req="id">
    <div class="u1-req-head"><span class="oui-strong">{{ name }}</span><OuiStatus :state="state" :data-req-status="id">{{ status }}</OuiStatus></div>
    <p class="oui-meta">{{ why }}</p>
    <p v-if="detail" class="oui-meta" :data-req-detail="id">{{ detail }}</p>
    <ol v-if="steps?.length" class="u1-req-steps oui-meta" :data-req-steps="id"><li v-for="(x, i) in steps" :key="i">{{ x }}</li></ol>
    <a v-if="steps?.length && link" class="u1-inline" :href="link.href"><OuiIcon :icon="external" :size="14" />{{ link.label }}</a>
  </div>
</template>
<style>
.u1-req { display: grid; gap: var(--oui-s1); padding: var(--oui-s3) var(--oui-s4); border-top: 1px solid var(--oui-border); }
.u1-req:first-child { border-top: 0; }
.u1-req-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--oui-s2); }
.u1-req-steps { margin: 0; padding-inline-start: 1.4em; display: grid; gap: 2px; }
</style>
