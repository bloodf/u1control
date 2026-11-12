<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import Icon from './Icon.vue';
import FirmwareCard from './FirmwareCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import { s, run, tracker, controlsOff, busy, loadSpools, printerName } from '../app/store';
import { config, form, dirty, saving, save, valueOf } from '../app/settings';
import { ask } from '../core/dialog';
import { t, tMaybe, langPref, setLangPref, autoLocale, fmt } from '../core/i18n';
import type { Automation } from '../app/types';
import type { LangPref } from '../core/i18n-core';
import { boot } from '../core/boot';

const autos = computed(() => config.value?.automations ?? []);
const autoLabel = (a: Automation) => tMaybe(`auto.${a.key}`, a.label);
const choiceLabel = (v: unknown) => (typeof v === 'boolean' ? t(v ? 'mode.on' : 'mode.off') : tMaybe(`choice.${v}`, String(v)));
const setDraft = (k: string, v: unknown) => { form.draft = { ...form.draft, [k]: v }; };
const showKey = ref(false);

const smInfo = computed(() => s.spoolsError || (s.spoolsLoaded
  ? (s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n: s.spools.length }) : t('heads.source.direct', { n: s.spools.length })) : t('sm.notLoaded')));

const PREFS = ['bed_level', 'flow_calibrate', 'time_lapse_camera', 'auto_refill', 'refill_any_colour', 'tangle_detect', 'unload_when_done', 'light_off_when_done'];
const prefs = computed(() => Object.entries(s.status?.options ?? {}));
const prefLabel = (k: string) => (PREFS.includes(k) ? t(`pref.${k}` as any) : k);
async function setPref(k: string, v: boolean) {
  await run({ key: `pref:${k}`, label: t('act.prefs'), cmd: 'preferences', args: { prefs: { [k]: v } }, okText: t('ok.prefs') });
}

const CAL = [{ kind: 'bed_mesh', label: 'cal.bed_mesh' }, { kind: 'input_shaper', label: 'cal.input_shaper' }, { kind: 'flow', label: 'cal.flow' }] as const;
const calWhy = computed(() => controlsOff.value || (busy.value ? t('cal.busy') : ''));
async function calibrate(kind: string, name: string) {
  if (!await ask({ title: t('cal.title'), text: t('confirm.cal.text', { name, printer: printerName.value }), yes: t('confirm.cal.yes'), no: t('common.goBack') })) return;
  await run({ key: `cal:${kind}`, label: t('act.calibrate'), cmd: 'calibrate', args: { kind }, okText: t('ok.calibrate'), timeoutMs: 60000 });
}
const langOptions = computed(() => [
  { value: 'auto', label: t('lang.auto', { current: t(`lang.${autoLocale.value}`) }) },
  { value: 'en', label: t('lang.en') }, { value: 'pt-BR', label: t('lang.pt-BR') }]);
</script>

