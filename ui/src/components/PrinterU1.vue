<script setup lang="ts">
import { computed } from 'vue';

// The U1, drawn: an enclosed printer with four parked toolheads in their identity colours. The active one is on
// the gantry and the print grows with the job. Decorative: every value it shows is in text next to it.
const props = defineProps<{ active?: number | null; progress?: number | null; size?: number; stale?: boolean }>();
const h = computed(() => 3 + Math.max(0, Math.min(100, props.progress ?? 0)) * 0.22);
</script>
<template>
  <svg class="art-printer" :width="(size ?? 96) * 1.25" :height="size ?? 96" viewBox="0 0 120 96" aria-hidden="true" focusable="false" :data-stale="stale || undefined">
    <rect class="art-body" x="10" y="8" width="100" height="80" rx="7" />
    <rect class="art-well" x="18" y="16" width="84" height="64" rx="4" />
    <path class="art-line" d="M18 30h84" />
    <template v-for="n in 4" :key="n">
      <rect v-if="n !== active" class="art-tool" :x="14 + n * 15.5" y="19" width="10" height="9" rx="2" :style="{ fill: `var(--oui-tool${n})` }" />
    </template>
    <path class="art-line" d="M22 44h76" />
    <g v-if="active"><rect class="art-tool" x="55" y="38" width="12" height="12" rx="2.5" :style="{ fill: `var(--oui-tool${active})` }" /><path class="art-tool" d="M58 50l3 4 3-4z" :style="{ fill: `var(--oui-tool${active})` }" /></g>
    <rect v-if="progress != null" class="art-print" x="49" :y="70 - h" width="24" :height="h" rx="2" />
    <rect class="art-bed" x="30" y="70" width="60" height="5" rx="2" />
  </svg>
</template>
