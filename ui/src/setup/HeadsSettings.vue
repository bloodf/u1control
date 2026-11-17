<script setup lang="ts">
// Heads settings inside the print setup: each toolhead's filament (vendor, type, colour) and its Spoolman spool,
// written with the Dashboard's own commands (set_filament, bind_spool, unbind_spool) through the U1 Control tab's
// service. The plugin re-reads the toolheads after each change, so the mapping above follows.
import { onMounted, reactive, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import { OuiSwatch } from '../../shared/src/components';
import * as bridge from '../core/bridge';
import { t } from '../core/i18n';
import type { SetupHead } from '../core/logic';

interface Spool { id: number; vendor: string; name: string; material: string; colour?: string | null }
const props = defineProps<{ heads: SetupHead[]; disabled: boolean }>();
const TYPES = ['PLA', 'PLA+', 'PLA-CF', 'PETG', 'PETG-CF', 'PCTG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'PC', 'PVA', 'HIPS'];

const forms = reactive(props.heads.map(h => ({ vendor: h.vendor || 'Generic', type: h.type || 'PLA', colour: h.colour || '#ffffff' })));
const spools = ref<Spool[]>([]);
const bindings = ref<Record<string, number>>({});
const status = reactive<Record<number, { busy: boolean; text: string; error: boolean }>>({});
const say = (i: number, busy: boolean, text = '', error = false) => { status[i] = { busy, text, error }; };

onMounted(async () => {
  try {
    const r = await bridge.command('spools');
    spools.value = r?.spools ?? [];
    bindings.value = r?.bindings ?? {};
  } catch (e) { say(-1, false, String((e as Error).message ?? e), true); }
});

async function save(i: number) {
  say(i, true);
  try {
    const f = forms[i], h = props.heads[i];
    await bridge.command('set_filament', { head: i, vendor: f.vendor, type: f.type, colour: f.colour, sub_type: h.sub_type || 'Basic', force: !!h.official });
    say(i, false, t('setup.headSaved', { n: i + 1 }));
  } catch (e) { say(i, false, String((e as Error).message ?? e), true); }
}
async function link(i: number, id: number) {
  say(i, true);
  try {
    const r = id ? await bridge.command('bind_spool', { head: i, spool_id: id, force: !!props.heads[i].official })
      : await bridge.command('unbind_spool', { head: i });
    bindings.value = r?.bindings ?? bindings.value;
    say(i, false, t('setup.headSaved', { n: i + 1 }));
  } catch (e) { say(i, false, String((e as Error).message ?? e), true); }
}
const spoolOptions = () => [{ id: 0, label: t('setup.noSpool') }, ...spools.value.map(sp => ({ id: sp.id, label: `#${sp.id} ${sp.vendor} ${sp.name} · ${sp.material}`, colour: sp.colour }))];
</script>

<template>
  <section class="hs" aria-labelledby="hs-title">
    <h3 id="hs-title" class="hs-title">{{ t('setup.headsSettings') }}</h3>
    <p class="oui-meta">{{ t('setup.headsHint') }}</p>
    <p v-if="status[-1]?.error" class="u1-note" data-tone="error" role="alert">{{ status[-1].text }}</p>
    <form v-for="(h, i) in heads" :key="h.index" class="hs-row" :data-head="i" @submit.prevent="save(i)">
      <span class="hs-name"><span class="u1-tool" :data-tool="i + 1">T{{ i + 1 }}</span></span>
      <label class="oui-sr" :for="`hs-v-${i}`">{{ t('edit.vendor') }}</label>
      <InputText :id="`hs-v-${i}`" v-model="forms[i].vendor" size="small" class="hs-vendor" :placeholder="t('edit.vendor')" :disabled="disabled" />
      <Select v-model="forms[i].type" :options="TYPES" size="small" :aria-label="t('edit.type') + ' T' + (i + 1)" :disabled="disabled" />
      <input v-model="forms[i].colour" type="color" class="hs-colour" :aria-label="t('edit.colour') + ' T' + (i + 1)" :disabled="disabled">
      <Button type="submit" size="small" severity="secondary" :label="t('common.save')" :loading="status[i]?.busy" :disabled="disabled" />
      <Select v-if="spools.length" :model-value="bindings[String(i)] ?? 0" :options="spoolOptions()" option-label="label" option-value="id" size="small" class="hs-spool"
              :aria-label="t('setup.spoolFor', { n: i + 1 })" :disabled="disabled || status[i]?.busy" @update:model-value="v => link(i, v)">
        <template #option="{ option }"><span class="hs-opt"><OuiSwatch v-if="option.id" :color="option.colour" :size="12" />{{ option.label }}</span></template>
      </Select>
      <p v-if="status[i]?.text" class="u1-note hs-status" :data-tone="status[i].error ? 'error' : undefined" role="status">{{ status[i].text }}</p>
    </form>
  </section>
</template>

<style>
.hs { display: grid; gap: var(--oui-s2); padding: var(--oui-s3) var(--oui-s4); border-radius: var(--oui-radius-lg); background: var(--oui-raised); box-shadow: inset 0 0 0 1px var(--oui-border); }
.hs-title { font-weight: 700; }
.hs-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s2); padding-top: var(--oui-s2); border-top: 1px solid var(--oui-border); }
.hs-vendor { width: 9rem; min-width: 0; }
.hs-spool { flex: 1 1 14rem; min-width: 0; }
.hs-colour { width: 40px; height: var(--oui-control-sm); padding: 0; border: 1px solid var(--oui-control-border); border-radius: var(--oui-radius); background: none; }
.hs-opt { display: inline-flex; align-items: center; gap: 6px; }
.hs-status { flex-basis: 100%; margin: 0; }
</style>
