<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { OuiThumb } from '@orca-plugins/ui-foundation/src/components';
import { file } from '@orca-plugins/ui-foundation/src/icons';
import { watchThumb } from '../app/thumbs';
// A print file's preview, asked for only once its row is on screen (app/thumbs). The box keeps its size without it.
const props = defineProps<{ gen: number; path: string; rel?: string }>();
const el = ref<HTMLElement | null>(null);
const src = ref('');
let stop = () => {};
onMounted(() => { if (props.rel && el.value) stop = watchThumb(el.value, props.gen, { path: props.path, thumb: props.rel }, v => { src.value = v; }); });
onBeforeUnmount(() => stop());
</script>
<template><span ref="el" class="thumb"><OuiThumb :src="src" :size="40" :icon="file" /></span></template>
<style>.thumb { display: inline-flex; }</style>
