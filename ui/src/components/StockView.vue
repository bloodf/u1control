<script setup lang="ts">
// The Stock tab: Spooler's Spoolman stock, linked to this U1's toolheads. Choose the toolhead once, in the rail; every
// row then has one action, named with it. Every link still checks the spool in Spoolman and asks first.
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import VirtualScroller from 'primevue/virtualscroller';
import { longList, OuiBanner, OuiEmpty, OuiHint, OuiIcon, OuiLevel, OuiPageHeader, OuiPanel, OuiSpool, OuiStatus, OuiToolbar } from '@orca-plugins/ui-foundation/src/components';
import { boxes, link as linkIcon, refresh, settings as settingsIcon } from '@orca-plugins/ui-foundation/src/icons';
import { headColours, headFraction, levelTone, present, spoolFraction } from '../core/spool-level';
import { s, run, tracker, loadStock, loadSpools, busy, controlsOff, targetKnown, printerName, reqStatus, openSettings } from '../app/store';
import { ask } from '../core/dialog';
import { t, tn, tMaybe, fmt } from '../core/i18n';
import { family, boundHeads } from '../core/logic';
import type { Spool } from '../app/types';

const q = ref('');
const mat = ref<string | null>(null);
const fit = ref(false);
const head = ref(0);
const sp = computed(() => s.stock?.spooler);
const sk = computed(() => s.stock?.stock);
/** Spooler shares no list, so the plugin lists U1 Control's own Spoolman read ("own"), or says why it can't. */
const own = computed(() => sk.value?.code === 'own');
const ownish = computed(() => ['own', 'no_spoolman', 'own_error'].includes(sk.value?.code ?? ''));
const usable = computed(() => !s.stockError && !!sk.value && (own.value
  || (sp.value?.state === 'active' && !['unavailable', 'missing', 'error', 'mismatch'].includes(sk.value.state))));
/** Why the list isn't shown: peer state or list state, with its own severity (U09). An error is a plain sentence with what
 * went wrong under it; no spools at all is the empty state, not a list with a Link-to rail. */
