<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import { OuiBanner, OuiEmpty, OuiFormRow, OuiIcon, OuiKeyValue, OuiPanel } from '../../shared/src/components';
import { external, refresh, wrench } from '../../shared/src/icons';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown, printing } from '../app/store';
import { ask, prompt } from '../core/dialog';
import { t } from '../core/i18n';
import { message } from '../core/tracker';

interface Opt { value: string; label: string; confirm?: string; hidden?: boolean; inputs?: { name: string; label: string; placeholder?: string; regex?: string }[] }
interface Item { id: string; label: string; description?: string; current?: string; hidden?: boolean; print_safe?: boolean; options: Opt[] }
interface Group { id: string; label: string; items: Item[] }

const state = ref<'idle' | 'loading' | 'ok' | 'error'>('idle');
const error = ref('');
const status = ref<Record<string, unknown>>({});
const groups = ref<Group[]>([]);
const chosen = reactive<Record<string, string | null>>({});
const log = ref('');

async function load() {
  if (s.info?.firmware.kind !== 'extended') return;
  const epoch = s.epoch;
  state.value = 'loading';
  try {
    const r = await bridge.command('ext_settings', {}, s.info.generation);
    if (epoch !== s.epoch) return;
    status.value = r.status || {};
    groups.value = r.settings || [];
    for (const g of groups.value) for (const x of g.items) chosen[x.id] = x.current ?? null;
    state.value = 'ok';
  } catch (e) {
    if (epoch !== s.epoch) return;
    error.value = message(e);
    state.value = 'error';
  }
}
watch(() => [s.epoch, s.info?.firmware.kind], () => { groups.value = []; log.value = ''; void load(); }, { immediate: true });

const visibleItems = (g: Group) => g.items.filter(x => !x.hidden);
// Settings that restart Klipper or reboot (print_safe false, see extended.PRINT_SAFE) would end a running print.
const waits = (x: Item) => printing.value && !x.print_safe;
const options = (x: Item) => {
  const opts = x.options.filter(o => !o.hidden || o.value === x.current);
  const known = opts.some(o => o.value === x.current);
  return [...(known || !x.current ? [] : [{ value: '', label: t('ext.unknownValue', { value: x.current }), disabled: true }]),
    ...opts.map(o => ({ value: o.value, label: o.label }))];
};
const show = (v: unknown) => (typeof v === 'object' ? JSON.stringify(v) : String(v));

async function inputs(opt: Opt): Promise<Record<string, string> | null> {
  const values: Record<string, string> = {};
  for (const inp of opt.inputs ?? []) {
    const label = inp.placeholder ? t('ext.inputExample', { label: inp.label, example: inp.placeholder }) : t('ext.input', { label: inp.label });
    const v = ((await prompt({ title: opt.label, text: label, yes: t('common.apply'), no: t('common.goBack'), input: { label: inp.label, value: '', placeholder: inp.placeholder } })) || '').trim();
    if (!v) return null;
    let ok = true;
    try { ok = !inp.regex || new RegExp(inp.regex).test(v); } catch { ok = true; }   // the printer checks it too
    if (!ok) { tracker.notify('error', t('ext.inputBad', { label: inp.label })); return null; }
    values[inp.name] = v;
  }
  return values;
}
function result(r: any, okText: string) {
  log.value = r?.log || '';
  if (r?.ok) tracker.notify('success', okText);
  else tracker.notify('unknown', t('ext.resultUnknown', { error: r?.error || t('common.unknown') }));
}
async function apply(x: Item) {
  const v = chosen[x.id];
  const opt = x.options.find(o => o.value === v);
  if (!opt) { tracker.notify('error', t('ext.pickValue')); return; }
  const vals = await inputs(opt);
  if (vals === null) return;
  const text = (opt.confirm ? opt.confirm + '\n\n' : '') + t('confirm.extSet.text', { label: x.label, value: opt.label });
  if (!await ask({ title: t('ext.applyLabel', { label: x.label }), text, yes: t('common.apply'), no: t('common.goBack') })) return;
  const r = await run({ key: `ext:${x.id}`, label: t('act.extSet'), cmd: 'ext_set', timeoutMs: 120000,
    args: { setting_id: x.id, value: v, inputs: Object.keys(vals).length ? vals : null } });
  if (r.ok) result(r.result, t('ok.extSet'));
}
const actions = [{ id: 'restart-klipper', label: 'ext.restartKlipper', ends: true }, { id: 'restart-moonraker', label: 'ext.restartMoonraker' },
  { id: 'reboot-system', label: 'ext.reboot', danger: true, ends: true }] as const;
