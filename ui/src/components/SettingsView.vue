<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import Checkbox from 'primevue/checkbox';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiBanner, OuiEmpty, OuiFormRow, OuiFormSection, OuiIcon, OuiRequirement, OuiStatus, type OuiSettingsSection } from '@orca-plugins/ui-foundation/src/components';
import { chart, circleCheck, clipboard, drop, external, grid, info, languages, plug, printer, refresh, save as saveIcon, settings as settingsIcon, target, wrench, zap } from '@orca-plugins/ui-foundation/src/icons';
import { themePref, setThemePref, type ThemePref } from '../core/theme';
import FirmwareCard from './FirmwareCard.vue';
import SettingsPages from './SettingsPages.vue';
import { s, run, tracker, controlsOff, busy, printerName, targetKnown, loadRequirements, checkRequirements } from '../app/store';
import { config, form, dirty, saving, save, discard, valueOf } from '../app/settings';
import { ask } from '../core/dialog';
import { t, tMaybe, langPref, setLangPref, autoLocale, fmt, clockPref, setClockPref } from '../core/i18n';
import type { ClockPref } from '../core/i18n-core';
import { LOCALES } from '../core/i18n-core';
import type { Automation, Requirement } from '../app/types';
import type { LangPref } from '../core/i18n-core';
import { boot } from '../core/boot';
import * as bridge from '../core/bridge';

// Settings > Connection: how often the page re-reads Spoolman (stored by the plugin as spoolman_refresh_s; 0 = off).
const REFRESH = computed(() => [0, 10, 15, 30, 60, 120, 300].map(n => ({ value: n, label: n ? t('sm.refreshOption', { n }) : t('sm.refreshOff') })));
function setRefresh(n: number) { bridge.post({ type: 'spoolman_refresh', value: n }); }

const autos = computed(() => config.value?.automations ?? []);
const autoLabel = (a: Automation) => tMaybe(`auto.${a.key}`, a.label);
const choiceLabel = (v: unknown) => (typeof v === 'boolean' ? t(v ? 'mode.on' : 'mode.off') : tMaybe(`choice.${v}`, String(v)));
const setDraft = (k: string, v: unknown) => { form.draft = { ...form.draft, [k]: v }; };
const showKey = ref(false);
const smInfo = computed(() => s.spoolsError || (s.spoolsLoaded
  ? (s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n: s.spools.length }) : t('heads.source.direct', { n: s.spools.length })) : t('sm.notLoaded')));

// Unload when done is chosen per toolhead in the print setup pop-up, so it has no row here (it could never be changed).
const PREFS = ['bed_level', 'flow_calibrate', 'time_lapse_camera', 'auto_refill', 'refill_any_colour', 'tangle_detect', 'unload_when_done', 'light_off_when_done', 'spaghetti_detect', 'bed_check'];
const CAMERA = ['spaghetti_detect', 'bed_check'];   // shown only when the printer has DEFECT_DETECTION_CONFIG
const prefs = computed(() => Object.entries(s.status?.options ?? {}).filter(([k]) => k !== 'unload_when_done' && (!CAMERA.includes(k) || (s.status?.features ?? []).includes(k))));
const prefLabel = (k: string) => (PREFS.includes(k) ? t(`pref.${k}` as any) : k);
async function setPref(k: string, v: boolean) {
  await run({ key: `pref:${k}`, label: t('act.prefs'), cmd: 'preferences', args: { prefs: { [k]: v } }, okText: t('ok.prefs') });
}

const CAL = [{ kind: 'bed_mesh', label: 'cal.bed_mesh', help: 'cal.meshHelp', icon: grid }, { kind: 'input_shaper', label: 'cal.input_shaper', help: 'cal.shaperHelp', icon: chart },
  { kind: 'flow', label: 'cal.flow', help: 'cal.flowHelp', icon: drop }] as const;
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
const modeOptions = computed(() => [{ value: 'automagic', label: t('mode.automagic'), icon: zap }, { value: 'expert', label: t('mode.expert'), icon: wrench }]);
const themeOptions = computed(() => (['auto', 'light', 'dark'] as const).map(value => ({ value, label: t(`theme.${value}`) })));
const clockOptions = computed(() => (['auto', '24', '12'] as const).map(value => ({ value, label: t(`clock.${value}`) })));
const langOptions = computed(() => [
  { value: 'auto', label: t('lang.auto', { current: t(`lang.${autoLocale.value}`) }) },
  ...LOCALES.map(value => ({ value, label: t(`lang.${value}`) }))]);
