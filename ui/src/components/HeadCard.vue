<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import { fuzzyFilter, longList, OuiHint, OuiIcon, OuiLevel, OuiPresetMatch, OuiSlot, OuiSpool, OuiStatus } from '@orca-plugins/ui-foundation/src/components';
import { download, edit as editIcon, home as parkIcon, rfid as rfidIcon, upload } from '@orca-plugins/ui-foundation/src/icons';
import HeaterControl from './HeaterControl.vue';
import { config } from '../app/settings';
import { s, run, tracker, busy, controlsOff, loadSpools, relink, guidedWhy, pickPreset } from '../app/store';
import { reasonTexts } from '../core/match';
import type { MessageKey } from '../core/messages';
import { ask } from '../core/dialog';
import { t, fmt, tMaybe } from '../core/i18n';
import { family } from '../core/logic';
import { AT_INLET, headColours, headFraction, levelTone, present, spoolFraction } from '../core/spool-level';
import type { Spool, Tag } from '../app/types';

// One toolhead as a neutral card: a 4 px strip of its filament's colour, the spool, what is left of the linked
// Spoolman spool, the spool chooser, its nozzle heater, and Load / Unload / Park (when picked up) / Edit / Read RFID.
const props = defineProps<{ index: number }>();
const i = props.index, n = i + 1;
const TYPES = ['PLA', 'PLA+', 'PLA-CF', 'PETG', 'PETG-CF', 'PCTG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'PC', 'PVA', 'HIPS'];

const head = computed(() => s.status?.heads[i]);
const tag = computed<Tag | null>(() => s.status?.rfid?.[i] ?? null);
const feed = computed(() => s.status?.feed?.[i] ?? {});
const active = computed(() => !!s.status?.extruders[i]?.active);
// Filament in the head, named or not (a spool nobody has named reports NONE, but the head is not empty).
const has = computed(() => present(head.value));
// The feeder knows whether the filament went all the way into the toolhead (load_finish) or only waits at the
// inlet (preload_finish, e.g. after Unload): the RFID tag and filament_exist stay set either way.
const notInHead = computed(() => has.value && AT_INLET.includes(feed.value.state || ''));
const feedText = computed(() => (feed.value.state ? tMaybe(`heads.feedState.${feed.value.state}`, feed.value.state) : '—'));
// On the carriage (park detector ACTIVATE): offer Park, e.g. after a manual bed mesh left the head picked up.
const picked = computed(() => !!s.status?.extruders[i]?.picked);
const tagged = computed(() => !!(head.value?.official || tag.value));
const tagText = computed(() => {
  const g = tag.value;
  if (!g) return '';
  const temp = g.hotend_min || g.hotend_max ? `${g.hotend_min || '?'}–${g.hotend_max || '?'} °C` : '';
  return [[g.vendor || g.manufacturer, g.type, g.sub_type].filter(Boolean).join(' '), temp,
    g.bed_temp ? t('heads.tagBed', { temp: g.bed_temp }) : '', g.sku ? `SKU ${g.sku}` : ''].filter(Boolean).join(' · ');
});
const why = computed(() => (guidedWhy.value ? 'heads-why' : undefined));
const offWhy = computed(() => (controlsOff.value ? 'heads-why' : undefined));

async function load() {
  if (!await ask({ title: t('act.load', { n }), text: t('confirm.load.text', { n }), yes: t('confirm.load.yes', { n }), no: t('common.goBack') })) return;
  await run({ key: `load:${i}`, label: t('act.load', { n }), cmd: 'load', args: { head: i }, okText: t('ok.load', { n }), timeoutMs: 120000 });
}
async function unload() {
  if (!await ask({ title: t('act.unload', { n }), text: t('confirm.unload.text', { n }), yes: t('confirm.unload.yes', { n }), no: t('common.goBack') })) return;
  await run({ key: `unload:${i}`, label: t('act.unload', { n }), cmd: 'unload', args: { head: i }, okText: t('ok.unload', { n }), timeoutMs: 120000 });
}
async function park() {
  if (!await ask({ title: t('act.park', { n }), text: t('confirm.park.text', { n }), yes: t('confirm.park.yes', { n }), no: t('common.goBack') })) return;
  await run({ key: `park:${i}`, label: t('act.park', { n }), cmd: 'park', args: { head: i }, okText: t('ok.park', { n }), timeoutMs: 120000 });
}
const rfid = () => run({ key: `rfid:${i}`, label: t('act.rfid', { n }), cmd: 'reread_rfid', args: { head: i }, okText: t('ok.rfid', { n }) });

// ---------------------------------------------------------------- edit form (survives status refreshes)
const editing = ref(false);
const form = reactive({ vendor: '', type: 'PLA', sub: '', colour: '#ffffff' });
function startEdit() {
  const h = head.value;
  Object.assign(form, { vendor: h?.vendor || 'Generic', type: h?.type || 'PLA', sub: h?.sub_type || 'Basic', colour: h?.colour || '#ffffff' });
  editing.value = true;
}
async function saveEdit() {
  if (guidedWhy.value) return;
  if (tagged.value && !await ask({ title: t('edit.title', { n }),
    text: t('confirm.overwrite.text', { n, kind: head.value?.official ? t('edit.official') : t('edit.tagged') }),
    yes: t('confirm.overwrite.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: `edit:${i}`, label: t('act.setFilament', { n }), cmd: 'set_filament', timeoutMs: 60000,
    args: { head: i, vendor: form.vendor, type: form.type, sub_type: form.sub, colour: form.colour, force: tagged.value }, okText: t('ok.setFilament', { n }) });
  if (r.ok) editing.value = false;
}

// ---------------------------------------------------------------- Spoolman spool
const bound = computed(() => s.bindings[String(i)] ?? null);
// The linked Spoolman spool, when there is one: its colour(s) and how much is left draw the spool and the bar; else the
// printer's own colours (every colour of a multi-colour spool, as segments).
const linked = computed(() => (bound.value != null ? s.spools.find(x => x.id === bound.value) ?? null : null));
const colours = computed(() => headColours(linked.value, head.value));
// Filament left (headFraction), given to OuiSlot as remaining/initial; null when unknown, which draws the full reel with
// the unknown badge. The weight line below is ours.
const fraction = computed(() => headFraction(has.value, linked.value));
const grams = (v: number) => Math.round(v).toLocaleString(document.documentElement.lang || undefined);
const label = (sp: Spool) => t('pick.option', { id: sp.id, vendor: sp.vendor, name: sp.name, material: sp.material, grams: fmt.grams(sp.remaining) });
// The chooser's search: brand, name and material by fuzzyFilter (foundation: case and accents ignored, letters in order, best
// first); a spool's ID only ever matches exactly: "12" or "#12" lists that spool and nothing fuzzy (a bare number is an ID, so a
// brand like "3D" is typed with a letter, "3d x"). While it is typed the list is only the hits, without "no spool" (Enter on the
// first hit must never unlink), and nothing is bound until one is chosen.
// ponytail: Select still runs its own "contains" pass; every option carries the typed text as `q` so it keeps all of ours.
const query = ref('');
const idQuery = computed(() => /^#?(\d+)$/.exec(query.value.trim()));
const hits = computed(() => {
  const m = idQuery.value;
  const byId = m ? s.spools.filter(sp => sp.id === Number(m[1])) : [];
  const fuzzy = m ? [] : fuzzyFilter(s.spools, query.value, sp => [sp.vendor, sp.name, sp.material].filter(Boolean).join(' ')).map(r => r.item);
  return [...byId, ...fuzzy.filter(sp => !byId.includes(sp))];
});
// The material family on its own: a status refresh gives the head a new object every 2 s, and the 2000-spool list below must
// not be rebuilt for it (only a different family, the spools or the search do that).
const fam = computed(() => (head.value?.type ? family(head.value.type) : ''));
const groups = computed(() => {
  const searching = !!query.value.trim();
  const list = searching ? hits.value : s.spools;
  const fit: Spool[] = [], rest: Spool[] = [];
  for (const sp of list) (!fam.value || family(sp.material) === fam.value ? fit : rest).push(sp);
  const opt = (sp: Spool) => ({ value: sp.id, label: label(sp), sp, q: query.value });
  return searching
    ? [...(fit.length ? [{ label: t('pick.fit'), items: fit.map(opt) }] : []), ...(rest.length ? [{ label: t('pick.other'), items: rest.map(opt) }] : [])]
    : [
      { label: t('pick.fit'), items: [{ value: 0, label: t('pick.none'), sp: null, q: '' }, ...fit.map(opt)] },
      ...(rest.length ? [{ label: t('pick.other'), items: rest.map(opt) }] : []),
    ];
});
const groupRows = computed(() => groups.value.reduce((n, g) => n + 1 + g.items.length, 0));
async function choose(id: number | null) {
  if (!id) {
    const was = bound.value;
    if (was == null) return;
    if (!await ask({ title: t('act.unbind', { n }), text: t('confirm.unbind.text', { id: was, n }), yes: t('confirm.unbind.yes'), no: t('common.goBack') })) return;
    await relink(i, null, () => run({ key: `bind:${i}`, label: t('act.unbind', { n }), cmd: 'unbind_spool', args: { head: i }, okText: t('ok.unbind', { n }) }));
    return;
  }
  const force = tagged.value;
  if (!await ask({ title: t('act.bind', { n }), text: force ? t('confirm.bind.force', { n, id }) : t('confirm.bind.text', { n, id }),
    yes: t('confirm.bind.yes', { n }), no: t('common.goBack'), danger: force })) return;
  await relink(i, id, () => run({ key: `bind:${i}`, label: t('act.bind', { n }), cmd: 'bind_spool', args: { head: i, spool_id: id, force }, okText: t('ok.bind', { n, id }), timeoutMs: 60000 }));
}
const spoolOf = (id: number) => s.spools.find(x => x.id === id) ?? null;
// The OrcaSlicer preset Apply to project filaments gives this head, why, and Change (remembered by the plugin).
const match = computed(() => s.matches[String(i)] ?? null);
// Settings > Connection "Show the matched preset": off hides the block; Apply to project filaments still uses the match.
const showMatch = computed(() => config.value?.settings?.show_preset_match !== false);
const words = (reasons: unknown) => reasonTexts(reasons, (code, v) => t(`match.r.${code}` as MessageKey, { v }));
const BADGES: Record<string, MessageKey> = { remembered: 'match.remembered', linked: 'match.linked', spooler: 'match.spooler' };
const candidates = computed(() => (!match.value || match.value.source === 'linked' ? [] : [
  ...match.value.candidates.map(c => ({ name: c.shown ?? c.name, score: c.score, reasons: words(c.reasons) })),
  ...(match.value.ofd ?? []).map(c => ({ name: c.name, score: c.score, reasons: words(c.reasons), badge: t('ofd.badge'), note: t('ofd.note') }))]));
// The card shows Spooler's presets as Spooler/<preset> (shown); a pick goes back to the real name.
const realName = (name: string | null) => name && (match.value?.candidates.find(c => (c.shown ?? c.name) === name)?.name ?? name);
function pick(name: string | null) { const real = realName(name); pickPreset(i, real, match.value?.ofd?.find(c => c.name === real)?.id); }
const matchLabels = computed(() => ({ change: t('match.change'), none: t('match.none'), score: t('match.score'), auto: t('match.auto'), autoHint: t('match.autoHint') }));
// Pressure advance the head has now; Save keeps it on the linked spool (Spoolman only, keyed by the nozzle).
const pa = computed(() => s.status?.extruders[i]?.pa ?? null);
async function savePa() {
  const r = await run({ key: `pa:${i}`, label: t('heads.savePaLabel', { n }), cmd: 'save_pa', args: { head: i }, okText: t('ok.savePa', { n }) });
  if (r.ok) void loadSpools(true);
}
</script>

<template>
  <OuiSlot v-if="head" class="hc" :label="`T${n}`" :tool="(n as 1 | 2 | 3 | 4)" :name="head.loaded ? [head.type, head.sub_type].filter(Boolean).join(' ') || t('common.unknown') : has ? t('heads.unnamed') : null"
           :material="head.loaded ? head.vendor || head.type : null" :color="linked?.colour || head.colour || null" :colors="colours"
           :remaining="fraction" :initial="1" :active="active" :data-unnamed="(has && !head.loaded) || undefined" :empty-label="t('heads.noFilament')" :aria-label="`T${n}`">
    <template #state>
      <OuiStatus v-if="!has" state="idle">{{ t('heads.empty') }}</OuiStatus>
      <OuiStatus v-else-if="active && s.status?.state === 'printing'" state="busy">{{ t('status.state.printing') }}</OuiStatus>
      <OuiStatus v-else-if="notInHead" state="idle" :data-not-in-head="i">{{ t('heads.notInHead') }}</OuiStatus>
      <OuiStatus v-else-if="linked?.low" state="warn">{{ t('heads.low') }}</OuiStatus>
      <OuiStatus v-else-if="active" state="ok">{{ t('heads.activeChip') }}</OuiStatus>
    </template>
    <template #meta>{{ head.loaded ? head.vendor : t('heads.unnamedMeta') }}<span v-if="tag" class="oui-chip hc-tag" :title="tag.official ? t('heads.tagOfficial', { uid: tag.uid || '' }) : t('heads.tagThird', { uid: tag.uid || '' })">{{ t('heads.tag') }}</span></template>
    <!-- No Spoolman spool linked: there is no weight to show, so no amount line at all (not a dash that looks like a reading). -->
    <template #amount>
      <div v-if="linked" class="oui-slot-amount">
        <p v-if="linked.remaining == null" class="oui-muted">—</p>
        <p v-else class="oui-num"><strong>{{ grams(linked.remaining) }}</strong> g<span v-if="linked.initial != null" class="oui-muted"> / {{ grams(linked.initial) }} g</span></p>
        <OuiLevel :fraction="fraction" :tone="levelTone(fraction, linked.low)" />
      </div>
    </template>

    <!-- The nozzle heater stays on screen while the Edit form is open: its reading and Off must not disappear. -->
    <template v-if="!editing">
      <Select v-if="s.spools.length" :model-value="bound ?? 0" :options="groups" option-group-label="label" option-group-children="items" size="small"
              option-label="label" option-value="value" :virtual-scroller-options="longList(groupRows, 38)" filter :filter-fields="['q']" reset-filter-on-hide :filter-placeholder="t('pick.filter')" :aria-label="t('pick.label', { n })"
              :disabled="!!controlsOff || tracker.isBusy(`bind:${i}`)" :pt="{ label: { 'aria-describedby': offWhy } }" class="hc-pick" :data-focus-key="`pick:${i}`" :data-pick="i"
              @update:model-value="choose" @filter="e => (query = e.value)" @hide="query = ''">
        <template #value="{ value }">
          <span class="hc-opt"><OuiSpool v-if="value" :color="spoolOf(value)?.colour" :colors="spoolOf(value)?.colours" :fraction="spoolFraction(spoolOf(value)?.remaining, spoolOf(value)?.initial)" :size="22" />
            <span class="oui-truncate">{{ value ? label(spoolOf(value) ?? { id: value, vendor: '', name: '', material: '' } as Spool) : t('pick.choose') }}</span></span>
        </template>
        <template #option="{ option }">
          <span class="hc-opt"><OuiSpool v-if="option.sp" :color="option.sp.colour" :colors="option.sp.colours" :fraction="spoolFraction(option.sp.remaining, option.sp.initial)" :size="28" />
            <span class="oui-truncate">{{ option.label }}</span>
            <span v-if="option.sp && option.sp.remaining != null && option.sp.remaining < 100" class="oui-chip" data-tone="warn">{{ t('stock.low') }}</span></span>
        </template>
      </Select>
    </template>
    <HeaterControl :id="String(i)" card />
    <div v-if="!editing && match && has && showMatch" class="hc-match" :data-match="i">
      <p class="oui-label">{{ t('match.title') }}</p>
      <OuiPresetMatch :name="match.shown ?? match.name" :score="match.score" :confident="match.confident" :reasons="words(match.reasons)"
                      :badge="BADGES[match.source] ? t(BADGES[match.source]) : undefined" :remembered="match.source === 'remembered' && !!match.remembered_key"
                      :candidates="candidates"
                      :labels="matchLabels" :busy="s.matchBusy" @pick="pick" />
    </div>
    <template v-if="!editing">
      <p class="oui-meta"><template v-if="tag">{{ t('heads.tagDetail', { text: tagText }) }} · </template>{{ t('heads.feeder', { state: feedText }) }}<template v-if="feed.detected && !['preload_finish', 'load_finish'].includes(feed.state || '')"> · {{ t('heads.atInlet') }}</template></p>
      <p v-if="pa != null" class="oui-meta oui-row" :data-pa="i">{{ t('heads.pa', { v: pa }) }}<template v-if="head.nozzle"> · {{ tMaybe(`nozzle.${head.nozzle}`, head.nozzle) }}</template>
        <Button v-if="linked" text size="small" :label="t('heads.savePa')" :aria-label="t('heads.savePaLabel', { n })" :disabled="!!controlsOff || tracker.isBusy(`pa:${i}`)"
                :loading="tracker.isBusy(`pa:${i}`)" :data-save-pa="i" @click="savePa" /></p>
    </template>
    <form v-else :id="`hc-form-${i}`" class="hc-form" @submit.prevent="saveEdit">
      <p class="oui-strong hc-form-title">{{ t('edit.title', { n }) }}<OuiHint v-if="tagged" :label="t('heads.tag')" :text="t('edit.rfidNote')" /></p>
      <div class="hc-grid">
        <label :for="`e${i}-v`">{{ t('edit.vendor') }}</label><InputText :id="`e${i}-v`" v-model="form.vendor" size="small" />
        <label :id="`e${i}-tl`">{{ t('edit.type') }}</label><Select v-model="form.type" :options="TYPES" :aria-labelledby="`e${i}-tl`" size="small" />
        <label :for="`e${i}-s`">{{ t('edit.subtype') }}</label><InputText :id="`e${i}-s`" v-model="form.sub" size="small" />
        <label :for="`e${i}-c`">{{ t('edit.colour') }}</label><input :id="`e${i}-c`" v-model="form.colour" type="color" class="hc-colour">
      </div>
      <div class="oui-row">
        <Button type="submit" size="small" :label="t('common.save')" :loading="tracker.isBusy(`edit:${i}`)" :disabled="!!guidedWhy" :aria-describedby="why" />
        <Button severity="secondary" size="small" :label="t('common.cancel')" @click="editing = false" />
      </div>
    </form>

    <template v-if="!editing" #actions>
      <Button size="small" severity="secondary" :label="t('heads.load')" :aria-label="t('heads.loadLabel', { n })" :disabled="!!guidedWhy || tracker.isBusy(`load:${i}`)" :aria-describedby="why"
              :loading="tracker.isBusy(`load:${i}`)" :data-focus-key="`load:${i}`" :data-load="i" @click="load"><template #icon><OuiIcon :icon="download" :size="14" /></template></Button>
      <Button size="small" severity="secondary" :label="t('heads.unload')" :aria-label="t('heads.unloadLabel', { n })" :disabled="!!guidedWhy || tracker.isBusy(`unload:${i}`)" :aria-describedby="why"
              :loading="tracker.isBusy(`unload:${i}`)" :data-focus-key="`unload:${i}`" :data-unload="i" @click="unload"><template #icon><OuiIcon :icon="upload" :size="14" /></template></Button>
      <Button v-if="picked && !busy" size="small" severity="secondary" :label="t('heads.park')" :aria-label="t('heads.parkLabel', { n })" :disabled="!!guidedWhy || tracker.isBusy(`park:${i}`)" :aria-describedby="why"
              :loading="tracker.isBusy(`park:${i}`)" :data-focus-key="`park:${i}`" :data-park="i" @click="park"><template #icon><OuiIcon :icon="parkIcon" :size="14" /></template></Button>
      <span class="oui-spacer" />
      <Button size="small" severity="secondary" text :aria-label="t('heads.editLabel', { n })" :title="t('heads.editLabel', { n })" :disabled="!!guidedWhy" :aria-describedby="why"
              :data-focus-key="`edit:${i}`" :data-edit="i" @click="startEdit"><template #icon><OuiIcon :icon="editIcon" :size="14" /></template></Button>
      <Button size="small" severity="secondary" text :aria-label="t('heads.rfidLabel', { n })" :title="t('heads.rfidLabel', { n })" :disabled="!!controlsOff || tracker.isBusy(`rfid:${i}`)" :aria-describedby="offWhy"
              :data-focus-key="`rfid:${i}`" :data-rfid="i" @click="rfid"><template #icon><OuiIcon :icon="rfidIcon" :size="14" /></template></Button>
    </template>
  </OuiSlot>
</template>

<style>
/* A dense card: tighter spacing, a smaller spool beside the name and material, one-line names and a slimmer amount;
   cards are as tall as their content (the widget does not stretch them), so the actions sit at the foot of the taller card
   of a row, right after its content, and line up with its neighbour's. */
.oui-slot.hc { gap: 6px; padding: 6px 4px; }
.oui-slot.hc .oui-slot-head { min-height: 20px; }
.oui-slot.hc .oui-slot-main { gap: var(--oui-s2); }
.oui-slot.hc .oui-slot-main .oui-spool { width: 36px !important; height: 36px !important; flex: none; }
.oui-slot.hc .oui-slot-name { -webkit-line-clamp: 1; line-clamp: 1; line-height: 1.3; }
.oui-slot.hc .oui-slot-amount { gap: 3px; line-height: 18px; }
.oui-slot.hc .oui-slot-amount strong { font-size: var(--oui-text-md); }
.oui-slot.hc .oui-slot-extra { gap: 6px; }
.oui-slot.hc .oui-slot-extra > .oui-meta { font-size: var(--oui-text-xs); line-height: 1.35; }
.oui-slot.hc .oui-slot-actions { padding-top: 0; }
.hc-tag { margin-inline-start: var(--oui-s2); }
.hc-match { display: grid; gap: 2px; padding-top: 6px; border-top: 1px solid var(--oui-border); }
.hc-match .oui-match-name { font-size: var(--oui-text-sm); }
/* Change-list names wrap instead of being cut off. */
.hc-match .oui-match-option-name { align-items: flex-start; }
.hc-match .oui-match-option-name .oui-truncate { white-space: normal; overflow: visible; overflow-wrap: anywhere; }
.hc-pick { width: 100%; min-width: 0; }
.hc-opt { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; }
.hc-form-title { display: flex; align-items: center; gap: var(--oui-s1); }
.hc-form { display: grid; gap: var(--oui-s2); padding-top: var(--oui-s2); border-top: 1px solid var(--oui-border); }
.hc-grid { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--oui-s2); align-items: center; }
.hc-grid > label { font-size: var(--oui-text-sm); font-weight: 600; color: var(--oui-muted); }
.hc-colour { width: 44px; height: var(--oui-control-sm); padding: 0; border: 1px solid var(--oui-control-border); border-radius: var(--oui-radius); background: none; }
</style>
