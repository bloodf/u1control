<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { watchThumb } from '../app/thumbs';
const props = defineProps<{ gen: number; path: string; rel?: string }>();
const el = ref<HTMLElement | null>(null);
const src = ref('');
let stop = () => {};
onMounted(() => { if (props.rel && el.value) stop = watchThumb(el.value, props.gen, { path: props.path, thumb: props.rel }, v => { src.value = v; }); });
onBeforeUnmount(() => stop());
</script>
<template><span ref="el" class="thumb"><img v-if="src" :src="src" alt=""></span></template>
<style scoped>.thumb { display: inline-block; width: 40px; height: 40px; } .thumb img { width: 40px; height: 40px; object-fit: contain; }</style>
