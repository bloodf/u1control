<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Button from 'primevue/button';
import { OuiCamera, OuiIcon, OuiPanel, OuiWidgetMaximize } from '@orca-plugins/ui-foundation/src/components';
import { camera, cameraOff, download, refresh } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { s, lease, run, tracker, targetKnown, printerName, stale } from '../app/store';
import { t } from '../core/i18n';
import { watchInView } from '../core/in-view';
import { config as stored } from '../app/settings';

// The widget's settings: the picture's shape (the box keeps it at any widget size, the picture is shown whole in it)
// and the most pictures a second to ask for. The rate is the plugin's (settings camera_fps, 5 by default): a choice
// made here is stored there.
const props = withDefaults(defineProps<{ config?: { aspect?: string; fps?: number } }>(), { config: () => ({}) });
const shape = computed(() => { const [w, h] = (props.config.aspect ?? '16/9').split('/'); return { '--oui-camera-w': w, '--oui-camera-h': h }; });
function start(on: boolean) {
  s.camOn = on;
  s.frame = ''; s.camError = '';
  lease();
}
/** After an error: ask again from the start. */
function retry() { start(false); start(true); }
async function save() {
  const r = await run({ key: 'snapshot', label: t('act.snapshot'), cmd: 'snapshot' });
  if (r.ok) tracker.notify('success', t('ok.saved', { path: r.result }));
}
const fps = computed(() => props.config.fps ?? stored.value?.settings.camera_fps ?? 5);
watch(() => props.config.fps, n => { if (n && stored.value && n !== stored.value.settings.camera_fps) bridge.post({ type: 'camera_fps', value: n }); });
// A card scrolled out of view (or behind a maximised widget) is not streamed to: the lease says so.
const panel = ref<{ $el: Element }>();
watchInView(() => panel.value?.$el, seen => { s.camSeen = seen; lease(); });
const state = computed(() => (!s.camOn ? 'off' : s.frame ? 'live' : s.camError ? 'error' : 'loading'));
const title = computed(() => (!s.camOn ? t('cam.off') : s.camError ? t('cam.unavailable') : t('cam.starting')));
const text = computed(() => (!s.camOn ? (targetKnown.value ? undefined : t('cam.noTarget')) : s.camError ? t('cam.unavailableText') : undefined));
</script>
<template>
  <!-- The picture box keeps its 16:9 whatever the camera does, so turning it on does not move the page. The snapshot
       and on/off are the module's header; the rate is one of the widget's settings, and what it means is its (i). -->
  <OuiPanel ref="panel" :icon="camera" tone="sky" flush aria-labelledby="cam-h" :hint="t('cam.fpsHelp')" hint-id="cam-fps-help" :hint-label="t('cam.about')">
    <template #title><span id="cam-h">{{ t('cam.title') }}</span></template>
    <template #actions>
      <Button v-if="s.frame" severity="secondary" text size="small" :aria-label="t('cam.save')" :title="t('cam.saveHint')" :loading="tracker.isBusy('snapshot')"
              data-focus-key="cam-save" data-test="cam-save" @click="save"><template #icon><OuiIcon :icon="download" :size="14" /></template></Button>
      <Button v-if="s.camOn" severity="secondary" size="small" :label="t('cam.stop')" data-focus-key="camera" data-test="camera" @click="start(false)">
        <template #icon><OuiIcon :icon="cameraOff" :size="14" /></template></Button>
      <OuiWidgetMaximize />
    </template>
    <!-- Every picture shown is acknowledged, so the plugin sends the next one. The camera's picture is shown whole.
         A printer the page no longer hears from keeps its last picture, greyed and named as that, never as live. -->
    <OuiCamera fit="contain" :style="shape" :src="s.frame" :alt="t('cam.alt', { printer: printerName })" :state="state" :title="title" :text="text" :data-stale="stale || undefined"
               @frame="bridge.post({ type: 'frame_ack' })">
      <template #actions>
        <Button v-if="!s.camOn" severity="secondary" :label="t('cam.start')" :disabled="!targetKnown" data-focus-key="camera" data-test="camera" @click="start(true)">
          <template #icon><OuiIcon :icon="camera" :size="14" /></template></Button>
        <Button v-else-if="s.camError" severity="secondary" :label="t('common.retry')" data-focus-key="cam-retry" data-test="cam-retry" @click="retry">
          <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
      </template>
      <template #overlay>
        <span v-if="stale" class="oui-chip" data-test="cam-last">{{ t('cam.last') }}</span>
        <template v-else><span class="oui-chip">{{ t('cam.live') }}</span><span class="oui-chip oui-num">{{ t('cam.fpsOption', { n: fps }) }}</span></template>
      </template>
    </OuiCamera>
  </OuiPanel>
</template>
<style>
.oui-camera[data-stale] .oui-camera-picture { filter: grayscale(1); opacity: .6; }
</style>
