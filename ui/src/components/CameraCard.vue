<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import { OuiCamera, OuiIcon, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { camera, cameraOff, download } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { s, lease, run, tracker, targetKnown, printerName } from '../app/store';
import { t } from '../core/i18n';
import { config } from '../app/settings';

function toggle() {
  s.camOn = !s.camOn;
  if (!s.camOn) { s.frame = ''; s.camError = ''; }
  lease();
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
const state = computed(() => (!s.camOn ? 'off' : s.frame ? 'live' : s.camError ? 'error' : 'loading'));
const title = computed(() => (!s.camOn ? t('cam.off') : s.camError ? t('cam.unavailable', { error: s.camError }) : t('cam.starting')));
</script>
<template>
  <!-- The picture box keeps its 16:9 whatever the camera does, so turning it on does not move the page. The rate, the
       snapshot and on/off are the module's header; what the rate means is its (i). -->
  <OuiPanel :icon="camera" tone="sky" flush aria-labelledby="cam-h" :hint="t('cam.fpsHelp')" hint-id="cam-fps-help" :hint-label="t('cam.about')">
    <template #title><span id="cam-h">{{ t('cam.title') }}</span></template>
    <template #actions>
      <Select v-if="s.camOn" :model-value="fps" :options="FPS" option-label="label" option-value="value" size="small" :aria-label="t('cam.fps')"
              :pt="{ label: { 'aria-describedby': 'cam-fps-help' } }" data-test="cam-fps" @update:model-value="setFps" />
      <Button v-if="s.frame" severity="secondary" text size="small" :aria-label="t('cam.save')" :title="t('cam.saveHint')" :loading="tracker.isBusy('snapshot')"
              data-focus-key="cam-save" data-test="cam-save" @click="save"><template #icon><OuiIcon :icon="download" :size="14" /></template></Button>
      <Button severity="secondary" size="small" :label="s.camOn ? t('cam.stop') : t('cam.start')" :disabled="!s.camOn && !targetKnown" data-focus-key="camera" data-test="camera" @click="toggle">
        <template #icon><OuiIcon :icon="s.camOn ? cameraOff : camera" :size="14" /></template></Button>
    </template>
    <!-- Every picture shown is acknowledged, so the plugin sends the next one. The camera's picture is shown whole. -->
    <OuiCamera fit="contain" :src="s.frame" :alt="t('cam.alt', { printer: printerName })" :state="state" :title="title" :text="s.camOn ? undefined : targetKnown ? t('cam.offHint') : t('cam.noTarget')"
               @frame="bridge.post({ type: 'frame_ack' })">
      <template #overlay><span class="oui-chip">{{ t('cam.live') }}</span><span class="oui-chip oui-num">{{ t('cam.fpsOption', { n: fps }) }}</span></template>
    </OuiCamera>
  </OuiPanel>
</template>
