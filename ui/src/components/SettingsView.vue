<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiBanner, OuiEmpty, OuiFormRow, OuiFormSection, OuiIcon, OuiSettings, OuiStatus, type OuiSettingsSection } from '../../shared/src/components';
import { clipboard, info, languages, plug, printer, refresh, save as saveIcon, spoolman, target, wrench, zap } from '../../shared/src/icons';
import FirmwareCard from './FirmwareCard.vue';
import SpoolerHint from './SpoolerHint.vue';
import { s, run, tracker, controlsOff, busy, loadSpools, printerName } from '../app/store';
import { config, form, dirty, saving, save, discard, valueOf } from '../app/settings';
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
// Why printer options and calibration are off is said once for the page (#heads-why).
const why = computed(() => (controlsOff.value || busy.value ? 'heads-why' : undefined));
async function calibrate(kind: string, name: string) {
  if (!await ask({ title: t('cal.title'), text: t('confirm.cal.text', { name, printer: printerName.value }), yes: t('confirm.cal.yes'), no: t('common.goBack') })) return;
  await run({ key: `cal:${kind}`, label: t('act.calibrate'), cmd: 'calibrate', args: { kind }, okText: t('ok.calibrate'), timeoutMs: 60000 });
}
// When the toolhead choice (U1 print setup) runs and when its pop-up opens: a print sent without asking is easy to
// mistake for a broken setup.
const pipe = computed(() => config.value?.pipeline ?? null);
const dialogRule = computed(() => tMaybe(`ps.dialog.${config.value?.settings.print_dialog}`, ''));
const langOptions = computed(() => [
  { value: 'auto', label: t('lang.auto', { current: t(`lang.${autoLocale.value}`) }) },
  { value: 'en', label: t('lang.en') }, { value: 'pt-BR', label: t('lang.pt-BR') }]);
const sections = computed<OuiSettingsSection[]>(() => [
  { id: 'mode', label: t('mode.title'), icon: zap },
  { id: 'print-setup', label: t('ps.title'), icon: printer, ...(pipe.value && !pipe.value.on ? { state: 'warn' as const } : {}) },
  { id: 'options', label: t('prefs.title'), icon: clipboard },
  { id: 'calibration', label: t('cal.title'), icon: target },
  { id: 'connection', label: t('conn.title'), icon: plug },
  { id: 'spoolman', label: t('sm.title'), icon: spoolman },
  { id: 'firmware', label: t('ext.title'), icon: wrench },
  { id: 'language', label: t('lang.title'), icon: languages },
  { id: 'about', label: t('about.title'), icon: info },
]);
// Enter in a text field saves, as the form's own button did.
function onEnter(e: KeyboardEvent) { if (e.target instanceof HTMLInputElement && e.target.type !== 'checkbox') { e.preventDefault(); void save(); } }
</script>


