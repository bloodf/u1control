<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiBanner, OuiEmpty, OuiFormRow, OuiFormSection, OuiIcon, OuiRequirement, OuiStatus, type OuiSettingsSection } from '@orca-plugins/ui-foundation/src/components';
import { circleCheck, clipboard, info, languages, plug, printer, save as saveIcon, target, wrench, zap } from '@orca-plugins/ui-foundation/src/icons';
import { themePref, setThemePref, type ThemePref } from '../core/theme';
import FirmwareCard from './FirmwareCard.vue';
import SettingsPages from './SettingsPages.vue';
import { s, run, tracker, controlsOff, busy, loadSpools, printerName, targetKnown, loadRequirements, checkRequirements } from '../app/store';
import { config, form, dirty, saving, save, discard, valueOf } from '../app/settings';
import { ask } from '../core/dialog';
import { t, tMaybe, langPref, setLangPref, autoLocale, fmt } from '../core/i18n';
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
// Open Filament Database (off by default): read only once it is on and saved; the line says which index is kept.
type OfdState = { on: boolean; fetched?: number; version?: string; count?: number; stale?: boolean; error?: string };
const ofdSaved = computed(() => !!config.value?.settings?.ofd_enabled);
const ofdState = ref<OfdState | null>(null);
const ofdBusy = ref(false);
async function askOfd(refresh: boolean): Promise<void> {
  ofdBusy.value = refresh;
  try { ofdState.value = await bridge.request({ type: 'ofd', refresh }); } catch (e) { ofdState.value = { on: true, error: String((e as Error)?.message ?? e) }; }
  finally { ofdBusy.value = false; }
}
const ofdLine = computed(() => {
  const st = ofdState.value;
  if (!st?.on) return '';
  if (!st.count) return st.error ? t('ofd.failed', { error: st.error }) : t('ofd.none');
  const line = t('ofd.status', { date: fmt.dateTime(st.fetched ?? 0), n: st.count });
  return st.error ? `${line} · ${t('ofd.kept', { error: st.error })}` : line;
});
watch(ofdSaved, on => { if (on) void askOfd(false); else ofdState.value = null; }, { immediate: true });

const smInfo = computed(() => s.spoolsError || (s.spoolsLoaded
  ? (s.spoolsVia === 'moonraker' ? t('heads.source.printer', { n: s.spools.length }) : t('heads.source.direct', { n: s.spools.length })) : t('sm.notLoaded')));

