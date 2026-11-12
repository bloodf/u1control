<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Icon from './Icon.vue';
import { s, run, tracker, controlsOff, busy, loadSpools } from '../app/store';
import { ask } from '../core/dialog';
import { t, fmt } from '../core/i18n';
import { family } from '../core/logic';
import type { Spool, Tag } from '../app/types';

const props = defineProps<{ index: number }>();
const i = props.index, n = i + 1;
const TYPES = ['PLA', 'PLA+', 'PLA-CF', 'PETG', 'PETG-CF', 'PCTG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'PC', 'PVA', 'HIPS'];

const head = computed(() => s.status?.heads[i]);
const tag = computed<Tag | null>(() => s.status?.rfid?.[i] ?? null);
const feed = computed(() => s.status?.feed?.[i] ?? {});
const active = computed(() => !!s.status?.extruders[i]?.active);
const tagged = computed(() => !!(head.value?.official || tag.value));
const guidedWhy = computed(() => controlsOff.value || (busy.value ? t('reason.busy') : ''));
const tagText = computed(() => {
  const g = tag.value;
  if (!g) return '';
  const temp = g.hotend_min || g.hotend_max ? `${g.hotend_min || '?'}–${g.hotend_max || '?'} °C` : '';
  return [[g.vendor || g.manufacturer, g.type, g.sub_type].filter(Boolean).join(' '), temp,
    g.bed_temp ? t('heads.tagBed', { temp: g.bed_temp }) : '', g.sku ? `SKU ${g.sku}` : ''].filter(Boolean).join(' · ');
});

async function load() {
  if (!await ask({ title: t('act.load', { n }), text: t('confirm.load.text', { n }), yes: t('confirm.load.yes', { n }), no: t('common.goBack') })) return;
  await run({ key: `load:${i}`, label: t('act.load', { n }), cmd: 'load', args: { head: i }, okText: t('ok.load', { n }), timeoutMs: 120000 });
}
async function unload() {
  if (!await ask({ title: t('act.unload', { n }), text: t('confirm.unload.text', { n }), yes: t('confirm.unload.yes', { n }), no: t('common.goBack') })) return;
  await run({ key: `unload:${i}`, label: t('act.unload', { n }), cmd: 'unload', args: { head: i }, okText: t('ok.unload', { n }), timeoutMs: 120000 });
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
  if (tagged.value && !await ask({ title: t('edit.title', { n }),
    text: t('confirm.overwrite.text', { n, kind: head.value?.official ? t('edit.official') : t('edit.tagged') }),
    yes: t('confirm.overwrite.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: `edit:${i}`, label: t('act.setFilament', { n }), cmd: 'set_filament', timeoutMs: 60000,
    args: { head: i, vendor: form.vendor, type: form.type, sub_type: form.sub, colour: form.colour, force: tagged.value }, okText: t('ok.setFilament', { n }) });
  if (r.ok) editing.value = false;
}

// ---------------------------------------------------------------- Spoolman spool
const bound = computed(() => s.bindings[String(i)] ?? null);
const label = (sp: Spool) => t('pick.option', { id: sp.id, vendor: sp.vendor, name: sp.name, material: sp.material, grams: fmt.grams(sp.remaining) });
const groups = computed(() => {
  const fam = head.value?.type ? family(head.value.type) : '';
  const fit = s.spools.filter(sp => !fam || family(sp.material) === fam);
  const rest = s.spools.filter(sp => !fit.includes(sp));
  const opt = (sp: Spool) => ({ value: sp.id, label: label(sp), sp });
  return [
    { label: t('pick.fit'), items: [{ value: 0, label: t('pick.none'), sp: null }, ...fit.map(opt)] },
    ...(rest.length ? [{ label: t('pick.other'), items: rest.map(opt) }] : []),
  ];
});
async function choose(id: number | null) {
  if (!id) {
    const was = bound.value;
    if (was == null) return;
    if (!await ask({ title: t('act.unbind', { n }), text: t('confirm.unbind.text', { id: was, n }), yes: t('confirm.unbind.yes'), no: t('common.goBack') })) return;
    const r = await run({ key: `bind:${i}`, label: t('act.unbind', { n }), cmd: 'unbind_spool', args: { head: i }, okText: t('ok.unbind', { n }) });
    if (r.ok) s.bindings = r.result.bindings; else void loadSpools(true);
    return;
  }
  const force = tagged.value;
  if (!await ask({ title: t('act.bind', { n }), text: force ? t('confirm.bind.force', { n, id }) : t('confirm.bind.text', { n, id }),
    yes: t('confirm.bind.yes', { n }), no: t('common.goBack'), danger: force })) return;
  const r = await run({ key: `bind:${i}`, label: t('act.bind', { n }), cmd: 'bind_spool', args: { head: i, spool_id: id, force }, okText: t('ok.bind', { n, id }), timeoutMs: 60000 });
  if (r.ok) s.bindings = r.result.bindings; else void loadSpools(true);
}
const swatch = (sp: Spool | null) => !sp ? 'transparent'
  : sp.colours && sp.colours.length > 1 ? `linear-gradient(90deg,${sp.colours.join(',')})` : sp.colour || 'transparent';
</script>

<template>
  <article v-if="head" class="hc" :class="{ active }" :style="{ '--tc': `var(--u1-t${n})` }" :aria-labelledby="`hc-${i}`">
    <template v-if="!editing">
      <div class="hc-top">
        <Icon :name="`toolhead/t${n}`" :size="32" />
        <span class="u1-sw hc-sw" :style="{ background: head.colour || 'transparent' }" />
        <div class="hc-name">
          <strong :id="`hc-${i}`">T{{ n }}<span v-if="active" class="oui-meta"> · {{ t('heads.active') }}</span></strong>
          <div>{{ head.loaded ? head.type : t('heads.empty') }} <span class="oui-muted">{{ head.vendor }} {{ head.sub_type }}</span>
            <span v-if="tag" class="u1-pill hc-tag" :title="tag.official ? t('heads.tagOfficial', { uid: tag.uid || '' }) : t('heads.tagThird', { uid: tag.uid || '' })">{{ t('heads.tag') }}</span></div>
        </div>
      </div>
      <p v-if="tag" class="oui-meta hc-p">{{ t('heads.tagDetail', { text: tagText }) }}</p>
      <p class="oui-meta hc-p">{{ t('heads.feeder', { state: feed.state || '—' }) }}<template v-if="feed.detected"> · {{ t('heads.atInlet') }}</template></p>
      <div class="u1-row hc-actions">
        <Button size="small" severity="secondary" outlined :label="t('heads.edit')" :aria-label="t('heads.editLabel', { n })" :disabled="!!guidedWhy"
                :data-focus-key="`edit:${i}`" :data-edit="i" @click="startEdit" />
        <Button size="small" severity="secondary" outlined :aria-label="t('heads.loadLabel', { n })" :disabled="!!guidedWhy || tracker.isBusy(`load:${i}`)"
                :loading="tracker.isBusy(`load:${i}`)" :data-focus-key="`load:${i}`" :data-load="i" @click="load">
          <Icon name="icon/load-filament" /><span>{{ t('heads.load') }}</span></Button>
        <Button size="small" severity="secondary" outlined :aria-label="t('heads.unloadLabel', { n })" :disabled="!!guidedWhy || tracker.isBusy(`unload:${i}`)"
                :loading="tracker.isBusy(`unload:${i}`)" :data-focus-key="`unload:${i}`" :data-unload="i" @click="unload">
          <Icon name="icon/unload-filament" /><span>{{ t('heads.unload') }}</span></Button>
        <Button size="small" severity="secondary" outlined :aria-label="t('heads.rfidLabel', { n })" :disabled="!!controlsOff || tracker.isBusy(`rfid:${i}`)"
                :data-focus-key="`rfid:${i}`" :data-rfid="i" @click="rfid">
          <Icon name="icon/rfid-tag" /><span>{{ t('heads.rfid') }}</span></Button>
      </div>
      <p v-if="guidedWhy" class="u1-why">{{ guidedWhy }}</p>
      <Select v-if="s.spools.length" :model-value="bound ?? 0" :options="groups" option-group-label="label" option-group-children="items"
              option-label="label" option-value="value" filter :filter-placeholder="t('pick.filter')" :aria-label="t('pick.label', { n })"
              :disabled="!!controlsOff || tracker.isBusy(`bind:${i}`)" class="hc-pick" :data-focus-key="`pick:${i}`" :data-pick="i"
              @update:model-value="choose">
        <template #value="{ value }">
          <span class="hc-opt"><span class="u1-sw" :style="{ background: swatch(s.spools.find(x => x.id === value) ?? null) }" />
            <span class="hc-opt-t">{{ value ? label(s.spools.find(x => x.id === value) ?? { id: value, vendor: '', name: '', material: '' } as Spool) : t('pick.choose') }}</span></span>
        </template>
        <template #option="{ option }">
          <span class="hc-opt"><span class="u1-sw" :style="{ background: swatch(option.sp) }" />
            <span class="hc-opt-t">{{ option.label }}</span>
            <span v-if="option.sp && option.sp.remaining != null && option.sp.remaining < 100" class="u1-warn">·</span></span>
        </template>
      </Select>
    </template>
    <form v-else class="hc-form" @submit.prevent="saveEdit">
      <strong :id="`hc-${i}`">{{ t('edit.title', { n }) }}</strong>
      <div class="hc-grid">
        <label :for="`e${i}-v`">{{ t('edit.vendor') }}</label><InputText :id="`e${i}-v`" v-model="form.vendor" />
        <label :id="`e${i}-tl`">{{ t('edit.type') }}</label><Select v-model="form.type" :options="TYPES" :aria-labelledby="`e${i}-tl`" />
        <label :for="`e${i}-s`">{{ t('edit.subtype') }}</label><InputText :id="`e${i}-s`" v-model="form.sub" />
        <label :for="`e${i}-c`">{{ t('edit.colour') }}</label><input :id="`e${i}-c`" v-model="form.colour" type="color" class="hc-colour">
      </div>
      <p v-if="tagged" class="oui-meta">{{ t('edit.rfidNote') }}</p>
      <div class="u1-row">
        <Button type="submit" :label="t('common.save')" :loading="tracker.isBusy(`edit:${i}`)" :disabled="!!guidedWhy" />
        <Button severity="secondary" outlined :label="t('common.cancel')" @click="editing = false" />
      </div>
    </form>
  </article>
</template>

<style scoped>
.hc { min-width: 0; border: 1px solid var(--oui-border); border-top: 4px solid var(--tc); border-radius: 12px; padding: 12px; background: var(--oui-surface); display: grid; gap: 6px; align-content: start; }
.hc.active { border-color: var(--p-primary-color); border-top-color: var(--tc); }
.hc-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.hc-sw { width: 32px; height: 32px; }
.hc-name { min-width: 0; overflow-wrap: anywhere; }
.hc-tag { margin-left: 4px; }
.hc-p { margin: 0; }
.hc-actions :deep(.p-button) { gap: 4px; }
.hc-pick { width: 100%; min-width: 0; }
.hc-opt { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; }
.hc-opt-t { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hc-form { display: grid; gap: 8px; }
.hc-grid { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: center; }
.hc-colour { width: 44px; height: 32px; padding: 0; border: 1px solid var(--oui-control-border, var(--oui-border)); border-radius: 6px; background: none; }
</style>
