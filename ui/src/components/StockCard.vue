<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import { OuiBanner, OuiEmpty, OuiIcon, OuiLevel, OuiPanel, OuiSpool, OuiStatus, OuiToolbar, materialTone } from '../../shared/src/components';
import { boxes, link as linkIcon, refresh } from '../../shared/src/icons';
import { spoolFraction } from '../core/spool-level';
import { s, run, tracker, loadStock, loadSpools, busy, controlsOff, targetKnown, printerName, stockVisible } from '../app/store';
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
const blocker = computed<{ state: 'error' | 'loading' | 'offline' | 'empty'; text: string } | null>(() => {
  if (s.stockError) return { state: 'error', text: t('stock.failed', { error: s.stockError }) };
  if (!s.stock) return { state: 'loading', text: t('stock.loading') };
  if (sp.value!.state !== 'active') return { state: 'offline', text: sp.value!.detail ? t('common.paren', { a: tMaybe(`stock.peer.${sp.value!.state}`, sp.value!.text), b: sp.value!.detail }) : tMaybe(`stock.peer.${sp.value!.state}`, sp.value!.text) };
  const k = sk.value!;
  if (usable.value) return null;
  const text = k.code ? tMaybe(`stock.code.${k.code}`, k.text, { detail: k.detail ?? '' }) : k.text;
  return { state: k.state === 'error' ? 'error' : k.state === 'missing' ? 'empty' : 'offline', text };
});
const otherSpoolman = computed(() => !!usable.value && s.stock!.same_spoolman === false);
const isStale = computed(() => !!usable.value && sk.value!.state === 'stale');
/** Plain information, not a warning: a quiet line, not a bordered box. */
const viaPrinter = computed(() => usable.value && s.stock!.same_spoolman == null);
const rows = computed<Spool[]>(() => sk.value?.rows ?? []);
const materials = computed(() => [...new Set(rows.value.map(r => r.material).filter(Boolean))].sort().map(m => ({ value: m, label: m })));
const targetHead = computed(() => s.status?.heads[head.value]);
const shown = computed(() => {
  const needle = q.value.trim().toLowerCase();
  const fam = fit.value && targetHead.value?.loaded ? family(targetHead.value.type) : '';
  return rows.value.filter(r => (!mat.value || r.material === mat.value) && (!fam || family(r.material) === fam)
    && (!needle || [r.name, r.vendor, r.material, r.location, '#' + r.id].join(' ').toLowerCase().includes(needle)));
});
const bound = computed(() => boundHeads(s.bindings, s.stock?.bindings ?? {}));
/** Why linking is off, and where that is said: once for the page (no printer, busy), or in this panel (other Spoolman). */
const why = computed(() => (!targetKnown.value || !s.info ? t('stock.why.connect') : controlsOff.value ? controlsOff.value : busy.value ? t('stock.why.busy')
  : s.stock?.same_spoolman === false ? t('stock.why.spoolman') : ''));
