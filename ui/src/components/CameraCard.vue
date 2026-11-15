<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import { OuiEmpty, OuiIcon, OuiPanel } from '../../shared/src/components';
import { camera, cameraOff, download } from '../../shared/src/icons';
import * as bridge from '../core/bridge';
import { s, lease, run, tracker, targetKnown, printerName } from '../app/store';
import { t } from '../core/i18n';
import { config } from '../app/settings';

async function toggle() {
  s.camOn = !s.camOn;
  if (!s.camOn) { s.frame = ''; s.camError = ''; }
  lease();
  await nextTick();   // Start and Stop are different buttons: keep the keyboard on the one that replaced the other
  if (document.activeElement === document.body) document.querySelector<HTMLElement>('[data-focus-key="camera"]')?.focus();
}
async function save() {
  const r = await run({ key: 'snapshot', label: t('act.snapshot'), cmd: 'snapshot' });
  if (r.ok) tracker.notify('success', t('ok.saved', { path: r.result }));
}
// Most camera pictures a second to ask for; stored by the plugin (settings camera_fps), 5 by default.
const FPS = computed(() => [5, 10, 15, 30].map(n => ({ value: n, label: t('cam.fpsOption', { n }) })));
const fpsChoice = ref<number | null>(null);
const fps = computed(() => fpsChoice.value ?? config.value?.settings.camera_fps ?? 5);
function setFps(n: number) {
  fpsChoice.value = n;
  bridge.post({ type: 'camera_fps', value: n });
}
</script>
<template>
  <!-- Off: one row, so the printer's state stays above the fold (U08). -->
  <OuiPanel :icon="camera" tone="sky" flush aria-labelledby="cam-h">
    <template #title><span id="cam-h">{{ t('cam.title') }}</span></template>
    <template v-if="s.camOn" #actions>
      <Select :model-value="fps" :options="FPS" option-label="label" option-value="value" size="small" :aria-label="t('cam.fps')"
              :pt="{ label: { 'aria-describedby': 'cam-fps-help' } }" data-test="cam-fps" @update:model-value="setFps" />
      <Button v-if="s.frame" severity="secondary" size="small" :label="t('cam.save')" :title="t('cam.saveHint')" :loading="tracker.isBusy('snapshot')"
              data-focus-key="cam-save" data-test="cam-save" @click="save"><template #icon><OuiIcon :icon="download" :size="14" /></template></Button>
      <Button severity="secondary" size="small" :label="t('cam.stop')" data-focus-key="camera" data-test="camera" @click="toggle"><template #icon><OuiIcon :icon="cameraOff" :size="14" /></template></Button>
    </template>
    <OuiEmpty v-if="!s.camOn" compact tone="sky" :icon="cameraOff" :title="t('cam.off')" :text="targetKnown ? t('cam.offHint') : t('cam.noTarget')">
      <template #actions><Button severity="secondary" :label="t('cam.start')" :disabled="!targetKnown" data-focus-key="camera" data-test="camera" @click="toggle">
        <template #icon><OuiIcon :icon="camera" :size="14" /></template></Button></template>
    </OuiEmpty>
    <template v-else>
      <div class="u1-view">
        <img v-if="s.frame" :src="s.frame" :alt="t('cam.alt', { printer: printerName })" @load="bridge.post({ type: 'frame_ack' })">
        <div v-else class="oui-on-band u1-view-wait" role="status"><OuiEmpty :state="s.camError ? 'error' : 'loading'" :title="s.camError ? t('cam.unavailable', { error: s.camError }) : t('cam.starting')" /></div>
      </div>
      <p id="cam-fps-help" class="oui-meta u1-pad">{{ t('cam.fpsHelp') }}</p>
    </template>
  </OuiPanel>
</template>
<style>
/* The picture area: always black behind the picture, whatever the theme (it is a camera frame, not a surface). */
.u1-view { position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; aspect-ratio: 16 / 9; background: #000; }
.u1-view img { width: 100%; height: 100%; object-fit: contain; }
.u1-view .u1-view-wait { background: none; }
</style>
