<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { OuiIcon } from '../../shared/src/components';
import { video } from '../../shared/src/icons';
import { covers } from '../app/thumbs';
// A time-lapse's cover picture, asked for only once its row is on screen (app/thumbs); the video icon without one.
// foundation-gap: OuiThumb (5.0.0) is a square box with one `size`; a video cover is 16:9 and, fitted into a square
// that keeps the row low, it is a sliver. This is OuiThumb's box with a width and a height.
// OuiThumb should take a width and a height (or a ratio).
const props = defineProps<{ gen: number; path?: string | null }>();
const el = ref<HTMLElement | null>(null);
const src = ref('');
const failed = ref(false);
let stop = () => {};
onMounted(() => { if (props.path && el.value) stop = covers.watch(el.value, props.gen, { path: props.path }, v => { src.value = v; }); });
onBeforeUnmount(() => stop());
</script>
<template>
  <span ref="el" class="tl-cover">
    <img v-if="src && !failed" :src="src" alt="" width="96" height="54" draggable="false" @error="failed = true">
    <OuiIcon v-else :icon="video" :size="20" />
  </span>
</template>
<style>
/* Box and picture both get the same width and height in px, as OuiThumb: the picture never sets the row's height. */
.tl-cover { flex: none; display: inline-flex; align-items: center; justify-content: center; overflow: hidden; width: 96px; height: 54px;
  border-radius: var(--oui-radius-sm); color: var(--oui-muted); background: var(--oui-inset); box-shadow: inset 0 0 0 1px var(--oui-border); vertical-align: middle; }
.tl-cover > img { display: block; flex: none; width: 96px; height: 54px; object-fit: contain; }
</style>