const whyId = computed(() => (!why.value ? undefined : !targetKnown.value || !s.info || controlsOff.value || busy.value ? 'heads-why' : 'stock-why'));
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
  <OuiPanel v-if="stockVisible" :icon="boxes" tone="lime" flush aria-labelledby="stock-h" data-test="stock-card">
    <template #title><span id="stock-h">{{ t('stock.title') }}</span></template>
    <template v-if="usable" #meta>
      <OuiStatus v-if="isStale" id="stock-meta" state="stale">{{ t('stock.read', { version: sp?.version, age: fmt.ago(sk?.ts, s.now / 1000) }) }}</OuiStatus>
      <span v-else id="stock-meta">{{ t('stock.read', { version: sp?.version, age: fmt.ago(sk?.ts, s.now / 1000) }) }}</span>
    </template>
    <template #actions>
      <Button severity="secondary" size="small" :label="t('common.refresh')" :aria-label="t('stock.refresh')" :loading="s.stockLoading" data-focus-key="stock-refresh" @click="loadStock(true)">
        <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
    </template>

    <div role="status" aria-live="polite" class="sc-notes">
      <OuiEmpty v-if="blocker" compact :state="blocker.state" :icon="boxes" tone="lime" :title="blocker.text" />
      <OuiBanner :show="otherSpoolman" id="stock-why" role="none" data-test="stock-why" tone="error" dismissible dismiss-key="other-spoolman" :close-label="t('common.close')" :title="t('stock.blocked', { reason: t('stock.why.spoolman') })">{{ t('stock.otherSpoolman') }}</OuiBanner>
    </div>
    <template v-if="usable">
      <OuiToolbar class="sc-bar" :summary="t('stock.count', { shown: shown.length, n: rows.length })" :label="t('stock.searchLabel')">
        <InputText v-model="q" type="search" size="small" :placeholder="t('stock.search')" :aria-label="t('stock.searchLabel')" />
        <Select v-model="mat" :options="materials" option-label="label" option-value="value" show-clear size="small" :placeholder="t('stock.allMaterials')" :aria-label="t('stock.material')" />
        <label class="u1-inline" for="stock-fit"><Checkbox v-model="fit" input-id="stock-fit" binary />{{ t('stock.sameMaterial') }}</label>
        <template #end>
          <span class="u1-inline"><span id="stock-head-l">{{ t('stock.linkTo') }}</span>
            <Select v-model="head" :options="heads" option-label="label" option-value="value" size="small" aria-labelledby="stock-head-l" data-test="stock-head" /></span>
        </template>
      </OuiToolbar>
      <div class="sc-wrap u1-scroll">
        <table class="u1-table sc-table">
          <thead><tr><th scope="col">{{ t('stock.col.spool') }}</th><th scope="col" class="sc-mat">{{ t('stock.col.material') }}</th>
            <th scope="col" class="sc-loc">{{ t('stock.col.location') }}</th><th scope="col" class="sc-left oui-num">{{ t('stock.col.left') }}</th>
            <th scope="col" class="sc-act oui-end"><span class="oui-sr">{{ t('stock.col.action') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="r in shown" :key="r.id">
              <td><div class="sc-nm"><OuiSpool :color="r.colour" :colors="r.colours" :fraction="spoolFraction(r.remaining, r.initial)" :size="40" />
                <div class="sc-id"><p class="oui-truncate" :title="`${r.vendor} ${r.name}`"><span class="oui-strong">{{ r.name }}</span> <span class="oui-muted oui-num">#{{ r.id }}</span></p>
                  <p class="oui-meta sc-meta"><span v-if="bound[r.id]" class="oui-chip" data-tone="accent" data-solid>{{ t('stock.on', { n: bound[r.id].slice(1) }) }}</span>
                    <span v-if="r.use_first" class="oui-chip">{{ t('stock.useFirst') }}</span><span class="oui-truncate">{{ r.vendor }}</span></p></div></div></td>
              <td class="sc-mat"><span class="oui-chip" :data-tone="materialTone(r.material)">{{ r.material }}</span></td>
              <td class="sc-loc" :class="{ 'oui-muted': !r.location }">{{ r.location || '—' }}</td>
              <td class="sc-left oui-num"><div class="sc-amount"><span :class="{ 'u1-low': r.low }">{{ r.remaining == null ? '—' : fmt.grams(r.remaining) }}<template v-if="r.low"> · {{ t('stock.low') }}</template></span>
                <OuiLevel :fraction="spoolFraction(r.remaining, r.initial)" :tone="r.low ? 'low' : 'normal'" /></div></td>
              <td class="sc-act oui-end"><Button size="small" severity="secondary" text :label="t('stock.linkBtn', { n: head + 1 })" :disabled="!!why || tracker.isBusy(`bind:${head}`)" :aria-describedby="whyId"
                          :data-focus-key="`stock:${r.id}`" :data-stock="r.id" :aria-label="t('stock.linkLabel', { id: r.id, name: `${r.vendor} ${r.name}`, n: head + 1 })" @click="link(r)">
                <template #icon><OuiIcon :icon="linkIcon" :size="14" /></template></Button></td>
            </tr>
            <tr v-if="!shown.length"><td colspan="5" class="oui-muted">
              <template v-if="rows.length">{{ t('stock.noMatch') }} <Button text size="small" severity="secondary" :label="t('stock.clearFilters')" @click="clear" /></template>
              <template v-else>{{ t('stock.empty') }}</template></td></tr>
          </tbody>
        </table>
      </div>
    </template>
    <template #footer>
      <div class="sc-foot">
        <p v-if="isStale" class="u1-note" data-tone="warn" data-test="stock-stale">{{ t('stock.stale', { age: fmt.ago(sk?.ts, s.now / 1000) }) }}</p>
        <p v-if="viaPrinter" class="oui-meta" data-test="stock-via">{{ t('stock.viaPrinter') }}</p>
        <p v-if="usable && s.stock?.usage && s.stock.usage !== 'unknown'" class="oui-meta">{{ tMaybe(`stock.usage.${s.stock.usage}`, '') }}</p>
        <details class="sc-tabs"><summary>{{ t('stock.tabs.summary') }}</summary><p class="oui-meta">{{ t('stock.tabs.body') }}</p></details>
      </div>
    </template>
  </OuiPanel>
</template>

<style>
.sc-notes:empty { display: none; }
.sc-notes > .oui-banner { margin: var(--oui-s3) var(--oui-s3) 0; }
.sc-bar { border-bottom: 1px solid var(--oui-border); }
.sc-wrap { max-height: 420px; }
/* Fixed layout: a long spool name is cut, never widens the table. */
.sc-table { table-layout: fixed; min-width: 560px; }
.sc-mat { width: 92px; } .sc-loc { width: 120px; } .sc-left { width: 124px; } .sc-act { width: 132px; }
.sc-nm { display: flex; align-items: center; gap: var(--oui-s3); min-width: 0; }
.sc-id { display: grid; gap: 1px; min-width: 0; }
.sc-meta { display: flex; align-items: center; gap: var(--oui-s1); min-width: 0; }
.sc-amount { display: grid; gap: 4px; }
.sc-foot { display: grid; gap: var(--oui-s1); min-width: 0; }
.sc-tabs summary { cursor: pointer; font-size: var(--oui-text-sm); font-weight: 600; color: var(--oui-primary); }
.sc-tabs p { margin-top: var(--oui-s1); max-width: 96ch; }
</style>
