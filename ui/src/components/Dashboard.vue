<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import Icon from './Icon.vue';
import StatusCard from './StatusCard.vue';
import CameraCard from './CameraCard.vue';
import ScreenCard from './ScreenCard.vue';
import ToolheadsCard from './ToolheadsCard.vue';
import StockCard from './StockCard.vue';
import UsageCard from './UsageCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import { s, run, controlsOff } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';

const st = computed(() => s.status);
const exceptions = computed(() => (st.value?.exceptions ?? []).map(x => JSON.stringify(x)).join('\n'));
async function powerResume() {
  if (!await ask({ title: t('act.powerResume'), text: t('confirm.powerResume.text'), yes: t('confirm.powerResume.yes'), no: t('common.goBack') })) return;
  await run({ key: 'power', label: t('act.powerResume'), cmd: 'power_loss', args: { action: 'resume' }, okText: t('ok.powerResume'), timeoutMs: 60000 });
}
async function powerDiscard() {
  if (!await ask({ title: t('act.powerDiscard'), text: t('confirm.powerDiscard.text'), yes: t('confirm.powerDiscard.yes'), no: t('common.goBack'), danger: true })) return;
  await run({ key: 'power', label: t('act.powerDiscard'), cmd: 'power_loss', args: { action: 'discard' }, okText: t('ok.powerDiscard') });
}
</script>
<template>
  <div class="db">
    <section v-if="st?.power_loss" class="u1-card db-warn" aria-labelledby="pl-h">
      <h2 id="pl-h"><Icon name="icon/power-loss-resume" /> {{ t('power.title') }}</h2>
      <p v-if="st.reprint" class="oui-meta">{{ t('power.options', { options: JSON.stringify(st.reprint) }) }}</p>
      <div class="u1-row">
        <Button :disabled="!!controlsOff" data-focus-key="pl-resume" @click="powerResume"><Icon name="icon/resume" /><span>{{ t('power.resume') }}</span></Button>
        <Button severity="danger" outlined :disabled="!!controlsOff" data-focus-key="pl-discard" @click="powerDiscard"><Icon name="icon/delete" /><span>{{ t('power.discard') }}</span></Button>
      </div>
    </section>
    <section v-if="exceptions" class="u1-card db-err" aria-labelledby="ex-h" role="alert">
      <h2 id="ex-h" class="u1-err"><Icon name="icon/error" /> {{ t('exceptions.title') }}</h2>
      <pre class="oui-error-detail">{{ exceptions }}</pre>
    </section>
    <UsageCard />
    <div class="db-grid">
      <StatusCard />
      <div class="db-side">
        <CameraCard />
        <ScreenCard v-if="s.info?.firmware.kind === 'extended'" />
      </div>
    </div>
    <SpoolerHint where="dash" />
    <ToolheadsCard />
    <StockCard />
  </div>
</template>
<style scoped>
.db { display: grid; gap: 16px; }
.db-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(280px, 1fr); gap: 16px; align-items: start; }
.db-side { display: grid; gap: 16px; min-width: 0; }
.db-warn { border-color: var(--oui-warning); }
.db-err { border-color: var(--oui-danger); }
@media (max-width: 900px) { .db-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
