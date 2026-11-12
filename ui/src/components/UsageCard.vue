<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import Message from 'primevue/message';
import Icon from './Icon.vue';
import { s, run, tracker } from '../app/store';
import { ask } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import type { UsageEntry } from '../app/types';

// U05: prints whose Spoolman update wasn't confirmed stay listed with their identity until the user marks them
// checked. Marking is local and audited by the plugin (usage_ack); nothing is booked again from here.
const u = computed(() => s.usage);
const list = computed(() => u.value?.unconfirmed ?? []);
const show = computed(() => !!(list.value.length || u.value?.save_error || u.value?.restore_notice || s.usageError));
const fileName = (e: UsageEntry) => (e.file ? e.file.split('/').pop() : '') || t('common.unknown');
const when = (e: UsageEntry) => (e.at ? fmt.dateTime(e.at) : t('usage.unknownTime'));

async function ack(e: UsageEntry) {
  const n = (e.head ?? 0) + 1;
  if (!await ask({ title: t('confirm.ack.title'), text: t('confirm.ack.text', { grams: fmt.number(e.grams ?? 0, 1), n, file: fileName(e) }),
    yes: t('confirm.ack.yes'), no: t('common.goBack') })) return;
  const r = await run({ key: `ack:${e.id}`, label: t('act.usageAck'), cmd: 'usage_ack', args: { id: e.id } });
  if (r.ok) s.usage = r.result;
}
</script>
<template>
  <section v-if="show" class="u1-card uc" aria-labelledby="usage-h" data-test="usage-card">
    <h2 id="usage-h"><Icon name="icon/warning" /> {{ t('usage.title') }}
      <span v-if="list.length" class="u1-pill">{{ tn('usage.count', list.length) }}</span></h2>
    <div role="alert" class="uc-notes">
      <Message v-if="s.usageError" severity="error">{{ t('usage.loadError', { error: s.usageError }) }}</Message>
      <Message v-if="u?.save_error" severity="error">{{ t('usage.saveError', { error: u.save_error }) }}</Message>
      <Message v-if="u?.restore_notice" severity="warn">{{ t('usage.notice', { text: u.restore_notice }) }}</Message>
    </div>
    <template v-if="list.length">
      <p class="uc-intro">{{ t('usage.intro') }}</p>
      <div class="oui-table-wrap">
        <table class="u1-table">
          <thead><tr><th scope="col">{{ t('usage.col.file') }}</th><th scope="col">{{ t('usage.col.head') }}</th><th scope="col">{{ t('usage.col.grams') }}</th>
            <th scope="col">{{ t('usage.col.spool') }}</th><th scope="col">{{ t('usage.col.when') }}</th><th scope="col">{{ t('usage.col.why') }}</th>
            <th scope="col">{{ t('usage.col.action') }}</th></tr></thead>
          <tbody>
            <tr v-for="e in list" :key="e.id">
              <td class="uc-file">{{ fileName(e) }}<div class="oui-meta">{{ e.printer_name || e.printer }}</div></td>
              <td>T{{ (e.head ?? 0) + 1 }}</td>
              <td class="u1-num">{{ fmt.number(e.grams ?? 0, 1) }} g</td>
              <td>{{ e.spool != null ? '#' + e.spool : t('usage.noSpool') }}</td>
              <td>{{ when(e) }}</td>
              <td class="oui-meta uc-why">{{ e.error }}</td>
              <td><Button size="small" severity="secondary" outlined :label="t('usage.ack')" :loading="tracker.isBusy(`ack:${e.id}`)"
                          :aria-label="t('usage.ackLabel', { n: (e.head ?? 0) + 1, file: fileName(e) })" :data-focus-key="`ack:${e.id}`" @click="ack(e)" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <p v-if="u?.pending.length" class="oui-meta">{{ tn('usage.tracking', u.pending.length) }}</p>
    <details v-if="u?.acknowledged.length" class="uc-recent"><summary>{{ t('usage.recent', { total: u.acknowledged_total }) }}</summary>
      <ul><li v-for="e in u.acknowledged" :key="e.id">{{ fileName(e) }} · T{{ (e.head ?? 0) + 1 }} · {{ fmt.number(e.grams ?? 0, 1) }} g ·
        {{ t('usage.checkedAt', { when: e.acknowledged_at ? fmt.dateTime(e.acknowledged_at) : t('usage.unknownTime') }) }}</li></ul></details>
  </section>
</template>
<style scoped>
.uc { border-color: var(--oui-warning); }
.uc h2 { flex-wrap: wrap; }
.uc-notes { display: grid; gap: 8px; } .uc-notes:empty { display: none; }
.uc-intro { margin: 8px 0; }
.uc-file, .uc-why { overflow-wrap: anywhere; max-width: 260px; }
.uc-recent summary { cursor: pointer; color: var(--p-primary-color); }
</style>