// Settings > Requirements: what some features need and the plugin can't install. The plugin's check
// (requirements.py, the "requirements" message) is the one source; each row is ui-foundation's OuiRequirement.
const EXT_URL = 'https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware';
const AGENT_DOCS = 'https://github.com/bloodf/u1control/blob/main/docs/features.md#printer-agent';
const SPOOLMAN_URL = 'https://github.com/Donkie/Spoolman';
type ReqStatus = 'found' | 'missing' | 'checking' | 'unknown';
const FOUND = { ok: 'found', missing: 'missing', unknown: 'unknown' } as const;
// One chip vocabulary for every row; what was found (or why not) is the row's detail.
const CHIP = { found: 'req.found', missing: 'req.missing', checking: 'req.checking', unknown: 'req.unknown' } as const;
const reqs = computed(() => {
  const by = (id: Requirement['id']): Requirement => s.requirements.find(r => r.id === id) ?? { id, status: 'unknown', details: {} };
  const agents = by('printer_agents'), ext = by('extended_firmware'), sm = by('spoolman'), sp = by('spooler');
  const asked = (st: ReqStatus): ReqStatus => (s.reqChecking ? 'checking' : st);
  // Spoolman: the plugin says whether one is set; a failed spool load (the live answer) says it isn't reachable.
  const smState: ReqStatus = tracker.isBusy('spools') ? 'checking' : s.spoolsError && targetKnown.value ? 'missing' : FOUND[sm.status];
  const smWhere = sm.details.url ? t('req.sm.direct', { url: sm.details.url }) : sm.details.via === 'printer' ? t('req.sm.printer')
    : sm.status === 'missing' ? t('req.sm.missing') : sm.status === 'unknown' ? t('req.sm.unknown') : '';
  const lines = (...keys: string[]) => keys.map(k => t(k as any)).join('\n');
  return [
    // Plugins can't read the preference: "not detected" is shown as missing (a warning) with the steps, never an error.
    { key: 'agents', test: 'req-agents', name: t('req.agents.name'), why: t('req.agents.why'), status: asked(agents.status === 'ok' ? 'found' : 'missing'),
      detail: agents.status === 'ok' ? '' : t('req.agents.note'), install: lines('req.agents.step1', 'req.agents.step2', 'req.agents.step3', 'req.agents.step4'),
      url: AGENT_DOCS, urlLabel: t('req.agents.link') },
    { key: 'ext', test: 'req-ext', name: t('req.ext.name'), why: t('req.ext.why'), status: asked(FOUND[ext.status]),
      detail: ext.status === 'unknown' ? t('req.ext.unknown') : ext.status === 'missing' ? t('req.ext.missing') : ext.details.version ? t('req.ext.version', { version: ext.details.version }) : '',
      install: lines('req.ext.step1', 'req.ext.step2', 'req.ext.step3', 'req.ext.step4'), url: EXT_URL, urlLabel: t('ext.link') },
    { key: 'spoolman', test: 'req-spoolman', name: t('sm.title'), why: t('req.sm.why'), status: smState,
      detail: [smWhere, s.spoolsLoaded || s.spoolsError ? smInfo.value : ''].filter(Boolean).join(' · '),
      install: lines('req.sm.step1', 'req.sm.step2', 'req.sm.step3'), url: SPOOLMAN_URL, urlLabel: t('req.sm.link') },
    { key: 'spooler', test: 'req-spooler', name: t('spooler.title'), why: t('req.spooler.why'), status: asked(FOUND[sp.status]),
      detail: sp.status === 'ok' ? t('spooler.installed') : '', install: t('spooler.suggest'), url: sp.details.url, urlLabel: undefined },
  ].map(r => ({ ...r, label: t(CHIP[r.status]) }));
});
// One Check again for the list: the plugin looks again and, with a printer that answers, the spools are read again
// (checkRequirements), which is what says whether Spoolman is reachable. Off only while the plugin looks.
const reqBusy = computed(() => s.reqChecking);
// About: where to read more. Opened as normal links (the plugin's page opens them in the system browser).
const REPO = 'https://github.com/bloodf/u1control';
const ABOUT_LINKS = computed(() => [
  { href: `${REPO}/blob/main/CHANGELOG.md`, label: t('about.whatsNew') },
  { href: `${REPO}#readme`, label: t('about.docs') },
  { href: `${REPO}/issues`, label: t('about.report') },
  { href: `${REPO}/blob/main/docs/credits.md`, label: t('about.licences') }]);
