<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { OuiPanel, OuiStatus, OuiSwatch } from '@orca-plugins/ui-foundation/src/components';
import { ace as aceIcon } from '@orca-plugins/ui-foundation/src/icons';
import { s, run, busy, controlsOff, tracker } from '../app/store';
import { ask } from '../core/dialog';
import { t, fmt } from '../core/i18n';

// multiACE's filament units (ACE Pro, ACE 2): read-only, as multiACE reports them. Drying starts or stops only on a
// confirmed click, never while the U1 is busy or multiACE swaps (the plugin refuses it too); nothing restarts by itself.
const ace = computed(() => s.status?.ace ?? null);
const feeds = (u: number, sl: number) => Object.entries(ace.value?.heads ?? {})
  .filter(([, v]) => v?.[0] === u && v?.[1] === sl).map(([h]) => `T${+h + 1}`).join(' ');
const off = computed(() => !!controlsOff.value || busy.value || !!ace.value?.swapping);
async function dry(u: number, start: boolean) {
  const n = u + 1, label = t(start ? 'ace.dry' : 'ace.stop', { n });
  if (!await ask({ title: label, text: t(start ? 'ace.dryAsk' : 'ace.stopAsk', { n }), yes: label, no: t('common.goBack') })) return;
  await run({ key: `ace:${u}`, label, cmd: 'ace_dry', args: { unit: u, start }, okText: t('ace.sent', { n }) });
}
</script>

<template>
  <OuiPanel :icon="aceIcon" :title="t('ace.title')" data-test="ace-card">
    <p v-if="!ace" class="oui-meta">{{ t('ace.none') }}</p>
    <div v-for="u in ace?.units ?? []" v-else :key="u.index" class="oui-stack ace-unit" :data-ace="u.index">
      <p class="oui-row">
        <strong>{{ t('ace.unit', { n: u.index + 1 }) }}<template v-if="u.name"> · {{ u.name }}</template></strong>
        <OuiStatus v-if="!u.connected" state="warn">{{ t('ace.offline') }}</OuiStatus>
        <span class="oui-meta oui-num">{{ [u.temp != null ? `${u.temp} °C` : '', u.humidity != null ? `${u.humidity} % RH` : ''].filter(Boolean).join(' · ') }}</span>
        <span class="oui-spacer" />
        <span v-if="u.drying" class="oui-chip" data-tone="info">{{ t('ace.drying', { temp: u.drying.temp ?? '?', left: fmt.duration(u.drying.left) }) }}</span>
        <Button v-if="u.dryer && u.connected" size="small" severity="secondary" :label="t(u.drying ? 'ace.stop' : 'ace.dry', { n: u.index + 1 })"
                :disabled="off || tracker.isBusy(`ace:${u.index}`)" :loading="tracker.isBusy(`ace:${u.index}`)" :data-dry="u.index" @click="dry(u.index, !u.drying)" />
      </p>
      <ul class="ace-slots" role="list">
        <li v-for="(sl, i) in u.slots" :key="i" class="oui-meta">
          <OuiSwatch :color="sl.colour" :size="14" /> {{ sl.material || t('ace.emptySlot') }}<template v-if="feeds(u.index, i)"> → {{ feeds(u.index, i) }}</template>
        </li>
      </ul>
    </div>
  </OuiPanel>
</template>

<style>
.ace-unit + .ace-unit { border-top: 1px solid var(--oui-border); padding-top: var(--oui-s2); }
.ace-slots { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 4px; margin: 0; padding: 0; list-style: none; }
.ace-slots li { display: flex; align-items: center; gap: 6px; }
</style>