const PREFS = ['bed_level', 'flow_calibrate', 'time_lapse_camera', 'auto_refill', 'refill_any_colour', 'tangle_detect', 'unload_when_done', 'light_off_when_done', 'spaghetti_detect', 'bed_check'];
const CAMERA = ['spaghetti_detect', 'bed_check'];   // shown only when the printer has DEFECT_DETECTION_CONFIG
const prefs = computed(() => Object.entries(s.status?.options ?? {}).filter(([k]) => !CAMERA.includes(k) || (s.status?.features ?? []).includes(k)));
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
const themeOptions = computed(() => (['auto', 'light', 'dark'] as const).map(value => ({ value, label: t(`theme.${value}`) })));
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
const reqs = computed(() => {
  const by = (id: Requirement['id']): Requirement => s.requirements.find(r => r.id === id) ?? { id, status: 'unknown', details: {} };
  const agents = by('printer_agents'), ext = by('extended_firmware'), sm = by('spoolman'), sp = by('spooler');
  const asked = (st: ReqStatus): ReqStatus => (s.reqChecking ? 'checking' : st);
  // Spoolman: the plugin says whether one is set; a failed spool load (the live answer) says it isn't reachable.
  const smState: ReqStatus = tracker.isBusy('spools') ? 'checking' : s.spoolsError && targetKnown.value ? 'missing' : FOUND[sm.status];
  const smWhere = sm.details.url ? t('req.sm.direct', { url: sm.details.url }) : sm.details.via === 'printer' ? t('req.sm.printer') : sm.status === 'unknown' ? t('req.sm.unknown') : '';
  const lines = (...keys: string[]) => keys.map(k => t(k as any)).join('\n');
  return [
    { key: 'agents', test: 'req-agents', name: t('req.agents.name'), why: t('req.agents.why'),
      // Plugins can't read the preference: "not detected" is shown as missing (a warning) with the steps, never an error.
      status: asked(agents.status === 'ok' ? 'found' : 'missing'), label: agents.status === 'ok' ? t('req.agents.on') : t('req.agents.unknown'),
      detail: agents.status === 'ok' ? '' : t('req.agents.note'), install: lines('req.agents.step1', 'req.agents.step2', 'req.agents.step3', 'req.agents.step4'),
      url: AGENT_DOCS, urlLabel: t('req.agents.link'), check: checkRequirements },
    { key: 'ext', test: 'req-ext', name: t('req.ext.name'), why: t('req.ext.why'), status: asked(FOUND[ext.status]),
      label: ext.status === 'ok' ? t('req.found') : ext.status === 'missing' ? t('req.ext.missing') : t('req.unknown'),
      detail: ext.status === 'unknown' ? t('req.ext.unknown') : ext.details.version ? t('req.ext.version', { version: ext.details.version }) : '',
      install: lines('req.ext.step1', 'req.ext.step2', 'req.ext.step3', 'req.ext.step4'), url: EXT_URL, urlLabel: t('ext.link'), check: checkRequirements },
    { key: 'spoolman', test: 'req-spoolman', name: t('sm.title'), why: t('req.sm.why'), status: smState,
      label: smState === 'checking' ? t('req.checking') : smState === 'missing' ? (sm.status === 'missing' ? t('req.sm.missing') : t('req.missing'))
        : sm.status === 'ok' ? t('req.sm.set') : t('req.unknown'),
      detail: [smWhere, s.spoolsLoaded || s.spoolsError ? smInfo.value : ''].filter(Boolean).join(' · '),
      install: lines('req.sm.step1', 'req.sm.step2', 'req.sm.step3'), url: SPOOLMAN_URL, urlLabel: t('req.sm.link'),
      // Check again loads the spools again (the live answer), which also asks the plugin again; needs a printer that answers.
      disabled: !targetKnown.value || !!controlsOff.value, check: () => loadSpools(false) },
    { key: 'spooler', test: 'req-spooler', name: t('spooler.title'), why: t('req.spooler.why'), status: asked(FOUND[sp.status]),
      label: s.reqChecking ? t('req.checking') : sp.status === 'ok' ? t('req.found') : sp.status === 'missing' ? t('req.missing') : t('req.unknown'),
      detail: sp.status === 'ok' ? t('spooler.installed') : '', install: t('spooler.suggest'), url: sp.details.url, urlLabel: undefined, check: checkRequirements },
  ];
});
onMounted(() => loadRequirements());
const sections = computed<OuiSettingsSection[]>(() => [
  { id: 'mode', label: t('mode.title'), icon: zap },
  { id: 'print-setup', label: t('ps.title'), icon: printer, ...(pipe.value && !pipe.value.on ? { state: 'warn' as const } : {}) },
  { id: 'options', label: t('prefs.title'), icon: clipboard },
  { id: 'calibration', label: t('cal.title'), icon: target },
  { id: 'connection', label: t('conn.title'), icon: plug },
  { id: 'firmware', label: t('ext.title'), icon: wrench },
  { id: 'requirements', label: t('req.title'), icon: circleCheck },
  { id: 'language', label: t('lang.title'), icon: languages },
  { id: 'about', label: t('about.title'), icon: info },
]);
// A "Settings" link elsewhere (openSettings(page)) opens its page once Settings shows and the page is on it (some
// wait for the plugin's config).
const pages = ref<InstanceType<typeof SettingsPages>>();
watch(() => [s.settingsPage, s.tab, !!config.value], () => {
  const id = s.settingsPage;
  if (!id || s.tab !== 'settings' || !document.getElementById(id)) return;
  s.settingsPage = '';
  pages.value?.select(id);
}, { immediate: true, flush: 'post' });
// Enter in a text field saves, as the form's own button did.
function onEnter(e: KeyboardEvent) { if (e.target instanceof HTMLInputElement && e.target.type !== 'checkbox') { e.preventDefault(); void save(); } }
</script>


