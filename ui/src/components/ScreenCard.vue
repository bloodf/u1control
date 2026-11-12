<script setup lang="ts">
import Button from 'primevue/button';
import Icon from './Icon.vue';
import { s, lease, run } from '../app/store';
import { t } from '../core/i18n';

function toggle() { s.scrOn = !s.scrOn; if (!s.scrOn) { s.screen = ''; s.screenError = ''; } lease(); }
function tap(e: MouseEvent) {
  const img = e.currentTarget as HTMLImageElement;
  const r = img.getBoundingClientRect(), w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return;
  const k = Math.min(r.width / w, r.height / h), ox = (r.width - w * k) / 2, oy = (r.height - h * k) / 2;   // object-fit: contain
  const x = Math.round((e.clientX - r.left - ox) / k), y = Math.round((e.clientY - r.top - oy) / k);
  if (x >= 0 && y >= 0 && x < w && y < h) void run({ key: 'screen', label: t('act.screen'), cmd: 'screen_touch', args: { x, y }, allowRepeat: true });
}
</script>
<template>
  <section class="u1-card" aria-labelledby="scr-h">
    <h2 id="scr-h"><Icon name="icon/firmware" /> {{ t('scr.title') }}</h2>
    <div v-if="s.scrOn" class="scr-view">
      <img v-if="s.screen" :src="s.screen" :alt="t('scr.alt')" @click="tap">
      <div v-else class="scr-empty" role="status"><Icon name="spot/camera-off" :size="96" />
        <span>{{ s.screenError || t('scr.connecting') }}</span></div>
    </div>
    <div class="u1-row" style="margin-top: 8px">
      <Button :outlined="s.scrOn" :severity="s.scrOn ? 'secondary' : undefined" data-focus-key="screen" @click="toggle">
        <Icon name="icon/live-stream" /><span>{{ s.scrOn ? t('scr.hide') : t('scr.show') }}</span></Button>
      <span class="oui-meta">{{ s.scrOn ? t('scr.hint') : t('scr.off') }}</span>
    </div>
  </section>
</template>
<style scoped>
.scr-view { position: relative; background: #000; border-radius: 6px; aspect-ratio: 1024 / 600; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.scr-view img { width: 100%; height: 100%; object-fit: contain; cursor: pointer; }
.scr-empty { display: grid; justify-items: center; gap: 8px; color: #d5dbe3; }
</style>