onMounted(() => loadRequirements());
const sections = computed<OuiSettingsSection[]>(() => [
  { id: 'general', label: t('settings.general'), icon: settingsIcon },
  { id: 'printing', label: t('settings.printing'), icon: printer, ...(pipe.value && !pipe.value.on ? { state: 'warn' as const } : {}) },
  { id: 'connection', label: t('conn.title'), icon: plug },
  { id: 'printer', label: t('settings.printer'), icon: target },
  { id: 'about', label: t('about.title'), icon: info },
]);
// The pages before they were grouped: links (openSettings) and #<id> addresses naming one open the page holding it,
// at that group.
const HOME: Record<string, string> = { mode: 'general', language: 'general', 'print-setup': 'printing', options: 'printing', calibration: 'printer', firmware: 'printer', requirements: 'about' };
// The pages with fields that wait for Save; the others apply each change at once. With a change waiting, the bar
// shows on every page, so it is never left behind unseen.
const SAVES = ['general', 'connection'];
// A "Settings" link elsewhere (openSettings(page)) opens its page once Settings shows and the page is on it (some
// wait for the plugin's config).
const pages = ref<InstanceType<typeof SettingsPages>>();
watch(() => [s.settingsPage, s.tab, !!config.value], () => {
  const id = s.settingsPage;
  if (!id || s.tab !== 'settings' || !document.getElementById(id)) return;
  s.settingsPage = '';
  pages.value?.select(id);
}, { immediate: true, flush: 'post' });
const showBar = computed(() => dirty.value || SAVES.includes(pages.value?.current ?? ''));
// Enter in a text field saves, as the form's own button did, once something changed.
function onEnter(e: KeyboardEvent) { if (e.target instanceof HTMLInputElement && e.target.type !== 'checkbox') { e.preventDefault(); if (dirty.value) void save(); } }
</script>