<template>
  <div class="sv">
    <section class="u1-card" aria-labelledby="mode-h">
      <div class="u1-row">
        <h2 id="mode-h" class="sv-h">{{ t('mode.title') }}</h2><span class="u1-spacer" />
        <span v-if="dirty" class="u1-warn" role="status">{{ t('mode.unsaved') }}</span>
        <Button :label="saving ? t('mode.saving') : t('common.save')" :loading="saving" :disabled="!config" data-test="save-top" @click="save" />
      </div>
      <p v-if="!config" class="oui-muted">{{ t('mode.notLoaded') }}</p>
      <template v-else>
        <div class="u1-row" role="group" :aria-label="t('mode.title')">
          <Button :severity="form.mode === 'automagic' ? undefined : 'secondary'" :outlined="form.mode !== 'automagic'" :aria-pressed="form.mode === 'automagic'"
                  data-mode="automagic" @click="form.mode = 'automagic'"><Icon name="icon/automagic" /><span>{{ t('mode.automagic') }}</span></Button>
          <Button :severity="form.mode === 'expert' ? undefined : 'secondary'" :outlined="form.mode !== 'expert'" :aria-pressed="form.mode === 'expert'"
                  data-mode="expert" @click="form.mode = 'expert'"><Icon name="icon/expert" /><span>{{ t('mode.expert') }}</span></Button>
        </div>
        <p class="oui-meta">{{ form.mode === 'expert' ? t('mode.help.expert') : t('mode.help.automagic') }}</p>
        <table v-if="form.mode === 'automagic'" class="u1-table">
          <tbody><tr v-for="a in autos" :key="a.key"><td>{{ autoLabel(a) }}</td><td class="oui-muted">{{ choiceLabel(a.automagic) }}</td></tr></tbody>
        </table>
        <div v-else class="sv-autos">
          <template v-for="a in autos" :key="a.key">
            <label :for="`auto-${a.key}`">{{ autoLabel(a) }}<span class="oui-meta sv-help">{{ tMaybe(`autohelp.${a.key}`, a.help) }}</span></label>
            <Select v-if="a.choices" :input-id="`auto-${a.key}`" :model-value="valueOf(a.key)" :options="a.choices.map(c => ({ value: c, label: choiceLabel(c) }))"
                    option-label="label" option-value="value" :aria-label="autoLabel(a)" :data-auto="a.key" @update:model-value="setDraft(a.key, $event)" />
            <Checkbox v-else :input-id="`auto-${a.key}`" binary :model-value="!!valueOf(a.key)" :data-auto="a.key" @update:model-value="setDraft(a.key, $event)" />
          </template>
        </div>
      </template>
    </section>

    <section class="u1-card" aria-labelledby="sm-h">
      <h2 id="sm-h"><Icon name="icon/spoolman" /> {{ t('sm.title') }}</h2>
      <div class="u1-row"><span class="oui-muted" role="status">{{ smInfo }}</span><span class="u1-spacer" />
        <Button severity="secondary" outlined :disabled="!!controlsOff" :loading="tracker.isBusy('spools')" @click="loadSpools(false)">
          <Icon name="icon/spoolman" /><span>{{ t('sm.refresh') }}</span></Button></div>
    </section>

    <section class="u1-card" aria-labelledby="pref-h">
      <h2 id="pref-h">{{ t('prefs.title') }}</h2>
      <p class="oui-meta">{{ t('prefs.help') }}</p>
      <div v-if="prefs.length" class="sv-prefs">
        <span v-for="[k, v] in prefs" :key="k" class="u1-row">
          <Checkbox :input-id="`pref-${k}`" binary :model-value="!!v" :disabled="k === 'unload_when_done' || !!controlsOff || busy || tracker.isBusy(`pref:${k}`)"
                    :data-pref="k" @update:model-value="setPref(k, $event)" />
          <label :for="`pref-${k}`">{{ prefLabel(k) }} <span v-if="k === 'unload_when_done'" class="oui-muted">{{ t('prefs.inSetup') }}</span></label>
        </span>
      </div>
      <p v-else class="oui-muted">{{ t('prefs.none') }}</p>
      <p v-if="prefs.length && (controlsOff || busy)" class="u1-why">{{ controlsOff || t('reason.busy') }}</p>
    </section>

    <section class="u1-card" aria-labelledby="cal-h">
      <h2 id="cal-h"><Icon name="icon/calibration" /> {{ t('cal.title') }}</h2>
      <div class="u1-row">
        <Button v-for="c in CAL" :key="c.kind" severity="secondary" outlined :disabled="!!calWhy" :loading="tracker.isBusy(`cal:${c.kind}`)"
                :data-cal="c.kind" :data-focus-key="`cal:${c.kind}`" @click="calibrate(c.kind, t(c.label))"><Icon name="icon/calibration" /><span>{{ t(c.label) }}</span></Button>
      </div>
      <div v-if="busy && !controlsOff" class="sv-busy" role="status"><Icon name="spot/printer-busy" :size="96" /><span>{{ t('cal.busy') }}</span></div>
      <p class="u1-why">{{ controlsOff || t('cal.help') }}</p>
    </section>

    <FirmwareCard />
    <SpoolerHint where="settings" />

    <section class="u1-card" aria-labelledby="conn-h">
      <h2 id="conn-h">{{ t('conn.title') }}</h2>
      <form class="sv-conn" @submit.prevent="save">
        <label for="c-host">{{ t('conn.host') }}</label><InputText id="c-host" v-model="form.host" :placeholder="t('conn.hostPh')" />
        <label for="c-key">{{ t('conn.key') }}</label>
        <span class="u1-row"><InputText id="c-key" v-model="form.apiKey" :type="showKey ? 'text' : 'password'" autocomplete="off" :placeholder="t('conn.keyPh')" class="sv-grow" />
          <Checkbox v-model="showKey" input-id="c-key-show" binary /><label for="c-key-show">{{ t('conn.showKey') }}</label></span>
        <label for="c-name">{{ t('conn.name') }}</label><InputText id="c-name" v-model="form.name" />
        <label for="c-sm">{{ t('conn.sm') }}</label><InputText id="c-sm" v-model="form.spoolman" :placeholder="t('conn.smPh')" />
        <span /><div class="u1-row"><span v-if="dirty" class="u1-warn">{{ t('mode.unsaved') }}</span>
          <Button type="submit" :label="saving ? t('mode.saving') : t('common.save')" :loading="saving" :disabled="!config" data-test="save" /></div>
      </form>
    </section>

    <section class="u1-card" aria-labelledby="lang-h">
      <h2 id="lang-h">{{ t('lang.title') }}</h2>
      <div class="u1-row"><label id="lang-l">{{ t('lang.label') }}</label>
        <Select :model-value="langPref" :options="langOptions" option-label="label" option-value="value" aria-labelledby="lang-l" data-test="lang"
                @update:model-value="setLangPref($event as LangPref)" /></div>
      <p class="oui-meta">{{ t('lang.help') }}</p>
      <p class="oui-meta">{{ t('about.text', { version: config?.version || boot.version }) }}</p>
    </section>
  </div>
</template>
<style scoped>
.sv { display: grid; gap: 16px; max-width: 1000px; }
.sv-h { margin: 0; }
.sv-autos { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px 16px; align-items: center; }
.sv-help { display: block; }
.sv-prefs { display: flex; flex-wrap: wrap; gap: 8px 20px; }
.sv-conn { display: grid; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr); gap: 12px; align-items: center; }
.sv-grow { flex: 1; min-width: 0; }
.sv-busy { display: flex; align-items: center; gap: 12px; color: var(--oui-muted); }
@media (max-width: 640px) { .sv-conn { grid-template-columns: minmax(0, 1fr); } }
</style>