const blocker = computed<{ state: 'error' | 'loading' | 'offline' | 'empty'; title: string; text?: string } | null>(() => {
  if (s.stockError) return { state: 'error', title: t('stock.failed'), text: s.stockError };
  if (!s.stock) return { state: 'loading', title: t('stock.loading') };
  if (sp.value!.state !== 'active' && !ownish.value) return { state: 'offline', title: sp.value!.detail ? t('common.paren', { a: tMaybe(`stock.peer.${sp.value!.state}`, sp.value!.text), b: sp.value!.detail }) : tMaybe(`stock.peer.${sp.value!.state}`, sp.value!.text) };
  const k = sk.value!;
  if (usable.value) return k.rows?.length ? null : { state: 'empty', title: t('stock.empty') };
  const text = k.code ? tMaybe(`stock.code.${k.code}`, k.text, { detail: k.detail ?? '' }) : k.text;
  return k.state === 'error' ? { state: 'error', title: t('stock.failed'), text } : { state: k.state === 'missing' ? 'empty' : 'offline', title: text };
});
const otherSpoolman = computed(() => !!usable.value && s.stock!.same_spoolman === false);
/** The U1 has no Spoolman (no URL, none on the printer): a link would fail, so it is off with the reason. */
const noSpoolman = computed(() => !!usable.value && !otherSpoolman.value && reqStatus('spoolman') === 'missing');
const isStale = computed(() => !!usable.value && sk.value!.state === 'stale');
/** "30 spools · updated 31 s ago": what the list holds and how fresh it is, not which plugin read it. */
const meta = computed(() => [tn('stock.spools', rows.value.length), sk.value?.ts ? t('stock.updated', { age: fmt.ago(sk.value.ts, s.now / 1000) }) : ''].filter(Boolean).join(' · '));
/** Plain information, not a warning: a quiet line, not a bordered box. */
const viaPrinter = computed(() => usable.value && s.stock!.same_spoolman == null && (!own.value || sk.value?.origin === 'printer'));
const rows = computed<Spool[]>(() => sk.value?.rows ?? []);
const materials = computed(() => [...new Set(rows.value.map(r => r.material).filter(Boolean))].sort().map(m => ({ value: m, label: m })));
const targetHead = computed(() => s.status?.heads[head.value]);
const shown = computed(() => {
  const needle = q.value.trim().toLowerCase();
  const fam = fit.value && targetHead.value?.loaded ? family(targetHead.value.type) : '';
  // Empty spools (0 g) last; the rest keep Spoolman's order.
  return rows.value.filter(r => (!mat.value || r.material === mat.value) && (!fam || family(r.material) === fam)
    && (!needle || [r.name, r.vendor, r.material, r.location, '#' + r.id].join(' ').toLowerCase().includes(needle)))
    .sort((a, b) => Number(a.remaining === 0) - Number(b.remaining === 0));
});
// Past about 300 rows only the rows in view are drawn (the foundation's longList, as in the toolhead spool chooser); each row
// is then exactly ROW px tall. A shorter list stays a plain table.
const ROW = 56, LONG_STOCK = 300;
const virt = computed(() => (shown.value.length > LONG_STOCK ? longList(shown.value.length, ROW) : undefined));
const bound = computed(() => boundHeads(s.bindings, s.stock?.bindings ?? {}));
/** Why linking is off, and where that is said: once for the page (no printer, busy), or in this panel (other Spoolman). */
const why = computed(() => (!targetKnown.value || !s.info ? t('stock.why.connect') : controlsOff.value ? controlsOff.value : busy.value ? t('stock.why.busy')
  : s.stock?.same_spoolman === false ? t('stock.why.spoolman') : noSpoolman.value ? t('stock.why.noSpoolman') : ''));