async function action(id: string, name: string, danger = false) {
  if (!await ask({ title: name, text: t('confirm.extAction.text', { name }), yes: name, no: t('common.goBack'), danger })) return;
  const r = await run({ key: `exta:${id}`, label: t('act.extAction'), cmd: 'ext_action', args: { action_id: id }, timeoutMs: 120000 });
  if (r.ok) result(r.result, t('ok.extAction'));
}
const facts = computed(() => Object.entries(status.value).map(([label, v]) => ({ label, value: show(v) })));
</script>
<template>
  <!-- Built like a settings section (OuiFormSection), with its heading id kept for the section's label. -->
  <OuiPanel id="firmware" class="oui-formsection" :icon="wrench" flush tabindex="-1" aria-labelledby="fw-h">
    <template #title><span id="fw-h">{{ t('ext.title') }}</span></template>
    <OuiEmpty v-if="!targetKnown || !s.info" compact :state="s.phase === 'connecting' ? 'loading' : 'offline'" :title="s.phase === 'connecting' ? t('ext.detecting') : t('ext.noTarget')" />
    <OuiEmpty v-else-if="s.info.firmware.kind !== 'extended'" compact :icon="wrench" :title="t('ext.stock')">
      <template #actions><a class="u1-inline" href="https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware"><OuiIcon :icon="external" :size="14" />{{ t('ext.link') }}</a></template>
    </OuiEmpty>
    <OuiEmpty v-else-if="state === 'loading'" compact state="loading" :title="t('ext.detecting')" role="status" />
    <OuiEmpty v-else-if="state === 'error'" state="error" :title="t('ext.error', { error })" :text="t('ext.errorHelp')">
      <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="load"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
    </OuiEmpty>
    <template v-else-if="state === 'ok'">
      <div v-show="facts.length || printing" class="oui-stack u1-pad">
        <OuiKeyValue v-if="facts.length" :items="facts" />
        <!-- Said once for this panel; the Apply buttons and actions it turns off point here. -->
        <OuiBanner :show="printing" id="ext-print-why" role="note" tone="info" :title="t('ext.printWhy')" data-test="ext-print-why"
                   dismissible :dismiss-key="`ext-print-why:${s.status?.filename ?? ''}`" :close-label="t('common.close')" />
      </div>
      <div class="oui-formsection-rows fw-rows">
        <template v-for="g in groups" :key="g.id">
          <h3 v-if="visibleItems(g).length" class="oui-label fw-g">{{ g.label }}</h3>
          <OuiFormRow v-for="x in visibleItems(g)" :id="`ext-l-${x.id}`" :key="x.id" class="fw-item" :label="x.label" :hint="x.description">
            <Select v-model="chosen[x.id]" :options="options(x)" option-label="label" option-value="value" option-disabled="disabled" :aria-label="x.label" class="fw-sel" />
            <Button severity="secondary" :label="t('common.apply')" :aria-label="t('ext.applyLabel', { label: x.label })" :loading="tracker.isBusy(`ext:${x.id}`)"
                    :disabled="waits(x)" :aria-describedby="waits(x) ? 'ext-print-why' : undefined" :data-focus-key="`ext:${x.id}`" @click="apply(x)" />
          </OuiFormRow>
        </template>
      </div>
      <pre v-if="log" class="oui-error-detail oui-well fw-log" :aria-label="t('ext.log')" tabindex="0">{{ log }}</pre>
    </template>
    <!-- Restarts and the reboot: apart from the settings, the reboot in red, and each asks first. -->
    <template v-if="state === 'ok' && targetKnown && s.info?.firmware.kind === 'extended'" #footer>
      <Button v-for="a in actions" :key="a.id" :severity="'danger' in a ? 'danger' : 'secondary'" :outlined="'danger' in a" size="small" :label="t(a.label)" :loading="tracker.isBusy(`exta:${a.id}`)"
              :class="{ 'fw-danger': 'danger' in a }" :disabled="printing && 'ends' in a" :aria-describedby="printing && 'ends' in a ? 'ext-print-why' : undefined"
              :data-focus-key="`exta:${a.id}`" @click="action(a.id, t(a.label), 'danger' in a)" />
    </template>
  </OuiPanel>
</template>
<style>
.fw-g { padding: var(--oui-s3) var(--oui-s4) var(--oui-s1); }
.fw-rows { border-top: 1px solid var(--oui-border); }
.fw-rows:empty { display: none; }
.fw-log { max-height: 240px; overflow: auto; margin: 0 var(--oui-s4) var(--oui-s4); padding: var(--oui-s2); }
.fw-danger { margin-inline-start: auto; }
</style>