<template>
  <OuiSettings :sections="sections" :nav-label="t('settings.nav')">
    <div class="oui-stack">
      <OuiFormSection id="mode" :icon="zap" :title="t('mode.title')" :aria-label="t('mode.title')"
                      :description="config ? (form.mode === 'expert' ? t('mode.help.expert') : t('mode.help.automagic')) : undefined">
        <OuiEmpty v-if="!config" compact state="loading" :title="t('mode.notLoaded')" />
        <template v-else>
          <div class="oui-row u1-pad" role="group" :aria-label="t('mode.title')">
            <Button :severity="form.mode === 'automagic' ? undefined : 'secondary'" :label="t('mode.automagic')" :aria-pressed="form.mode === 'automagic'"
                    data-mode="automagic" @click="form.mode = 'automagic'"><template #icon><OuiIcon :icon="zap" :size="14" /></template></Button>
            <Button :severity="form.mode === 'expert' ? undefined : 'secondary'" :label="t('mode.expert')" :aria-pressed="form.mode === 'expert'"
                    data-mode="expert" @click="form.mode = 'expert'"><template #icon><OuiIcon :icon="wrench" :size="14" /></template></Button>
          </div>
          <template v-if="form.mode === 'automagic'">
            <OuiFormRow v-for="a in autos" :key="a.key" :label="autoLabel(a)"><span class="oui-muted">{{ choiceLabel(a.automagic) }}</span></OuiFormRow>
          </template>
          <template v-else>
            <OuiFormRow v-for="a in autos" :key="a.key" :label="autoLabel(a)" :for="`auto-${a.key}`" :hint="tMaybe(`autohelp.${a.key}`, a.help)">
              <Select v-if="a.choices" :label-id="`auto-${a.key}`" :model-value="valueOf(a.key)" :options="a.choices.map(c => ({ value: c, label: choiceLabel(c) }))"
                      option-label="label" option-value="value" :aria-label="autoLabel(a)" :data-auto="a.key" @update:model-value="setDraft(a.key, $event)" />
              <ToggleSwitch v-else :input-id="`auto-${a.key}`" :model-value="!!valueOf(a.key)" :data-auto="a.key" @update:model-value="setDraft(a.key, $event)" />
            </OuiFormRow>
          </template>
        </template>
      </OuiFormSection>

      <OuiFormSection v-if="config" id="print-setup" :icon="printer" :title="t('ps.title')" :aria-label="t('ps.title')" data-test="print-setup">
        <div class="oui-stack u1-pad">
          <OuiBanner v-if="pipe && !pipe.on" tone="warn" :title="t('ps.off', { preset: pipe.preset })" data-test="ps-off">
            {{ config.settings.auto_add_pipeline ? t('ps.offAuto') : t('ps.offManual') }}</OuiBanner>
          <p v-else-if="pipe" data-test="ps-on">{{ t('ps.on', { preset: pipe.preset }) }}</p>
          <p v-if="dialogRule" data-test="ps-rule">{{ dialogRule }}</p>
          <p class="oui-meta">{{ t('ps.how') }}</p>
        </div>
      </OuiFormSection>

      <OuiFormSection id="options" :icon="clipboard" tone="cobalt" :title="t('prefs.title')" :aria-label="t('prefs.title')" :description="t('prefs.help')">
        <OuiFormRow v-for="[k, v] in prefs" :key="k" :label="prefLabel(k)" :for="`pref-${k}`" :hint="k === 'unload_when_done' ? t('prefs.inSetup') : undefined">
          <ToggleSwitch :input-id="`pref-${k}`" :model-value="!!v" :disabled="k === 'unload_when_done' || !!controlsOff || busy || tracker.isBusy(`pref:${k}`)"
                        :aria-describedby="k === 'unload_when_done' ? undefined : why" :data-pref="k" @update:model-value="setPref(k, $event)" />
        </OuiFormRow>
        <p v-if="!prefs.length" class="oui-muted u1-pad">{{ t('prefs.none') }}</p>
      </OuiFormSection>

      <OuiFormSection id="calibration" :icon="target" tone="cobalt" :title="t('cal.title')" :aria-label="t('cal.title')" :description="busy && !controlsOff ? t('cal.busy') : t('cal.help')">
        <div class="oui-row u1-pad">
          <Button v-for="c in CAL" :key="c.kind" severity="secondary" :label="t(c.label)" :disabled="!!calWhy" :aria-describedby="why" :loading="tracker.isBusy(`cal:${c.kind}`)"
                  :data-cal="c.kind" :data-focus-key="`cal:${c.kind}`" @click="calibrate(c.kind, t(c.label))"><template #icon><OuiIcon :icon="target" :size="14" /></template></Button>
        </div>
      </OuiFormSection>
    </div>

    <div class="oui-stack">
      <OuiFormSection id="connection" :icon="plug" tone="cobalt" :title="t('conn.title')" :aria-label="t('conn.title')">
        <form class="oui-formsection-rows" @submit.prevent="save" @keydown.enter="onEnter">
          <OuiFormRow :label="t('conn.host')" for="c-host"><InputText id="c-host" v-model="form.host" class="oui-mono" :placeholder="t('conn.hostPh')" /></OuiFormRow>
          <OuiFormRow :label="t('conn.key')" for="c-key">
            <InputText id="c-key" v-model="form.apiKey" class="oui-mono" :type="showKey ? 'text' : 'password'" autocomplete="off" :placeholder="t('conn.keyPh')" />
            <label class="u1-inline" for="c-key-show"><Checkbox v-model="showKey" input-id="c-key-show" binary />{{ t('conn.showKey') }}</label>
          </OuiFormRow>
          <OuiFormRow :label="t('conn.name')" for="c-name"><InputText id="c-name" v-model="form.name" /></OuiFormRow>
          <OuiFormRow :label="t('conn.sm')" for="c-sm"><InputText id="c-sm" v-model="form.spoolman" class="oui-mono" :placeholder="t('conn.smPh')" /></OuiFormRow>
        </form>
      </OuiFormSection>

      <OuiFormSection id="spoolman" :icon="spoolman" tone="magenta" :title="t('sm.title')" :aria-label="t('sm.title')">
        <template #actions>
          <Button severity="secondary" size="small" :label="t('sm.refresh')" :disabled="!!controlsOff" :aria-describedby="controlsOff ? 'heads-why' : undefined" :loading="tracker.isBusy('spools')" @click="loadSpools(false)">
            <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
        <div class="oui-stack u1-pad">
          <p role="status" :class="{ 'u1-note': !!s.spoolsError }" :data-tone="s.spoolsError ? 'danger' : undefined">{{ smInfo }}</p>
          <SpoolerHint where="settings" />
        </div>
      </OuiFormSection>

      <FirmwareCard />

      <OuiFormSection id="language" :icon="languages" tone="neutral" :title="t('lang.title')" :aria-label="t('lang.title')">
        <OuiFormRow :label="t('lang.label')" :hint="t('lang.help')">
          <Select :model-value="langPref" :options="langOptions" option-label="label" option-value="value" :aria-label="t('lang.label')" data-test="lang"
                  @update:model-value="setLangPref($event as LangPref)" />
        </OuiFormRow>
      </OuiFormSection>

      <OuiFormSection id="about" :icon="info" tone="neutral" :title="t('about.title')" :aria-label="t('about.title')">
        <p class="oui-meta u1-pad">{{ t('about.text', { version: config?.version || boot.version }) }}</p>
      </OuiFormSection>
    </div>

    <template #footer>
      <OuiStatus v-if="dirty" state="pending" role="status">{{ t('mode.unsaved') }}</OuiStatus>
      <span class="oui-spacer" />
      <Button severity="secondary" text :label="t('settings.discard')" :disabled="!dirty || saving" data-test="discard" @click="discard" />
      <Button :label="saving ? t('mode.saving') : t('common.save')" :loading="saving" :disabled="!config" data-test="save" @click="save"><template #icon><OuiIcon :icon="saveIcon" :size="14" /></template></Button>
    </template>
  </OuiSettings>
</template>
