<script setup lang="ts">
import { computed } from 'vue';
import { iconSvg } from '../core/icons';
const props = defineProps<{ name: string; size?: number }>();
const svg = computed(() => iconSvg(props.name));
</script>
<template>
  <!-- Build-time sanitized SVG from the plugin's own icon files (no script, no handlers). -->
  <span v-if="svg" class="u1-icon" aria-hidden="true" :style="size ? { '--icon-size': size + 'px' } : undefined" v-html="svg" />
</template>
<style scoped>
.u1-icon { display: inline-flex; flex: none; width: var(--icon-size, 16px); height: var(--icon-size, 16px); }
.u1-icon :deep(svg) { width: 100%; height: 100%; }
</style>
