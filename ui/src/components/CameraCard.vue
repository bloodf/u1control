<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import Icon from './Icon.vue';
import * as bridge from '../core/bridge';
import { s, lease, targetKnown, printerName } from '../app/store';
import { t } from '../core/i18n';

function toggle() {
  s.camOn = !s.camOn;
  if (!s.camOn) { s.frame = ''; s.camError = ''; }
  lease();
}
const msg = computed(() => (s.camError ? t('cam.unavailable', { error: s.camError }) : t('cam.starting')));
</script>
<template>
  <!-- Off: a compact strip so status and controls stay above the fold (U08). -->
  <section class="u1-card cam-card" :class="{ compact: !s.camOn }" aria-labelledby="cam-h">
    <div class="u1-row">
      <h2 id="cam-h" class="cam-h"><Icon name="icon/camera" /> {{ t('cam.title') }}</h2>
      <span v-if="!s.camOn" class="oui-meta">{{ t('cam.off') }} · {{ t('cam.offHint') }}</span>
      <span class="u1-spacer" />
      <Button :severity="s.camOn ? 'secondary' : undefined" :outlined="s.camOn" :disabled="!targetKnown && !s.camOn"
              data-focus-key="camera" data-test="camera" @click="toggle">
        <Icon name="icon/live-stream" /><span>{{ s.camOn ? t('cam.stop') : t('cam.start') }}</span></Button>
    </div>
    <p v-if="!targetKnown && !s.camOn" class="u1-why">{{ t('cam.noTarget') }}</p>
    <div v-if="s.camOn" class="cam-view">
      <img v-if="s.frame" :src="s.frame" :alt="t('cam.alt', { printer: printerName })" @load="bridge.post({ type: 'frame_ack' })">
      <div v-else class="cam-empty" role="status"><Icon :name="s.camError ? 'spot/camera-off' : 'spot/not-connected'" :size="96" /><span>{{ msg }}</span></div>
    </div>
  </section>
</template>
<style scoped>
.cam-h { margin: 0; display: flex; align-items: center; gap: 8px; }
.cam-card.compact { padding-block: 10px; }
.cam-view { margin-top: 12px; position: relative; background: #000; border-radius: 6px; aspect-ratio: 16 / 9; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.cam-view img { width: 100%; height: 100%; object-fit: contain; }
.cam-empty { display: grid; justify-items: center; gap: 8px; color: #d5dbe3; padding: 16px; text-align: center; }
</style>
