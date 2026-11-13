<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import SpoolFigure from './SpoolFigure.vue';
import LevelBar from './LevelBar.vue';
import { spoolFraction, spoolPaint } from '../core/spool-level';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import Message from 'primevue/message';
import Icon from './Icon.vue';
import { s, run, tracker, loadStock, loadSpools, busy, targetKnown, printerName, stockVisible } from '../app/store';
import { ask } from '../core/dialog';
import { t, tMaybe, fmt } from '../core/i18n';
import { family, boundHeads } from '../core/logic';
import type { Spool } from '../app/types';

const q = ref('');
const mat = ref<string | null>(null);
const fit = ref(false);
const head = ref(0);
const sp = computed(() => s.stock?.spooler);
const sk = computed(() => s.stock?.stock);
const usable = computed(() => !s.stockError && sp.value?.state === 'active' && sk.value && !['unavailable', 'missing', 'error', 'mismatch'].includes(sk.value.state));
/** Why the list isn't shown: peer state or list state, with its own severity (U09). */
const blocker = computed(() => {
  if (s.stockError) return { sev: 'error', text: t('stock.failed', { error: s.stockError }) };
  if (!s.stock) return { sev: 'secondary', text: t('stock.loading') };
  if (sp.value!.state !== 'active') return { sev: 'warn', text: tMaybe(`stock.peer.${sp.value!.state}`, sp.value!.text) + (sp.value!.detail ? ` (${sp.value!.detail})` : '') };
  const k = sk.value!;
  if (usable.value) return null;
  const text = k.code ? tMaybe(`stock.code.${k.code}`, k.text, { detail: k.detail ?? '' }) : k.text;
  return { sev: k.state === 'error' ? 'error' : k.state === 'missing' ? 'secondary' : 'warn', text };
});
/** Separate notes, blocking first (U09). */
const notes = computed(() => {
  if (!usable.value) return [];
  const out: { sev: string; text: string }[] = [];
  if (s.stock!.same_spoolman === false) out.push({ sev: 'error', text: t('stock.otherSpoolman') });
  if (sk.value!.state === 'stale') out.push({ sev: 'warn', text: t('stock.stale', { age: fmt.ago(sk.value!.ts, s.now / 1000) }) });
  if (s.stock!.same_spoolman == null) out.push({ sev: 'info', text: t('stock.viaPrinter') });
  return out;
});
const rows = computed<Spool[]>(() => sk.value?.rows ?? []);
const materials = computed(() => [...new Set(rows.value.map(r => r.material).filter(Boolean))].sort().map(m => ({ value: m, label: m })));
const targetHead = computed(() => s.status?.heads[head.value]);
const shown = computed(() => {
  const needle = q.value.trim().toLowerCase();
  const fam = fit.value && targetHead.value?.loaded ? family(targetHead.value.type) : '';
  return rows.value.filter(r => (!mat.value || r.material === mat.value) && (!fam || family(r.material) === fam)
    && (!needle || [r.name, r.vendor, r.material, r.location, '#' + r.id].join(' ').toLowerCase().includes(needle)));
});
const filtered = computed(() => !!(q.value.trim() || mat.value || fit.value));
const bound = computed(() => boundHeads(s.bindings, s.stock?.bindings ?? {}));
/** Visible reason when linking is off (U06/B-06): disabled buttons can't show a tooltip by keyboard. */
const why = computed(() => (!targetKnown.value || !s.info ? t('stock.why.connect') : busy.value ? t('stock.why.busy')
  : s.stock?.same_spoolman === false ? t('stock.why.spoolman') : ''));
const heads = [0, 1, 2, 3].map(h => ({ value: h, label: `T${h + 1}` }));
function clear() { q.value = ''; mat.value = null; fit.value = false; }

async function link(r: Spool) {
  const i = head.value, n = i + 1, key = sk.value?.key;
  if (!key || why.value) return;
  const force = !!(s.status?.heads[i]?.official || s.status?.rfid?.[i]);
  const name = `${r.vendor} ${r.name}`.trim();
  if (!await ask({ title: t('act.stockLink'), text: force ? t('confirm.bind.force', { n, id: r.id })
    : t('confirm.stockLink.text', { id: r.id, name, material: r.material, n, printer: printerName.value }),
    yes: t('stock.linkBtn', { n }), no: t('common.goBack'), danger: force })) return;
  const res = await run({ key: `bind:${i}`, label: t('act.stockLink'), cmd: 'stock_assign', args: { head: i, spool_id: r.id, key, force },
    okText: t('ok.bind', { n, id: r.id }), timeoutMs: 60000 });
  if (res.ok) { s.bindings = res.result.bindings; void loadSpools(true); }
  void loadStock(false);
}
</script>

