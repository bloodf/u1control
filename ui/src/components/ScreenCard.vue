<script setup lang="ts">
import { nextTick } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel } from '../../shared/src/components';
import { hand, x } from '../../shared/src/icons';
import { s, lease, run } from '../app/store';
import { t } from '../core/i18n';

async function toggle() {
  s.scrOn = !s.scrOn; if (!s.scrOn) { s.screen = ''; s.screenError = ''; } lease();
  await nextTick();
  if (document.activeElement === document.body) document.querySelector<HTMLElement>('[data-focus-key="screen"]')?.focus();
}
function tap(e: MouseEvent) {
  const img = e.currentTarget as HTMLImageElement;
  const r = img.getBoundingClientRect(), w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return;
  const k = Math.min(r.width / w, r.height / h), ox = (r.width - w * k) / 2, oy = (r.height - h * k) / 2;   // object-fit: contain
  const px = Math.round((e.clientX - r.left - ox) / k), py = Math.round((e.clientY - r.top - oy) / k);
  if (px >= 0 && py >= 0 && px < w && py < h) void run({ key: 'screen', label: t('act.screen'), cmd: 'screen_touch', args: { x: px, y: py }, allowRepeat: true });
}
</script>
<template>
  <OuiPanel :icon="hand" tone="violet" flush aria-labelledby="scr-h">
    <template #title><span id="scr-h">{{ t('scr.title') }}</span></template>
    <template v-if="s.scrOn" #actions>
      <Button severity="secondary" size="small" :label="t('scr.hide')" data-focus-key="screen" @click="toggle"><template #icon><OuiIcon :icon="x" :size="14" /></template></Button>
    </template>
    <OuiEmpty v-if="!s.scrOn" compact tone="violet" :icon="hand" :title="t('scr.off')" :text="t('scr.hint')">
      <template #actions><Button severity="secondary" :label="t('scr.show')" data-focus-key="screen" @click="toggle"><template #icon><OuiIcon :icon="hand" :size="14" /></template></Button></template>
    </OuiEmpty>
    <template v-else>
      <div class="u1-view u1-view-screen">
        <img v-if="s.screen" :src="s.screen" :alt="t('scr.alt')" @click="tap">
        <div v-else class="oui-on-band u1-view-wait" role="status"><OuiEmpty :state="s.screenError ? 'error' : 'loading'" :title="s.screenError || t('scr.connecting')" /></div>
      </div>
      <p class="oui-meta u1-pad">{{ t('scr.hint') }}</p>
    </template>
  </OuiPanel>
</template>
<style>
.u1-view-screen { aspect-ratio: 1024 / 600; }
.u1-view-screen img { cursor: pointer; }
</style>