<template>
  <SettingsPages ref="pages" :sections="sections" :nav-label="t('settings.nav')" :back-label="t('settings.back')" :error-label="t('settings.hasError')">
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
          <OuiBanner :show="!!pipe && !pipe.on" role="note" tone="warn" :title="t('ps.off', { preset: pipe?.preset ?? '' })" data-test="ps-off"
                     dismissible :dismiss-key="`ps-off:${pipe?.preset ?? ''}`" :close-label="t('common.close')">
            {{ config.settings.auto_add_pipeline ? t('ps.offAuto') : t('ps.offManual') }}</OuiBanner>
          <p v-if="pipe?.on" data-test="ps-on">{{ t('ps.on', { preset: pipe.preset }) }}</p>
          <p v-if="dialogRule" data-test="ps-rule">{{ dialogRule }}</p>
          <p class="oui-meta">{{ t('ps.how') }}</p>
          <p class="oui-meta" data-test="ps-agent">{{ t('ps.agent') }}</p>
        </div>
      </OuiFormSection>

      <OuiFormSection id="options" :icon="clipboard" :title="t('prefs.title')" :aria-label="t('prefs.title')" :description="t('prefs.help')">
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
        <OuiFormRow :label="t('ofd.title')" for="ofd-on" :hint="t('ofd.help')">
          <ToggleSwitch input-id="ofd-on" :model-value="!!valueOf('ofd_enabled')" data-test="ofd-on" @update:model-value="setDraft('ofd_enabled', $event)" /></OuiFormRow>
        <div v-if="valueOf('ofd_enabled')" class="oui-row u1-ofd" data-test="ofd-state">
          <OuiStatus v-if="!ofdSaved" state="idle" variant="plain">{{ t('ofd.saveFirst') }}</OuiStatus>
          <OuiStatus v-else-if="ofdLine" :state="ofdState?.error || ofdState?.stale ? 'warn' : ofdState?.count ? 'ok' : 'idle'" variant="plain">{{ ofdLine }}</OuiStatus>
          <Button v-if="ofdSaved" severity="secondary" size="small" :label="t('ofd.refresh')" :loading="ofdBusy" data-test="ofd-refresh" @click="askOfd(true)" />
          <p class="oui-meta">{{ t('ofd.credit') }}</p>
        </div>
        <OuiFormRow :label="t('sm.refresh')" :hint="t('sm.refreshHelp')">
          <Select :model-value="s.refreshS" :options="REFRESH" option-label="label" option-value="value" :aria-label="t('sm.refresh')" data-test="sm-refresh"
                  @update:model-value="setRefresh($event as number)" />
        </OuiFormRow>
      </OuiFormSection>


      <FirmwareCard />

      <OuiFormSection id="requirements" :icon="circleCheck" tone="neutral" :title="t('req.title')" :aria-label="t('req.title')" :description="t('req.help')">
        <div role="status" class="u1-reqs" data-test="requirements">
          <OuiRequirement v-for="r in reqs" :key="r.key" :name="r.name" :why="r.why" :status="r.status" :status-label="r.label" :detail="r.detail || undefined"
                          :install-text="r.install" :install-url="r.url" :install-label="r.urlLabel" :check-label="t('req.check')" :disabled="r.disabled"
                          :data-test="r.test" @check="r.check()" />
        </div>
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
  </SettingsPages>
</template>
<style>
/* The install steps are one line each (per step, per OS). */
.u1-reqs .oui-req-install > span { flex-basis: 100%; white-space: pre-line; }
.u1-reqs .oui-req + .oui-req { border-top: 1px solid var(--oui-border); }
.u1-ofd { padding: 0 var(--oui-s4) var(--oui-s3); }
</style>