<template>
  <section v-if="stockVisible" class="u1-card" aria-labelledby="stock-h" data-test="stock-card">
    <div class="u1-row sc-head">
      <h2 id="stock-h"><Icon name="icon/filament-spool" /> {{ t('stock.title') }}</h2>
      <span v-if="usable" class="oui-meta" id="stock-meta">{{ t('stock.meta', { version: sp?.version, n: rows.length, age: fmt.ago(sk?.ts, s.now / 1000) }) }}</span>
      <span class="u1-spacer" />
      <Button severity="secondary" outlined :label="t('stock.refresh')" :loading="s.stockLoading" data-focus-key="stock-refresh" @click="loadStock(true)" />
    </div>
    <div role="status" aria-live="polite" class="sc-notes">
      <Message v-if="blocker" :severity="blocker.sev">{{ blocker.text }}</Message>
      <Message v-for="nt in notes" :key="nt.text" :severity="nt.sev">{{ nt.text }}</Message>
      <Message v-if="usable && why" severity="warn" data-test="stock-why">{{ t('stock.blocked', { reason: why }) }}</Message>
    </div>
    <template v-if="usable">
      <div class="u1-row sc-filters">
        <InputText v-model="q" type="search" :placeholder="t('stock.search')" :aria-label="t('stock.searchLabel')" class="sc-q" />
        <Select v-model="mat" :options="materials" option-label="label" option-value="value" show-clear :placeholder="t('stock.allMaterials')" :aria-label="t('stock.material')" />
        <span class="u1-row"><Checkbox v-model="fit" input-id="stock-fit" binary /><label for="stock-fit">{{ t('stock.sameMaterial') }}</label></span>
        <span class="u1-spacer" />
        <label id="stock-head-l">{{ t('stock.linkTo') }}</label>
        <Select v-model="head" :options="heads" option-label="label" option-value="value" aria-labelledby="stock-head-l" data-test="stock-head" />
      </div>
      <div class="sc-wrap">
        <table class="u1-table">
          <thead><tr><th scope="col">{{ t('stock.col.spool') }}</th><th scope="col">{{ t('stock.col.material') }}</th><th scope="col">{{ t('stock.col.left') }}</th>
            <th scope="col" class="sc-loc">{{ t('stock.col.location') }}</th><th scope="col">{{ t('stock.col.action') }}</th></tr></thead>
          <tbody>
            <tr v-for="r in shown" :key="r.id">
              <td><span class="sc-nm"><SpoolFigure :paint="spoolPaint(r.colour, r.colours)" :fraction="spoolFraction(r.remaining, r.initial) ?? 1" :size="40" />
                <span><strong>{{ r.vendor }} {{ r.name }}</strong> <span class="oui-muted">#{{ r.id }}</span>
                  <span v-if="r.use_first" class="u1-pill sc-chip">{{ t('stock.useFirst') }}</span>
                  <span v-if="bound[r.id]" class="u1-pill sc-chip on">{{ t('stock.on', { n: bound[r.id].slice(1) }) }}</span></span></span></td>
              <td>{{ r.material }}</td>
              <td class="u1-num sc-left" :class="{ 'u1-warn': r.low }">{{ fmt.grams(r.remaining) }}<template v-if="r.low"> · {{ t('stock.low') }}</template>
                <LevelBar v-if="spoolFraction(r.remaining, r.initial) !== null" class="sc-bar" :pct="Math.round(spoolFraction(r.remaining, r.initial)! * 100)"
                          :paint="spoolPaint(r.colour, r.colours) || '#888'" :level="r.low ? 'low' : ''" /></td>
              <td class="sc-loc oui-muted">{{ r.location }}</td>
              <td><Button size="small" severity="secondary" outlined :disabled="!!why || tracker.isBusy(`bind:${head}`)" :data-focus-key="`stock:${r.id}`" :data-stock="r.id"
                          :aria-label="t('stock.linkLabel', { id: r.id, name: `${r.vendor} ${r.name}`, n: head + 1 })" @click="link(r)">
                <Icon name="icon/link" /><span>{{ t('stock.linkBtn', { n: head + 1 }) }}</span></Button></td>
            </tr>
            <tr v-if="!shown.length"><td colspan="5" class="oui-muted">
              <template v-if="rows.length">{{ t('stock.noMatch') }} <Button text size="small" :label="t('stock.clearFilters')" @click="clear" /></template>
              <template v-else>{{ t('stock.empty') }}</template></td></tr>
          </tbody>
        </table>
      </div>
      <p v-if="s.stock?.usage && s.stock.usage !== 'unknown'" class="oui-meta">{{ tMaybe(`stock.usage.${s.stock.usage}`, '') }}</p>
    </template>
    <details class="sc-tabs"><summary>{{ t('stock.tabs.summary') }}</summary><p>{{ t('stock.tabs.body') }}</p></details>
  </section>
</template>

<style scoped>
.sc-head h2 { margin: 0; display: flex; gap: 8px; align-items: center; }
.sc-notes { display: grid; gap: 8px; margin: 8px 0; }
.sc-notes:empty { display: none; }
.sc-filters { margin-bottom: 8px; }
.sc-q { min-width: 240px; }
.sc-wrap { max-height: 360px; overflow: auto; }
.sc-wrap thead th { position: sticky; top: 0; background: var(--oui-surface); z-index: 1; }
.sc-nm { display: flex; align-items: center; gap: 8px; min-width: 0; overflow-wrap: anywhere; }
.sc-chip { font-size: 12px; margin-left: 4px; }
.sc-chip.on { border-color: var(--p-primary-color); color: var(--p-primary-color); }
.sc-tabs { margin-top: 12px; }
.sc-tabs summary { cursor: pointer; color: var(--p-primary-color); }
.sc-tabs p { margin: 8px 0 0; }
@media (max-width: 640px) { .sc-loc { display: none; } .sc-q { flex: 1 1 100%; min-width: 0; } }

.sc-left { min-width: 96px; }
.sc-bar { margin-top: 4px; height: 6px; }
</style>