const whyId = computed(() => (!why.value ? undefined : !targetKnown.value || !s.info || controlsOff.value || busy.value ? 'heads-why' : 'stock-why'));
// The places a spool can go: the four toolheads, each with what is in it now (its linked Spoolman spool, else what the printer reports).
const targets = computed(() => [0, 1, 2, 3].map(i => {
  const h = s.status?.heads[i], id = s.bindings[String(i)];
  const sp = id == null ? null : s.spools.find(x => x.id === id) ?? null;
  return { i, n: (i + 1) as 1 | 2 | 3 | 4, loaded: present(h), colour: sp?.colour || h?.colour || null, colours: headColours(sp, h),
    fraction: headFraction(present(h), sp), name: sp?.name || [h?.type, h?.sub_type].filter(Boolean).join(' ') || (h?.unnamed ? t('heads.unnamed') : ''),
    meta: [sp?.material || h?.vendor, sp?.remaining != null ? fmt.grams(sp.remaining) : ''].filter(Boolean).join(' · ') };
}));
function onTargetKey(e: KeyboardEvent) {
  const d = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
  if (!d) return;
  e.preventDefault();
  head.value = (head.value + d + 4) % 4;
  (e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-stock-target="${head.value}"]`)?.focus();
}
function clear() { q.value = ''; mat.value = null; fit.value = false; }
const linkedHere = (r: Spool) => bound.value[r.id] === `T${head.value + 1}`;
// The whole row links, as its button does (the button shows on hover and focus); a press on a control in it is its own.
function onRow(r: Spool, e: MouseEvent) {
  if (linkedHere(r) || why.value || tracker.isBusy(`bind:${head.value}`) || (e.target as Element).closest('button, a, input')) return;
  void link(r);
}

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
  <div class="u1-head">
    <OuiPageHeader :title="t('stock.title')">
      <template v-if="usable" #meta>
        <OuiStatus v-if="isStale" id="stock-meta" state="stale" :title="t('stock.stale', { age: fmt.ago(sk?.ts, s.now / 1000) })" data-test="stock-stale">{{ meta }}</OuiStatus>
        <span v-else id="stock-meta" data-test="stock-meta">{{ meta }}</span>
      </template>
      <template #actions>
        <!-- What sat under the stock list: how Spoolman is reached, who records filament use, why there are two tabs. -->
        <OuiHint end :label="t('stock.about')"><span class="sv-about" data-test="stock-about">
          <span v-if="isStale">{{ t('stock.stale', { age: fmt.ago(sk?.ts, s.now / 1000) }) }}</span>
          <span v-if="viaPrinter" data-test="stock-via">{{ t('stock.viaPrinter') }}</span>
          <span v-if="usable && s.stock?.usage && s.stock.usage !== 'unknown'">{{ tMaybe(`stock.usage.${s.stock.usage}`, '') }}</span>
          <details class="u1-details"><summary>{{ t('stock.tabs.summary') }}</summary><span>{{ t('stock.tabs.body') }}</span></details>
        </span></OuiHint>
        <Button severity="secondary" :label="t('common.refresh')" :aria-label="t('stock.refresh')" :loading="s.stockLoading" data-focus-key="stock-refresh" @click="loadStock(true)">
          <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
      </template>
    </OuiPageHeader>
    <div id="u1-banner-stock" />
    <div role="status" aria-live="polite" class="u1-live sc-notes">
      <OuiBanner :show="otherSpoolman" id="stock-why" role="none" data-test="stock-why" tone="error" dismissible dismiss-key="other-spoolman" :close-label="t('common.close')" :title="t('stock.blocked', { reason: t('stock.why.spoolman') })">{{ t('stock.otherSpoolman') }}</OuiBanner>
      <OuiBanner :show="noSpoolman" id="stock-why" role="none" data-test="stock-why" tone="warn" dismissible dismiss-key="no-spoolman" :close-label="t('common.close')" :title="t('stock.blocked', { reason: t('stock.why.noSpoolman') })">{{ t('stock.noSpoolman') }}</OuiBanner>
    </div>
  </div>

  <!-- No list to show: the centred empty state in the list's place, saying why; an error offers its ways out. -->
  <OuiPanel v-if="blocker" flush class="sv-empty" data-test="stock-card">
    <div role="status" aria-live="polite"><OuiEmpty :state="blocker.state" :icon="boxes" tone="lime" :title="blocker.title" :text="blocker.text">
      <template v-if="blocker.state === 'error'" #actions>
        <Button size="small" :label="t('common.retry')" :loading="s.stockLoading" data-test="stock-retry" @click="loadStock(true)"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        <Button severity="secondary" size="small" :label="t('common.openSettings')" data-test="stock-settings" @click="openSettings('connection')"><template #icon><OuiIcon :icon="settingsIcon" :size="14" /></template></Button>
      </template>
    </OuiEmpty></div>
  </OuiPanel>
  <div v-else class="oui-split" data-rail data-test="stock-card">
    <OuiPanel :icon="linkIcon" :title="t('stock.linkTo')" :hint="t('stock.linkHint')" :hint-label="t('stock.linkAbout')">
      <div class="sv-targets" role="radiogroup" :aria-label="t('stock.linkTo')" data-test="stock-head" @keydown="onTargetKey">
        <button v-for="x in targets" :key="x.i" type="button" role="radio" class="sv-target" :aria-checked="head === x.i" :tabindex="head === x.i ? 0 : -1" :data-stock-target="x.i" @click="head = x.i">
          <span class="oui-slot-badge oui-num" :data-tool="x.n">T{{ x.n }}</span>
          <OuiSpool :color="x.loaded ? x.colour : null" :colors="x.loaded ? x.colours : null" :fraction="x.fraction" :size="32" />
          <span v-if="x.loaded" class="sv-target-id"><span class="oui-strong oui-truncate">{{ x.name || t('common.unknown') }}</span><span class="oui-meta oui-num oui-truncate">{{ x.meta }}</span></span>
          <span v-else class="sv-target-id oui-muted">{{ s.status ? t('heads.empty') : t('common.unknown') }}</span>
        </button>
      </div>
    </OuiPanel>

    <OuiPanel flush class="sv-list" :aria-label="t('stock.title')">
      <OuiToolbar :summary="t('stock.count', { shown: shown.length, n: rows.length })" :label="t('stock.searchLabel')">
        <InputText v-model="q" type="search" size="small" :placeholder="t('stock.search')" :aria-label="t('stock.searchLabel')" />
        <Select v-model="mat" :options="materials" option-label="label" option-value="value" show-clear size="small" :placeholder="t('stock.allMaterials')" :aria-label="t('stock.material')" />
        <label class="u1-inline" for="stock-fit"><Checkbox v-model="fit" input-id="stock-fit" binary />{{ t('stock.sameAs', { n: head + 1 }) }}</label>
      </OuiToolbar>
      <div class="sc-wrap" :data-virtual="virt ? '' : undefined">
        <VirtualScroller :items="shown" :item-size="virt?.itemSize ?? ROW" :disabled="!virt" class="sc-scroll">
          <template #content="{ items, contentRef, contentStyle, styleClass }">
        <table :ref="contentRef" :class="['u1-table sc-table', styleClass]" :style="contentStyle">
          <thead><tr><th scope="col">{{ t('stock.col.spool') }}</th><th scope="col" class="sc-mat">{{ t('stock.col.material') }}</th>
            <th scope="col" class="sc-loc">{{ t('stock.col.location') }}</th><th scope="col" class="sc-left oui-num">{{ t('stock.col.left') }}</th>
            <th scope="col" class="sc-act oui-end"><span class="oui-sr">{{ t('stock.col.action') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="r in (items as Spool[])" :key="r.id" class="sc-row" :data-row="r.id" @click="onRow(r, $event)">
              <td><div class="sc-nm"><OuiSpool :color="r.colour" :colors="r.colours" :fraction="spoolFraction(r.remaining, r.initial)" :size="40" />
                <div class="sc-id"><p class="oui-truncate" :title="`${r.vendor} ${r.name}`"><span class="oui-strong">{{ r.name }}</span> <span class="oui-muted oui-num">#{{ r.id }}</span><span v-if="r.use_first" class="oui-chip sc-first" data-test="use-first">{{ t('stock.useFirst') }}</span></p>
                  <p class="oui-meta oui-truncate">{{ r.vendor }}</p></div></div></td>
              <td class="sc-mat"><span class="oui-chip">{{ r.material }}</span></td>
              <td class="sc-loc"><span class="sc-where"><span v-if="bound[r.id]" class="oui-slot-badge oui-num" :data-tool="bound[r.id].slice(1)" :title="t('stock.on', { n: bound[r.id].slice(1) })">{{ bound[r.id] }}</span>
                <span v-if="r.location" class="oui-truncate" :title="r.location">{{ r.location }}</span><span v-else-if="!bound[r.id]" class="oui-muted">—</span></span></td>
              <td class="sc-left oui-num"><div class="sc-amount"><span v-if="r.remaining === 0" class="sc-gone" :data-gone="r.id">{{ t('stock.spoolEmpty') }}</span><span v-else :class="{ 'u1-low': r.low }">{{ r.remaining == null ? t('common.unknown') : fmt.grams(r.remaining) }}<template v-if="r.low"> · {{ t('stock.low') }}</template></span>
                <OuiLevel :fraction="spoolFraction(r.remaining, r.initial)" :tone="levelTone(spoolFraction(r.remaining, r.initial), r.low)" /></div></td>
              <td class="sc-act oui-end">
                <OuiStatus v-if="linkedHere(r)" state="ok" :data-linked="r.id">{{ t('stock.linked') }}</OuiStatus>
                <Button v-else size="small" severity="secondary" class="sc-link" :label="t('stock.linkBtn', { n: head + 1 })" :disabled="!!why || tracker.isBusy(`bind:${head}`)" :aria-describedby="whyId"
                        :data-focus-key="`stock:${r.id}`" :data-stock="r.id" :aria-label="t('stock.linkLabel', { id: r.id, name: `${r.vendor} ${r.name}`, n: head + 1 })" @click="link(r)">
                  <template #icon><OuiIcon :icon="linkIcon" :size="14" /></template></Button></td>
            </tr>
            <tr v-if="!shown.length"><td colspan="5" class="oui-muted">{{ t('stock.noMatch') }} <Button text size="small" severity="secondary" :label="t('stock.clearFilters')" @click="clear" /></td></tr>
          </tbody>
        </table>
          </template>
        </VirtualScroller>
      </div>
    </OuiPanel>
  </div>
</template>

<style>
/* The rail: where a spool can go. The chosen place is the selected row, in OrcaSlicer's teal. */
/* One column in the rail; when the rail sits above the list (narrow page) the four go side by side. */
.sv-targets { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: var(--oui-s1); }
.sv-target { display: flex; align-items: center; gap: var(--oui-s2); width: 100%; min-height: 48px; padding: 6px var(--oui-s2); border: 0; border-radius: var(--oui-radius); text-align: start;
  font: inherit; color: var(--oui-text); background: none; cursor: pointer; box-shadow: inset 0 0 0 1px var(--oui-border); }
.sv-target:hover { background: var(--oui-raised); }
.sv-target[aria-checked='true'] { background: var(--oui-primary-soft); box-shadow: inset 0 0 0 2px var(--oui-primary-mark); }
.sv-target-id { display: grid; min-width: 0; }
.sv-about { display: grid; gap: var(--oui-s2); }
/* The list fills the window under the bars (app bar, page header, one banner) and scrolls inside, so the toolbar and
   the rail stay in view. */
.sv-list { max-height: calc(100vh - 172px); min-height: 320px; }
@supports (height: 100dvh) { .sv-list { max-height: calc(100dvh - 172px); } }
.sv-list > .oui-panel-body { display: flex; flex-direction: column; min-height: 0; }
.sc-wrap { flex: 1 1 auto; min-height: 0; overflow: auto; border-top: 1px solid var(--oui-border); }
/* Fixed layout: a long spool name is cut, never widens the table. */
.sc-table { table-layout: fixed; min-width: 600px; }
.sc-mat { width: 92px; } .sc-loc { width: 140px; } .sc-left { width: 124px; } .sc-act { width: 140px; }
.sc-nm { display: flex; align-items: center; gap: var(--oui-s3); min-width: 0; }
.sc-id { display: grid; gap: 1px; min-width: 0; }
.sc-meta, .sc-where { display: flex; align-items: center; gap: var(--oui-s1); min-width: 0; }
.sc-amount { display: grid; gap: 4px; }
.sc-gone { color: var(--oui-danger); font-weight: 600; }
.sc-first { margin-inline-start: var(--oui-s2); }
.sv-empty .oui-empty { min-height: 320px; }
/* The link shows on the row under the pointer or holding the focus (Tab still reaches it); the row itself links too. Touch
   screens have no hover: there it always shows. */
.sc-row:has(.sc-link:not(:disabled)) { cursor: pointer; }
.sc-table .sc-link { opacity: 0; }
.sc-row:hover .sc-link, .sc-row:focus-within .sc-link { opacity: 1; }
@media (hover: none) { .sc-table .sc-link { opacity: 1; } }
/* Long list: the scroller scrolls in place of the wrapper, every row exactly ROW px. */
.sc-wrap[data-virtual] { display: flex; flex-direction: column; overflow: hidden; }
.sc-wrap[data-virtual] > .sc-scroll { flex: 1 1 auto; min-height: 0; }
.sc-wrap[data-virtual] .sc-table tbody tr { height: 56px; }
</style>
