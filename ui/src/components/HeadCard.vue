<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import { OuiHint, OuiIcon, OuiLevel, OuiPresetMatch, OuiSlot, OuiSpool, OuiSpoolPick, OuiStatus, type OuiSpoolPickLabels } from '@orca-plugins/ui-foundation/src/components';
import { chevronDown, download, edit as editIcon, home as parkIcon, rfid as rfidIcon, upload, warning } from '@orca-plugins/ui-foundation/src/icons';
import HeaterControl from './HeaterControl.vue';
import { config } from '../app/settings';
import { s, run, tracker, busy, controlsOff, loadSpools, relink, guidedWhy, pickPreset } from '../app/store';
import { presetLabel } from '../core/match';
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
// The compact line shows the linked spool; it opens the shared colour-first picker (OuiSpoolPick) under it, over the card.
// One swatch per colour, drawn only while open: a colour with one spool picks it, with several a dialog lists them fullest
// first. Material chips start at the head's material family; "No spool" unlinks.
const fam = computed(() => (head.value?.type ? family(head.value.type) : ''));
const picking = ref(false);
const pickFam = ref('');
const trigger = ref<HTMLButtonElement | null>(null);
const panel = ref<HTMLElement | null>(null);
const pickSpools = computed(() => s.spools.map(sp => ({ ...sp, material: family(sp.material) })));
const pickLabels = computed<OuiSpoolPickLabels>(() => ({ label: t('pick.label', { n }), spools: t('pick.count'), noColour: t('pick.noColour'),
  choose: t('pick.dialog'), unknown: t('pick.weightUnknown'), empty: t('pick.empty'), search: t('pick.filter'), noMatch: t('pick.noMatch'),
  allMaterials: t('pick.allMaterials'), none: t('pick.none') }));