<template>
  <SettingsPages ref="pages" :sections="sections" :home="HOME" :nav-label="t('settings.nav')" :back-label="t('settings.back')" :error-label="t('settings.hasError')">
    <div id="general" class="u1-page">
      <OuiFormSection id="mode" :icon="zap" :title="t('mode.title')" :aria-label="t('mode.title')"
                      :description="config ? (form.mode === 'expert' ? t('mode.help.expert') : t('mode.help.automagic')) : undefined">
        <OuiEmpty v-if="!config" compact state="loading" :title="t('mode.notLoaded')" />
        <template v-else>
          <div class="u1-pad">
            <SelectButton :model-value="form.mode" :options="modeOptions" option-label="label" option-value="value" :allow-empty="false" :aria-label="t('mode.title')"
                          data-test="mode" @update:model-value="form.mode = $event">
              <template #option="{ option }"><OuiIcon :icon="option.icon" :size="14" /><span :data-mode="option.value">{{ option.label }}</span></template>
            </SelectButton>
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

      <OuiFormSection id="language" :icon="languages" tone="neutral" :title="t('lang.title')" :aria-label="t('lang.title')">
        <OuiFormRow :label="t('lang.label')" :hint="t('lang.help')">
          <Select :model-value="langPref" :options="langOptions" option-label="label" option-value="value" :aria-label="t('lang.label')" data-test="lang"
                  @update:model-value="setLangPref($event as LangPref)" />
        </OuiFormRow>
        <OuiFormRow :label="t('theme.label')">
          <Select :model-value="themePref" :options="themeOptions" option-label="label" option-value="value" :aria-label="t('theme.label')" data-test="theme"
                  @update:model-value="setThemePref($event as ThemePref)" />
        </OuiFormRow>
        <OuiFormRow :label="t('clock.label')" :hint="t('clock.help')">
          <Select :model-value="clockPref" :options="clockOptions" option-label="label" option-value="value" :aria-label="t('clock.label')" data-test="clock"
                  @update:model-value="setClockPref($event as ClockPref)" />
        </OuiFormRow>
      </OuiFormSection>
    </div>

    <div id="printing" class="u1-page">
      <OuiFormSection v-if="config" id="print-setup" :icon="printer" :title="t('ps.title')" :aria-label="t('ps.title')" data-test="print-setup">
        <div class="oui-stack u1-pad">
          <OuiBanner :show="!!pipe && !pipe.on" role="note" tone="warn" :title="t('ps.off', { preset: pipe?.preset ?? '' })" data-test="ps-off"
                     dismissible :dismiss-key="`ps-off:${pipe?.preset ?? ''}`" :close-label="t('common.close')">
            {{ config.settings.auto_add_pipeline ? t('ps.offAuto') : t('ps.offManual') }}</OuiBanner>
          <p v-if="pipe?.on" class="u1-status-line" data-test="ps-on"><OuiStatus state="ok">{{ t('ps.chipOn') }}</OuiStatus><span>{{ t('ps.on', { preset: pipe.preset }) }}</span></p>
          <details class="u1-details" data-test="ps-when"><summary>{{ t('ps.when') }}</summary>
            <div class="oui-stack"><p v-if="dialogRule" data-test="ps-rule">{{ dialogRule }}</p><p class="oui-meta">{{ t('ps.how') }}</p></div></details>
          <details class="u1-details"><summary>{{ t('ps.withAgents') }}</summary><p class="oui-meta" data-test="ps-agent">{{ t('ps.agent') }}</p></details>
        </div>
      </OuiFormSection>

      <OuiFormSection id="options" :icon="clipboard" :title="t('prefs.title')" :aria-label="t('prefs.title')" :description="t('prefs.help')">
        <OuiFormRow v-for="[k, v] in prefs" :key="k" :label="prefLabel(k)" :for="`pref-${k}`">
          <ToggleSwitch :input-id="`pref-${k}`" :model-value="!!v" :disabled="!!controlsOff || busy || tracker.isBusy(`pref:${k}`)"
                        :aria-describedby="why" :data-pref="k" @update:model-value="setPref(k, $event)" />
        </OuiFormRow>
        <p v-if="!prefs.length" class="oui-muted u1-pad">{{ t('prefs.none') }}</p>
      </OuiFormSection>
    </div>

    <OuiFormSection id="connection" :icon="plug" :title="t('conn.title')" :aria-label="t('conn.title')">
      <form class="oui-formsection-rows" @submit.prevent="save" @keydown.enter="onEnter">
        <OuiFormRow :label="t('conn.host')" for="c-host"><InputText id="c-host" v-model="form.host" class="oui-mono" :placeholder="t('conn.hostPh')" /></OuiFormRow>
        <OuiFormRow :label="t('conn.key')" for="c-key">
          <InputText id="c-key" v-model="form.apiKey" class="oui-mono" :type="showKey ? 'text' : 'password'" autocomplete="off" :placeholder="t('conn.keyPh')" />
          <label class="u1-inline" for="c-key-show"><Checkbox v-model="showKey" input-id="c-key-show" binary />{{ t('conn.showKey') }}</label>
        </OuiFormRow>
        <OuiFormRow :label="t('conn.name')" for="c-name"><InputText id="c-name" v-model="form.name" /></OuiFormRow>
        <OuiFormRow :label="t('conn.sm')" for="c-sm"><InputText id="c-sm" v-model="form.spoolman" class="oui-mono" :placeholder="t('conn.smPh')" /></OuiFormRow>
      </form>
      <OuiFormRow :label="t('match.show')" for="match-show" :hint="t('match.showHelp')">
        <ToggleSwitch input-id="match-show" :model-value="valueOf('show_preset_match') !== false" data-test="match-show"
                      @update:model-value="setDraft('show_preset_match', $event)" /></OuiFormRow>
      <OuiFormRow :label="t('sm.refresh')" :hint="t('sm.refreshHelp')">
        <Select :model-value="s.refreshS" :options="REFRESH" option-label="label" option-value="value" :aria-label="t('sm.refresh')" data-test="sm-refresh"
                @update:model-value="setRefresh($event as number)" />
      </OuiFormRow>
    </OuiFormSection>

    <div id="printer" class="u1-page">
      <OuiFormSection id="calibration" :icon="target" tone="cobalt" :title="t('cal.title')" :aria-label="t('cal.title')" :description="busy && !controlsOff ? t('cal.busy') : t('cal.help')">
        <OuiFormRow v-for="c in CAL" :key="c.kind" :label="t(c.label)" :hint="t(c.help)">
          <Button severity="secondary" :label="t('cal.run')" :aria-label="t('cal.runLabel', { name: t(c.label) })" :disabled="!!calWhy" :aria-describedby="why"
                  :loading="tracker.isBusy(`cal:${c.kind}`)" :data-cal="c.kind" :data-focus-key="`cal:${c.kind}`" @click="calibrate(c.kind, t(c.label))">
            <template #icon><OuiIcon :icon="c.icon" :size="14" /></template></Button>
        </OuiFormRow>
      </OuiFormSection>
      <FirmwareCard />
    </div>

    <div id="about" class="u1-page">
      <OuiFormSection :icon="info" tone="neutral" :title="t('about.title')" :aria-label="t('about.title')">
        <div class="oui-stack u1-pad">
          <p class="oui-meta">{{ t('about.text', { version: config?.version || boot.version }) }}</p>
          <ul class="u1-links" data-test="about-links">
            <li v-for="l in ABOUT_LINKS" :key="l.href"><a :href="l.href" target="_blank" rel="noopener noreferrer" class="u1-inline"><OuiIcon :icon="external" :size="14" />{{ l.label }}</a></li>
          </ul>
        </div>
      </OuiFormSection>
      <OuiFormSection id="requirements" :icon="circleCheck" tone="neutral" :title="t('req.title')" :aria-label="t('req.title')" :description="t('req.help')">
        <template #actions>
          <Button size="small" severity="secondary" :label="t('req.check')" :loading="reqBusy" :disabled="reqBusy" data-test="req-check" @click="checkRequirements">
            <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
        </template>
        <div role="status" class="u1-reqs" data-test="requirements">
          <OuiRequirement v-for="r in reqs" :key="r.key" :name="r.name" :why="r.why" :status="r.status" :status-label="r.label" :detail="r.detail || undefined"
                          :install-text="r.install" :install-url="r.url" :install-label="r.urlLabel" :check-label="t('req.check')" :data-test="r.test" />
        </div>
      </OuiFormSection>
    </div>

    <template v-if="showBar" #footer>
      <OuiStatus v-if="dirty" state="pending" role="status">{{ t('mode.unsaved') }}</OuiStatus>
      <span v-else id="set-clean" class="oui-muted">{{ t('settings.clean') }}</span>
      <span class="oui-spacer" />
      <Button severity="secondary" text :label="t('settings.discard')" :disabled="!dirty || saving" data-test="discard" @click="discard" />
      <Button :label="saving ? t('mode.saving') : t('common.save')" :loading="saving" :disabled="!config || !dirty" :aria-describedby="dirty ? undefined : 'set-clean'"
              data-test="save" @click="save"><template #icon><OuiIcon :icon="saveIcon" :size="14" /></template></Button>
    </template>
  </SettingsPages>
</template>
<style>
/* A page holding several groups (General, Printing, Printer, About). */
.u1-page { display: grid; gap: var(--oui-s3); align-content: start; min-width: 0; }
.u1-status-line { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s2); }
.u1-links { display: flex; flex-wrap: wrap; gap: var(--oui-s2) var(--oui-s4); margin: 0; padding: 0; list-style: none; }
.u1-links a { color: var(--oui-primary-text); font-weight: 600; }
/* The install steps are one line each (per step, per OS). */
.u1-reqs .oui-req-install > span { flex-basis: 100%; white-space: pre-line; }
.u1-reqs .oui-req + .oui-req { border-top: 1px solid var(--oui-border); }
/* ponytail: OuiRequirement 5.13 always draws its own Check again and sets details in mono; the section has the one
   Check again. Drop both overrides once the foundation makes them optional (5.14.0). */
.u1-reqs .oui-req-check { display: none; }
.u1-reqs .oui-req-detail { font-family: inherit; font-size: var(--oui-text-sm); }
</style>
