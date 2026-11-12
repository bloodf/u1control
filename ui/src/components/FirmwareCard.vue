<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import Message from 'primevue/message';
import Icon from './Icon.vue';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown } from '../app/store';
import { ask, prompt } from '../core/dialog';
import { t } from '../core/i18n';
import { message } from '../core/tracker';

interface Opt { value: string; label: string; confirm?: string; hidden?: boolean; inputs?: { name: string; label: string; placeholder?: string; regex?: string }[] }
interface Item { id: string; label: string; description?: string; current?: string; hidden?: boolean; options: Opt[] }
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
const actions = [{ id: 'restart-klipper', label: 'ext.restartKlipper' }, { id: 'restart-moonraker', label: 'ext.restartMoonraker' }, { id: 'reboot-system', label: 'ext.reboot', danger: true }] as const;
async function action(id: string, name: string, danger = false) {
  if (!await ask({ title: name, text: t('confirm.extAction.text', { name }), yes: name, no: t('common.goBack'), danger })) return;
  const r = await run({ key: `exta:${id}`, label: t('act.extAction'), cmd: 'ext_action', args: { action_id: id }, timeoutMs: 120000 });
  if (r.ok) result(r.result, t('ok.extAction'));
}
</script>
<template>
  <section class="u1-card" aria-labelledby="fw-h">
    <h2 id="fw-h"><Icon name="icon/firmware" /> {{ t('ext.title') }}</h2>
    <p v-if="!targetKnown || !s.info" class="oui-muted">{{ s.phase === 'connecting' ? t('ext.detecting') : t('ext.noTarget') }}</p>
    <div v-else-if="s.info.firmware.kind !== 'extended'" class="fw-stock"><Icon name="spot/stock-firmware" :size="96" />
      <p>{{ t('ext.stock') }} <a href="https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware">{{ t('ext.link') }}</a></p></div>
    <p v-else-if="state === 'loading'" class="oui-muted" role="status">{{ t('ext.detecting') }}</p>
    <Message v-else-if="state === 'error'" severity="error">
      {{ t('ext.error', { error }) }} {{ t('ext.errorHelp') }}
      <div><Button size="small" severity="secondary" outlined :label="t('common.retry')" @click="load" /></div></Message>
    <template v-else-if="state === 'ok'">
      <dl class="fw-kv"><template v-for="(v, k) in status" :key="k"><dt>{{ k }}</dt><dd>{{ show(v) }}</dd></template></dl>
      <template v-for="g in groups" :key="g.id">
        <h3 v-if="visibleItems(g).length" class="fw-g">{{ g.label }}</h3>
        <div v-for="x in visibleItems(g)" :key="x.id" class="fw-item">
          <div><label :id="`ext-l-${x.id}`">{{ x.label }}</label><div v-if="x.description" class="oui-meta">{{ x.description }}</div></div>
          <Select v-model="chosen[x.id]" :options="options(x)" option-label="label" option-value="value" option-disabled="disabled" :aria-labelledby="`ext-l-${x.id}`" class="fw-sel" />
          <Button severity="secondary" outlined :label="t('common.apply')" :aria-label="t('ext.applyLabel', { label: x.label })" :loading="tracker.isBusy(`ext:${x.id}`)"
                  :data-focus-key="`ext:${x.id}`" @click="apply(x)" />
        </div>
      </template>
      <div class="u1-row fw-actions">
        <Button v-for="a in actions" :key="a.id" :severity="'danger' in a ? 'danger' : 'secondary'" outlined :label="t(a.label)" :loading="tracker.isBusy(`exta:${a.id}`)"
                :data-focus-key="`exta:${a.id}`" @click="action(a.id, t(a.label), 'danger' in a)" />
      </div>
      <pre v-if="log" class="oui-error-detail fw-log" :aria-label="t('ext.log')">{{ log }}</pre>
    </template>
  </section>
</template>
<style scoped>
.fw-stock { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; } .fw-stock p { flex: 1 1 260px; margin: 0; }
.fw-kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; } .fw-kv dt { color: var(--oui-muted); } .fw-kv dd { margin: 0; overflow-wrap: anywhere; }
.fw-g { margin: 16px 0 8px; }
.fw-item { display: grid; grid-template-columns: minmax(0, 1fr) minmax(160px, 240px) auto; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--oui-border); }
.fw-sel { width: 100%; }
.fw-actions { margin-top: 12px; }
.fw-log { max-height: 240px; overflow: auto; border: 1px solid var(--oui-border); border-radius: 6px; padding: 8px; }
@media (max-width: 640px) { .fw-item { grid-template-columns: minmax(0, 1fr); } }
</style>
