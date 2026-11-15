<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Button from 'primevue/button';
import { OuiBanner, OuiIcon, OuiPanel } from '../../shared/src/components';
import { check, eye, warning } from '../../shared/src/icons';
import { s, run, tracker } from '../app/store';
import { ask } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import type { UsageEntry } from '../app/types';

// U05: prints whose Spoolman update wasn't confirmed stay listed with their identity until the user marks them
// checked. Marking is local and audited by the plugin (usage_ack); nothing is booked again from here.
// One banner says it; Review opens the list.
const u = computed(() => s.usage);
const list = computed(() => u.value?.unconfirmed ?? []);
const show = computed(() => !!(list.value.length || u.value?.save_error || u.value?.restore_notice || s.usageError));
const fileName = (e: UsageEntry) => (e.file ? e.file.split('/').pop() : '') || t('common.unknown');
const when = (e: UsageEntry) => (e.at ? fmt.dateTime(e.at) : t('usage.unknownTime'));
const open = ref(false);
watch(() => list.value.length, n => { if (!n) open.value = false; });
const first = computed(() => {
  const e = list.value[0];
  if (!e) return '';
  return [fileName(e), `T${(e.head ?? 0) + 1}`, `${fmt.number(e.grams ?? 0, 1)} g`, e.spool != null ? t('usage.spool', { id: e.spool }) : t('usage.noSpool'), e.error,
    list.value.length > 1 ? t('usage.more', { n: list.value.length - 1 }) : ''].filter(Boolean).join(' · ');
});

async function ack(e: UsageEntry) {
  const n = (e.head ?? 0) + 1;
  if (!await ask({ title: t('confirm.ack.title'), text: t('confirm.ack.text', { grams: fmt.number(e.grams ?? 0, 1), n, file: fileName(e) }),
    yes: t('confirm.ack.yes'), no: t('common.goBack') })) return;
  const r = await run({ key: `ack:${e.id}`, label: t('act.usageAck'), cmd: 'usage_ack', args: { id: e.id } });
  if (r.ok) s.usage = r.result;
}
</script>
<template>
  <div v-if="show" class="oui-stack" data-test="usage-card">
    <div role="alert" class="u1-live uc-alerts">
      <OuiBanner v-if="s.usageError" role="none" tone="error" :title="t('usage.loadError', { error: s.usageError })" />
      <OuiBanner v-if="u?.save_error" role="none" tone="error" :title="t('usage.saveError', { error: u.save_error })" />
      <OuiBanner v-if="u?.restore_notice" role="none" tone="warn" :title="t('usage.notice', { text: u.restore_notice })" />
    </div>
    <OuiBanner v-if="list.length" role="note" tone="warn" :title="tn('usage.banner', list.length)">
      {{ first }}
      <template #actions>
        <Button size="small" severity="secondary" :label="open ? t('usage.hide') : t('usage.review')" :aria-expanded="open" aria-controls="usage-list" data-focus-key="usage-review" data-test="usage-review" @click="open = !open">
          <template #icon><OuiIcon :icon="eye" :size="14" /></template></Button>
      </template>
    </OuiBanner>
    <OuiPanel v-if="open && list.length" id="usage-list" :icon="warning" tone="warn" flush aria-labelledby="usage-h">
      <template #title><span id="usage-h">{{ t('usage.title') }}</span></template>
      <template #meta><span class="oui-chip" data-tone="warn">{{ tn('usage.count', list.length) }}</span></template>
      <p class="oui-meta u1-pad">{{ t('usage.intro') }}</p>
      <div class="oui-table-wrap">
        <table class="u1-table">
          <thead><tr><th scope="col">{{ t('usage.col.file') }}</th><th scope="col">{{ t('usage.col.head') }}</th><th scope="col" class="oui-num">{{ t('usage.col.grams') }}</th>
            <th scope="col">{{ t('usage.col.spool') }}</th><th scope="col">{{ t('usage.col.when') }}</th><th scope="col">{{ t('usage.col.why') }}</th>
            <th scope="col" class="oui-end"><span class="oui-sr">{{ t('usage.col.action') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="e in list" :key="e.id">
              <td class="uc-file"><span class="oui-strong">{{ fileName(e) }}</span><div class="oui-meta">{{ e.printer_name || e.printer }}</div></td>
              <td><span class="u1-tool" :data-tool="(e.head ?? 0) + 1">T{{ (e.head ?? 0) + 1 }}</span></td>
              <td class="oui-num">{{ fmt.number(e.grams ?? 0, 1) }} g</td>
              <td :class="{ 'oui-muted': e.spool == null }">{{ e.spool != null ? '#' + e.spool : t('usage.noSpool') }}</td>
              <td>{{ when(e) }}</td>
              <td class="oui-meta uc-why">{{ e.error }}</td>
              <td class="oui-end"><Button size="small" severity="secondary" :label="t('usage.ack')" :loading="tracker.isBusy(`ack:${e.id}`)"
                          :aria-label="t('usage.ackLabel', { n: (e.head ?? 0) + 1, file: fileName(e) })" :data-focus-key="`ack:${e.id}`" @click="ack(e)">
                <template #icon><OuiIcon :icon="check" :size="14" /></template></Button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </OuiPanel>
    <div v-if="(open || !list.length) && (u?.pending.length || u?.acknowledged.length)" class="oui-stack uc-more">
      <p v-if="u?.pending.length" class="oui-meta">{{ tn('usage.tracking', u.pending.length) }}</p>
      <details v-if="u?.acknowledged.length" class="sc-tabs"><summary>{{ t('usage.recent', { total: u.acknowledged_total }) }}</summary>
        <ul class="oui-meta uc-recent"><li v-for="e in u.acknowledged" :key="e.id">{{ fileName(e) }} · T{{ (e.head ?? 0) + 1 }} · {{ fmt.number(e.grams ?? 0, 1) }} g ·
          {{ t('usage.checkedAt', { when: e.acknowledged_at ? fmt.dateTime(e.acknowledged_at) : t('usage.unknownTime') }) }}</li></ul></details>
    </div>
  </div>
</template>
<style>
.uc-file, .uc-why { overflow-wrap: anywhere; max-width: 260px; }
.uc-alerts:empty { display: none; }   /* no stack gap for an empty live region; it comes back with its first message */
.uc-more { padding-inline: var(--oui-s2); gap: var(--oui-s1); }
.uc-recent { margin: var(--oui-s1) 0 0; padding-inline-start: var(--oui-s4); }
</style>