async function openPick() {
  if (picking.value) { closePick(); return; }
  pickFam.value = fam.value;
  picking.value = true;
  await nextTick();
  const box = panel.value, r = trigger.value?.getBoundingClientRect();
  if (box && r) box.toggleAttribute('data-up', innerHeight - r.bottom < box.offsetHeight + 4 && r.top > innerHeight - r.bottom);
  box?.querySelector<HTMLElement>('.oui-spick-q, [data-colour][tabindex="0"]')?.focus();
}
function closePick() {
  picking.value = false;
  trigger.value?.focus();
}
// A press outside the open picker closes it; its dialog of one colour's spools is outside the card but belongs to it.
function outside(e: Event) {
  const at = e.target as Element | null;
  if (!at || panel.value?.contains(at) || trigger.value?.contains(at) || at.closest?.('.p-dialog-mask')) return;
  picking.value = false;
}
watch(picking, on => document[on ? 'addEventListener' : 'removeEventListener']('pointerdown', outside, true));
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside, true));
function onPick(id: number | string | null) {
  closePick();
  void choose(id == null ? null : Number(id));
}
async function choose(id: number | null) {
  if (id === bound.value) return;
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
// The OrcaSlicer preset Apply to project filaments gives this head, and Change (remembered by the plugin). The card shows
// only a clean name (presetLabel); scores and reasons stay with the plugin, a doubtful automatic pick gets a warning icon.
const match = computed(() => s.matches[String(i)] ?? null);
// Settings > Connection "Show the matched preset": off hides the block; Apply to project filaments still uses the match.
const showMatch = computed(() => config.value?.settings?.show_preset_match !== false);
// Change's list by shown name, first (best) of each; a pick goes back to the real name.
const candidates = computed(() => (!match.value || match.value.source === 'linked' ? []
  : [...new Set(match.value.candidates.map(c => presetLabel(c.name)))].map(name => ({ name }))));
const realName = (name: string | null) => name && (match.value?.candidates.find(c => presetLabel(c.name) === name)?.name ?? name);
const pick = (name: string | null) => pickPreset(i, realName(name));
const matchLabels = computed(() => ({ change: t('match.change'), none: t('match.none'), score: '', auto: t('match.auto'), autoHint: t('match.autoHint') }));
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
      <div v-if="s.spools.length" class="hc-pick" :data-open="picking || undefined">
        <button ref="trigger" type="button" class="hc-pick-btn" :aria-label="t('pick.label', { n })" :aria-expanded="picking" aria-haspopup="true"
                :disabled="!!controlsOff || tracker.isBusy(`bind:${i}`)" :aria-describedby="offWhy" :data-focus-key="`pick:${i}`" :data-pick="i" @click="openPick">
          <OuiSpool v-if="linked" :color="linked.colour" :colors="linked.colours" :fraction="spoolFraction(linked.remaining, linked.initial)" :size="22" />
          <span class="oui-truncate">{{ bound == null ? t('pick.choose') : label(linked ?? { id: bound, vendor: '', name: '', material: '' } as Spool) }}</span>
          <OuiIcon :icon="chevronDown" :size="14" />
        </button>
        <div v-if="picking" ref="panel" class="hc-pick-panel" :data-pick-panel="i">
          <OuiSpoolPick v-model:material="pickFam" :spools="pickSpools" :labels="pickLabels" :selected="bound" :grams="fmt.grams" @pick="onPick" @close="closePick" />
        </div>
      </div>
    </template>
    <HeaterControl :id="String(i)" card />
    <div v-if="!editing && match && has && showMatch" class="hc-match" :data-match="i">
      <p class="oui-label hc-match-title">{{ t('match.title') }}<span v-if="match.name && !match.confident" class="hc-unsure" role="img" :title="t('match.unsure')"
        :aria-label="t('match.unsure')" :data-unsure="i"><OuiIcon :icon="warning" :size="14" tone="warn" /></span></p>
      <OuiPresetMatch :name="match.name ? presetLabel(match.name) : null" :badge="match.source === 'remembered' ? t('match.remembered') : undefined" :remembered="match.source === 'remembered' && !!match.remembered_key"
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
.hc-match-title { display: flex; align-items: center; gap: var(--oui-s1); }
.hc-unsure { display: inline-flex; cursor: help; }
/* Change-list names wrap instead of being cut off. */
.hc-match .oui-match-option-name { align-items: flex-start; }
.hc-match .oui-match-option-name .oui-truncate { white-space: normal; overflow: visible; overflow-wrap: anywhere; }
.hc-pick { position: relative; min-width: 0; }
.orca-ui .hc-pick-btn { display: flex; align-items: center; gap: 6px; width: 100%; min-width: 0; height: 32px; padding: 0 var(--oui-s2); border: 1px solid var(--oui-control-border);
  border-radius: var(--oui-radius-sm); background: var(--oui-control); color: var(--oui-text); font: inherit; font-size: var(--oui-text-sm); text-align: start; cursor: pointer; }
.orca-ui .hc-pick-btn > .oui-truncate { flex: 1; min-width: 0; }
.orca-ui .hc-pick-btn:disabled { opacity: .6; cursor: default; }
.orca-ui .hc-pick-btn:focus-visible { outline: 2px solid var(--oui-primary-mark); outline-offset: 1px; }
/* The picker floats over the card under its line, as wide as the card: opening it never grows the card. */
.oui-slot.hc:has(.hc-pick[data-open]) { position: relative; z-index: 30; }
.hc-pick-panel { position: absolute; inset-inline: 0; top: calc(100% + 2px); z-index: 1; padding: var(--oui-s2); border-radius: var(--oui-radius-sm);
  background: var(--oui-surface); box-shadow: 0 0 0 1px var(--oui-border), 0 8px 24px rgb(0 0 0 / .28); }
.hc-pick-panel[data-up] { top: auto; bottom: calc(100% + 2px); }
.hc-form-title { display: flex; align-items: center; gap: var(--oui-s1); }
.hc-form { display: grid; gap: var(--oui-s2); padding-top: var(--oui-s2); border-top: 1px solid var(--oui-border); }
.hc-grid { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--oui-s2); align-items: center; }
.hc-grid > label { font-size: var(--oui-text-sm); font-weight: 600; color: var(--oui-muted); }
.hc-colour { width: 44px; height: var(--oui-control-sm); padding: 0; border: 1px solid var(--oui-control-border); border-radius: var(--oui-radius); background: none; }
</style>
