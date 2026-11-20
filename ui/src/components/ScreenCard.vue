<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { hand, x } from '@orca-plugins/ui-foundation/src/icons';
import { s, lease, run } from '../app/store';
import { t } from '../core/i18n';

/** The remote screen is the Extended Firmware's: on other firmware the card stays, off, and says why. */
const off = computed(() => (s.info?.firmware.kind === 'extended' ? '' : s.info?.firmware.kind === 'stock' ? t('scr.needsExt') : t('reason.waiting')));

function toggle() { s.scrOn = !s.scrOn; if (!s.scrOn) { s.screen = ''; s.screenError = ''; } lease(); }
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
  <OuiPanel :icon="hand" flush aria-labelledby="scr-h" :hint="t('scr.hint')" :hint-label="t('scr.about')">
    <template #title><span id="scr-h">{{ t('scr.title') }}</span></template>
    <template #actions>
      <Button severity="secondary" size="small" :label="s.scrOn && !off ? t('scr.hide') : t('scr.show')" :disabled="!!off" data-focus-key="screen" data-test="screen-show" @click="toggle">
        <template #icon><OuiIcon :icon="s.scrOn && !off ? x : hand" :size="14" /></template></Button>
    </template>
    <OuiEmpty v-if="!s.scrOn || off" compact :icon="hand" :title="t('scr.off')" :text="off || undefined" data-test="screen-card" />
    <div v-else class="u1-view-screen" :role="s.screen ? undefined : 'status'">
      <img v-if="s.screen" :src="s.screen" :alt="t('scr.alt')" @click="tap">
      <OuiEmpty v-else :state="s.screenError ? 'error' : 'loading'" :title="s.screenError || t('scr.connecting')" />
    </div>
  </OuiPanel>
</template>
<style>
/* The touchscreen's own 1024 x 600, on the neutral track every picture sits on. The picture is fitted, never cropped: a
   click is mapped back to the screen's pixels. */
.u1-view-screen { display: grid; place-items: center; overflow: hidden; aspect-ratio: 1024 / 600; background: var(--oui-inset); border-radius: 0 0 var(--oui-radius-lg) var(--oui-radius-lg); }
.u1-view-screen img { width: 100%; height: 100%; object-fit: contain; cursor: pointer; }
</style>
