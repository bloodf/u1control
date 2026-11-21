<script setup lang="ts">
// U1 Control — print setup: opened by the plugin after OrcaSlicer's Print (or by "U1 print setup" in the slicing
// pipeline), before anything is sent. The print at the top, one card per project filament with the toolhead it
// prints from, the print options, then "Apply & continue". The plugin checks the answer again (warnings, offered
// options, the exhaust fan); every option the printer's firmware lacks is simply not offered, so not shown.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Dialog from 'primevue/dialog';
import Popover from 'primevue/popover';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import Slider from 'primevue/slider';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiBanner, OuiIcon, OuiSpool, OuiStatus, OuiSwatch, OuiThumb } from '@orca-plugins/ui-foundation/src/components';
import { more, printer, refresh as refreshIcon, settings as settingsIcon, target, warning, wrench } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { boot } from '../core/boot';
import { t, tn, tMaybe } from '../core/i18n';
import { headColours, headFraction, present } from '../core/spool-level';
import { colourFar, family, setupWarnings, warningKey, type SetupFilament, type SetupHead } from '../core/logic';
import ConfirmDialog from '../components/ConfirmDialog.vue';
import HeadPicture from './HeadPicture.vue';
import HeadsSettings from './HeadsSettings.vue';
import PathPreview, { type PathData } from './PathPreview.vue';

type Pref = boolean | string | number | number[];
interface Spool { name: string; colour?: string | null; colours?: string[]; remaining?: number | null; initial?: number | null }
interface Data { job: { name?: string; time?: string; weight?: number | string; layers?: number | string; tool_changes?: number; address?: string;
    thumbnail?: string; preview?: PathData | null };
  filaments: SetupFilament[]; heads: SetupHead[]; map: Record<string, number>; prefs: Record<string, Pref>;
  labels: Record<string, string>; levels?: Record<string, string[]>; features?: string[]; purifier: string; auto_purifier: string;
  printer?: { name: string; busy: boolean; address: string } | null; spools?: Record<string, Spool | string>; remember?: boolean; tags?: boolean[] }
const D = boot.data as Data;
const heads = ref<SetupHead[]>(D.heads);
const spools = ref<Record<string, Spool | string>>(D.spools ?? {});
const tags = ref<boolean[]>(D.tags ?? []);
const map = reactive<Record<string, number>>({ ...D.map });
const touched = new Set<string>();
const prefs = reactive<Record<string, Pref>>({ ...D.prefs });
const purifier = ref(D.purifier);
const sent = ref(false);
const busy = ref(!!D.printer?.busy);
const remember = ref(D.remember !== false);
const has = (k: string) => k in D.prefs;

// ---------------------------------------------------------------- toolheads and spools
const spoolOf = (h: number): Spool | null => { const v = spools.value[String(h)]; return !v ? null : typeof v === 'string' ? { name: v } : v; };
/** The colour a head prints in: its Spoolman spool's colour first, the printer's own reading otherwise. */
const headColour = (h: number) => { const hd = heads.value[h]; return present(hd) ? spoolOf(h)?.colour || hd.colour || null : null; };
/** Every colour of a multi-colour spool in the head (its Spoolman spool's, else the printer's own), or null. */
const headMulti = (h: number) => (present(heads.value[h]) ? headColours(spoolOf(h), heads.value[h]) : null);
const headFill = (h: number) => headFraction(present(heads.value[h]), spoolOf(h));
/** What is in a head, in words: its filament, "unnamed" for filament nobody has named, '' when it is empty. */
const headName = (h: SetupHead | undefined) => (h?.loaded ? [h.type, h.sub_type].filter(Boolean).join(' ') : h?.unnamed ? t('setup.unnamed') : '');
const headOf = (f: SetupFilament) => heads.value[map[String(f.index)]];
const warnings = computed(() => setupWarnings(D.filaments, heads.value, map));
const warnFor = (f: SetupFilament) => warnings.value.find(w => w.f === f.index);
const colourHint = (f: SetupFilament) => { const h = headOf(f);
  return !!h && h.loaded && family(h.type) === family(f.type) && colourFar(f.colour, headColour(h.index)); };
const toolColours = computed(() => Object.fromEntries(D.filaments.map(f => [String(f.index), headColour(map[String(f.index)]) || f.colour || '#888'])));
// ---------------------------------------------------------------- warnings (same rule and ids as the plugin)
const ackFor = ref('');
const ackReset = ref(false);
const acked = computed({ get: () => !!warnings.value.length && ackFor.value === warningKey(warnings.value),
  set: v => { ackFor.value = v ? warningKey(warnings.value) : ''; ackReset.value = false; } });
watch(() => warningKey(warnings.value), now => { if (ackFor.value && ackFor.value !== now) { ackFor.value = ''; ackReset.value = true; } if (!now) ackReset.value = false; });
const warnText = (w: (typeof warnings.value)[number]) => (w.kind === 'material'
  ? t('setup.warn.material', { f: w.f + 1, a: w.a, n: w.h + 1, b: w.b }) : t(`setup.warn.${w.kind}`, { f: w.f + 1, n: w.h + 1 }));
const canSend = computed(() => !sent.value && !busy.value && (!warnings.value.length || acked.value));
const why = computed(() => sent.value ? '' : busy.value ? t('setup.busyShort') : !canSend.value ? t('setup.needAck') : '');

// ---------------------------------------------------------------- head picker (one popover, for the card that opened it)
const picker = ref<InstanceType<typeof Popover> | null>(null);
const picking = ref<SetupFilament | null>(null);
let opener: HTMLElement | null = null;
function openPicker(e: Event, f: SetupFilament) {
  picking.value = f;
  opener = e.currentTarget as HTMLElement;
  picker.value?.show(e, opener);
}
function onPickerShown() { (document.querySelector('.su-pick [aria-checked="true"]') as HTMLElement | null ?? document.querySelector('.su-pick button') as HTMLElement | null)?.focus(); }
function pick(h: number) {
  if (!picking.value) return;
  map[String(picking.value.index)] = h;
  touched.add(String(picking.value.index));
  picker.value?.hide();
  opener?.focus();
}

// ---------------------------------------------------------------- options
const flowPop = ref<InstanceType<typeof Popover> | null>(null);
const coverPop = ref<InstanceType<typeof Popover> | null>(null);
const prefsOpen = ref(false);
const DIALOG_PREFS = ['spaghetti_detect', 'bed_check', 'tangle_detect', 'auto_refill', 'refill_any_colour', 'unload_when_done', 'light_off_when_done'];
const LEVEL_OF: Record<string, string> = { spaghetti_detect: 'spaghetti_level', bed_check: 'bed_check_level', tangle_detect: 'tangle_level' };
const dialogPrefs = computed(() => DIALOG_PREFS.filter(has));
const prefLabel = (k: string) => k === 'tangle_detect' ? t('setup.airPrinting') : tMaybe(`pref.${k}`, D.labels[k] || k);
const levelOptions = (k: string) => (D.levels?.[k] ?? []).map(v => ({ value: v, label: tMaybe(`level.${v}`, v) }));
const flowHeads = computed({ get: () => (prefs.flow_calibrate_heads as number[] | undefined) ?? [],
  set: v => { prefs.flow_calibrate_heads = [...v].sort(); } });
function toggleFlowHead(i: number, on: boolean) { flowHeads.value = on ? [...new Set([...flowHeads.value, i])] : flowHeads.value.filter(x => x !== i); }

const purOptions = computed(() => ['auto', 'strong', 'weak', 'keep-warm', 'off'].map(v => ({ value: v, label: t(`purifier.${v}` as any) })));
const coverMode = computed(() => purifier.value === 'auto' ? D.auto_purifier : purifier.value);
const recirculating = computed(() => coverMode.value === 'keep-warm');
const FAN_AUTO = 60;   // u1.COVER_FAN_DEFAULT: Snapmaker's start G-code speed
// Auto / Off / a set speed per fan, kept as its own choice (a set speed of exactly 60 % stays "Set"): Auto sends
// Snapmaker's default speed, Off sends 0.
const startMode = (k: string) => prefs[k] === 0 ? 'off' : prefs[k] === FAN_AUTO ? 'auto' : 'set';
const exhaustMode = ref(startMode('exhaust_fan')), innerMode = ref(startMode('inner_fan'));
function followMode(k: string, mode: { value: string }) {
  watch(() => mode.value, v => { prefs[k] = v === 'off' ? 0 : v === 'auto' ? FAN_AUTO : (prefs[k] === 0 || prefs[k] === FAN_AUTO ? 50 : prefs[k]); });
}
followMode('exhaust_fan', exhaustMode);
followMode('inner_fan', innerMode);
const fanModes = computed(() => [{ value: 'auto', label: t('setup.fan.auto') }, { value: 'off', label: t('setup.fan.off') }, { value: 'set', label: t('setup.fan.set') }]);
const showExhaust = computed(() => has('exhaust_fan') && ['strong', 'weak', 'keep-warm'].includes(coverMode.value));
const showInner = computed(() => has('inner_fan') && recirculating.value);

// ---------------------------------------------------------------- job facts
const meta1 = computed(() => [D.job.time, D.job.weight !== '' && D.job.weight != null ? t('setup.grams', { g: D.job.weight }) : ''].filter(Boolean).join(' · '));
const meta2 = computed(() => [D.job.layers ? tn('setup.layers', Number(D.job.layers)) : '', D.job.tool_changes != null ? tn('setup.toolChanges', D.job.tool_changes) : '']
  .filter(Boolean).join(' · '));

// ---------------------------------------------------------------- refresh, auto mapping, send
const editing = ref(false);
let autoNext = false;
const refresh = () => bridge.post({ refresh: true });
function autoMap() { autoNext = true; refresh(); }
function send() {
  if (!canSend.value) return;
  sent.value = true;
  const out: Record<string, Pref> = { ...prefs };
  if (recirculating.value) delete out.exhaust_fan;   // the plugin drops it too (u1.exhaust_blocked)
  bridge.submit({ map: { ...map }, prefs: out, purifier: purifier.value, acknowledged: warnings.value.map(w => w.id), remember: remember.value });
}
const cancel = () => { if (!sent.value) bridge.submit({ cancelled: true }); };
const openSettings = () => bridge.post({ open_settings: true });

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && !document.querySelector('.p-select-overlay, .p-popover, .p-dialog, .p-dialog-mask')) cancel();
}
let timer = 0;
onMounted(() => {
  bridge.attach();
  bridge.onMessage(m => {   // live toolheads: a spool changed on the touchscreen or in Heads settings shows up here
    if (!m || !Array.isArray(m.heads)) return;
    heads.value = m.heads;
    if (typeof m.busy === 'boolean') busy.value = m.busy;
    if (m.spools && typeof m.spools === 'object') spools.value = m.spools;
    if (Array.isArray(m.tags)) tags.value = m.tags;
    for (const [f, h] of Object.entries(m.map || {})) if (autoNext || !touched.has(f)) map[f] = h as number;
    if (autoNext) { touched.clear(); autoNext = false; }
  });
  document.addEventListener('keydown', onKey, true);
  bridge.post({ ready: true });
  timer = window.setInterval(refresh, 3000);
});
onBeforeUnmount(() => { clearInterval(timer); document.removeEventListener('keydown', onKey, true); });
</script>

<template>
  <main class="oui-page su">
    <header class="su-head">
      <OuiThumb :src="D.job.thumbnail ? 'data:image/png;base64,' + D.job.thumbnail : null" :alt="t('setup.thumb')" :size="76" :icon="printer" />
      <div class="su-job">
        <h1 class="su-job-name">{{ D.job.name || t('setup.title') }}</h1>
        <p class="su-meta oui-num" data-test="job-meta">{{ meta1 }}</p>
        <p class="oui-meta oui-num" data-test="job-meta2">{{ meta2 }}</p>
      </div>
      <div v-if="D.printer" class="su-printer" data-test="printer">
        <p class="su-printer-name">{{ D.printer.name }}</p>
        <p class="oui-meta oui-num su-printer-line">{{ D.printer.address }}
          <OuiStatus :state="busy ? 'busy' : 'ok'" variant="plain" role="status">{{ busy ? t('bar.busy') : t('setup.ready') }}</OuiStatus></p>
        <Button v-if="dialogPrefs.length" size="small" severity="secondary" :label="t('setup.prefsButton')" data-test="prefs" :disabled="busy || sent" @click="prefsOpen = true">
          <template #icon><OuiIcon :icon="settingsIcon" :size="14" /></template></Button>
      </div>
    </header>

    <OuiBanner v-if="busy" tone="warn" :title="t('setup.busyTitle')" data-test="busy">{{ t('setup.busyText') }}</OuiBanner>

    <section class="su-map" aria-labelledby="su-map-h">
      <h2 id="su-map-h" class="su-section">{{ t('setup.mappingTitle') }}</h2>
      <div class="su-body">
        <ul class="su-cards" role="list">
          <li v-for="f in D.filaments" :key="f.index">
            <button type="button" class="su-card" :data-f="f.index" :data-t="map[String(f.index)]" :disabled="busy || sent" aria-haspopup="dialog"
                    :aria-label="t('setup.cardLabel', { f: f.index + 1, type: f.type, n: map[String(f.index)] + 1,
                                   loaded: headOf(f)?.loaded ? headOf(f)!.type : headName(headOf(f)) || t('setup.empty') }) + (warnFor(f) ? '. ' + warnText(warnFor(f)!) : '')"
                    @click="openPicker($event, f)">
              <!-- The project filament's colour is a 4 px strip, as on every slot card; the card itself is neutral. -->
              <span class="oui-slot-strip su-card-strip" :data-unknown="!f.colour || undefined" :style="f.colour ? { background: f.colour } : undefined" aria-hidden="true" />
              <span class="su-card-top">
                <span class="oui-num">[{{ f.index + 1 }}]</span> <strong>{{ f.type }}</strong>
                <span v-if="f.weight" class="su-card-g oui-num">{{ t('setup.grams', { g: f.weight }) }}</span></span>
              <HeadPicture :n="map[String(f.index)] + 1" :strand="headColour(map[String(f.index)])" />
              <span class="su-card-foot">
                <OuiSpool :color="headColour(map[String(f.index)])" :colors="headMulti(map[String(f.index)])" :fraction="headFill(map[String(f.index)])" :size="32" />
                <span class="su-card-id"><span class="oui-strong">{{ t('setup.head', { n: map[String(f.index)] + 1 }) }}
                  <OuiIcon v-if="warnFor(f)" :icon="warning" :size="14" class="su-warn-ico" data-test="card-warn" /></span>
                  <span class="oui-meta"><em v-if="!present(headOf(f))" class="su-empty">{{ t('setup.empty') }}</em>
                    <template v-else>{{ headName(headOf(f)) }}</template></span>
                  <span v-if="spoolOf(map[String(f.index)])" class="oui-meta su-spool" data-test="spool">{{ spoolOf(map[String(f.index)])!.name }}</span></span>
              </span>
              <span v-if="colourHint(f)" class="su-hint" data-test="colour-hint">{{ t('setup.colourDiffers', { f: f.index + 1, n: map[String(f.index)] + 1 }) }}</span>
            </button>
          </li>
        </ul>
        <PathPreview v-if="D.job.preview" :paths="D.job.preview" :colours="toolColours" :label="t('setup.preview')" data-test="preview" />
      </div>
      <div class="su-tools">
        <Button size="small" severity="secondary" :label="t('setup.refresh')" data-test="refresh" :disabled="sent" @click="refresh"><template #icon><OuiIcon :icon="refreshIcon" :size="14" /></template></Button>
        <Button size="small" severity="secondary" :label="t('setup.autoMap')" data-test="automap" :disabled="busy || sent" @click="autoMap"><template #icon><OuiIcon :icon="target" :size="14" /></template></Button>
        <Button size="small" severity="secondary" :label="t('setup.headsSettings')" data-test="heads" :aria-expanded="editing" aria-controls="su-heads-edit"
                :disabled="sent" @click="editing = !editing"><template #icon><OuiIcon :icon="wrench" :size="14" /></template></Button>
      </div>
      <div id="su-heads-edit"><HeadsSettings v-if="editing" :heads="heads" :tags="tags" :disabled="busy || sent" /></div>
    </section>

    <section v-if="warnings.length" class="oui-stack su-warn" aria-labelledby="su-w">
      <h2 id="su-w" class="oui-sr">{{ t('setup.warnings') }}</h2>
      <div role="alert" class="u1-live"><OuiBanner v-for="w in warnings" :key="w.id" role="none" tone="warn" :title="warnText(w)" /></div>
      <p v-if="ackReset" class="u1-note" data-tone="warn" role="status">{{ t('setup.ackReset') }}</p>
      <label class="su-check" for="su-ack"><Checkbox v-model="acked" input-id="su-ack" binary data-test="ack" />{{ t('setup.ack') }}</label>
    </section>

    <section class="su-opts" :aria-label="t('setup.options')">
      <label v-if="has('bed_level')" class="su-check" for="su-p-bed_level"><Checkbox v-model="prefs.bed_level" input-id="su-p-bed_level" binary :disabled="busy || sent" />{{ prefLabel('bed_level') }}</label>
      <span v-if="has('flow_calibrate')" class="su-check">
        <label class="su-check" for="su-p-flow_calibrate"><Checkbox v-model="prefs.flow_calibrate" input-id="su-p-flow_calibrate" binary :disabled="busy || sent" />{{ t('setup.flow') }}</label>
        <Button v-if="has('flow_calibrate_heads')" size="small" text severity="secondary" :aria-label="t('setup.flowMore')" :title="t('setup.flowMore')" data-test="flow-more"
                :disabled="busy || sent || !prefs.flow_calibrate" aria-haspopup="dialog" @click="flowPop?.toggle($event)"><template #icon><OuiIcon :icon="more" :size="14" /></template></Button>
      </span>
      <label v-if="has('time_lapse_camera')" class="su-check" for="su-p-time_lapse_camera"><Checkbox v-model="prefs.time_lapse_camera" input-id="su-p-time_lapse_camera" binary :disabled="busy || sent" />{{ prefLabel('time_lapse_camera') }}</label>
      <span class="oui-spacer" />
      <span class="su-check">{{ t('setup.cover') }} <span class="oui-meta">{{ t(`purifier.${purifier}` as any) }}</span>
        <Button size="small" text severity="secondary" :aria-label="t('setup.coverMore')" :title="t('setup.coverMore')" data-test="cover-more" :disabled="busy || sent"
                aria-haspopup="dialog" @click="coverPop?.toggle($event)"><template #icon><OuiIcon :icon="more" :size="14" /></template></Button></span>
    </section>

    <div class="su-send">
      <label class="su-check su-remember" for="su-remember"><Checkbox v-model="remember" input-id="su-remember" binary data-test="remember" aria-describedby="su-remember-hint" />
        <span>{{ t('setup.remember') }} <span id="su-remember-hint" class="oui-meta su-remember-hint">{{ t('setup.rememberHint') }}</span></span></label>
      <p v-if="why" id="su-why" class="u1-note" data-tone="warn">{{ why }}</p>
      <OuiStatus v-if="sent" state="busy" role="status">{{ t('setup.sending') }}</OuiStatus>
      <div class="su-actions">
        <Button severity="secondary" :label="t('setup.dontSend')" data-test="cancel" :disabled="sent" @click="cancel" />
        <Button size="large" class="su-apply" :severity="warnings.length ? 'warn' : undefined" :disabled="!canSend" :aria-describedby="why ? 'su-why' : undefined" data-test="send"
                :label="warnings.length ? tn('setup.sendWarn', warnings.length) : t('setup.apply')" @click="send" />
      </div>
      <Button text size="small" severity="secondary" :label="t('setup.pluginSettings')" data-test="plugin-settings" aria-describedby="su-ps-hint" @click="openSettings">
        <template #icon><OuiIcon :icon="settingsIcon" :size="14" /></template></Button>
      <p id="su-ps-hint" class="oui-meta">{{ t('setup.pluginSettingsHint') }}</p>
    </div>
  </main>

  <Popover ref="picker" @show="onPickerShown">
    <div v-if="picking" class="su-pick" role="radiogroup" :aria-label="t('setup.pickHead', { n: picking.index + 1 })">
      <p class="oui-strong">{{ t('setup.pickHead', { n: picking.index + 1 }) }}</p>
      <button v-for="h in heads" :key="h.index" type="button" role="radio" class="su-pick-head" :aria-checked="map[String(picking.index)] === h.index"
              :data-pick="h.index" @click="pick(h.index)">
        <span class="oui-slot-badge oui-num" :data-tool="h.index + 1">T{{ h.index + 1 }}</span>
        <!-- A colour chip, not the spool: picking a head is matching colours, and a head without a Spoolman spool would draw a colourless bare reel. -->
        <OuiSwatch :color="headColour(h.index)" :colors="headMulti(h.index)" :size="16" />
        <span class="su-pick-text"><span class="oui-strong"><em v-if="!present(h)" class="su-empty">{{ t('setup.empty') }}</em><template v-else>{{ headName(h) }}</template></span>
          <span v-if="spoolOf(h.index)" class="oui-meta">{{ spoolOf(h.index)!.name }}</span></span>
        <OuiIcon v-if="h.loaded && family(h.type) !== family(picking.type)" :icon="warning" :size="14" class="su-warn-ico" :title="t('setup.otherMaterial')" />
      </button>
    </div>
  </Popover>

  <Popover ref="flowPop">
    <fieldset class="su-pop">
      <legend class="oui-strong">{{ prefLabel('flow_calibrate_heads') }}</legend>
      <label v-for="h in heads" :key="h.index" class="su-check" :for="`su-fh-${h.index}`">
        <Checkbox :model-value="flowHeads.includes(h.index)" :input-id="`su-fh-${h.index}`" binary @update:model-value="v => toggleFlowHead(h.index, v)" />T{{ h.index + 1 }}</label>
      <p v-if="!flowHeads.length" class="oui-meta">{{ t('setup.flowNone') }}</p>
    </fieldset>
  </Popover>

  <Popover ref="coverPop">
    <div class="su-pop" data-test="cover-pop">
      <label class="oui-strong" for="su-cover">{{ t('setup.coverMode') }}</label>
      <Select v-model="purifier" input-id="su-cover" :options="purOptions" option-label="label" option-value="value" />
      <p class="oui-meta">{{ t('setup.autoPicks', { mode: t(`purifier.${D.auto_purifier}` as any) }) }}</p>
      <template v-if="showExhaust">
        <p id="su-fan-ex" class="oui-strong">{{ prefLabel('exhaust_fan') }}</p>
        <template v-if="recirculating"><p class="u1-note" data-tone="warn" data-test="exhaust-blocked">{{ t('fan.exhaustBlocked') }}</p></template>
        <template v-else>
          <SelectButton v-model="exhaustMode" :options="fanModes" option-label="label" option-value="value" :allow-empty="false" aria-labelledby="su-fan-ex" data-test="exhaust-mode" />
          <span v-if="exhaustMode === 'set'" class="su-slider"><Slider v-model="prefs.exhaust_fan as number" :min="1" :max="100" aria-labelledby="su-fan-ex" class="su-slider-bar" />
            <span class="oui-num">{{ prefs.exhaust_fan }} %</span></span>
        </template>
      </template>
      <template v-if="showInner">
        <p id="su-fan-in" class="oui-strong">{{ prefLabel('inner_fan') }}</p>
        <SelectButton v-model="innerMode" :options="fanModes" option-label="label" option-value="value" :allow-empty="false" aria-labelledby="su-fan-in" data-test="inner-mode" />
        <span v-if="innerMode === 'set'" class="su-slider"><Slider v-model="prefs.inner_fan as number" :min="1" :max="100" aria-labelledby="su-fan-in" class="su-slider-bar" />
          <span class="oui-num">{{ prefs.inner_fan }} %</span></span>
      </template>
      <p v-if="showExhaust || showInner" class="oui-meta">{{ t('setup.fanAutoHint', { n: FAN_AUTO }) }}</p>
    </div>
  </Popover>

  <Dialog v-model:visible="prefsOpen" modal :header="t('setup.prefsButton')" class="su-dialog" :draggable="false">
    <div class="su-prefs" data-test="prefs-dialog">
      <div v-for="k in dialogPrefs" :key="k" class="su-pref" :data-pref="k">
        <label class="su-pref-label" :for="`su-d-${k}`">{{ prefLabel(k) }}</label>
        <ToggleSwitch v-model="prefs[k] as boolean" :input-id="`su-d-${k}`" />
        <SelectButton v-if="LEVEL_OF[k] && has(LEVEL_OF[k])" v-model="prefs[LEVEL_OF[k]]" :options="levelOptions(LEVEL_OF[k])" option-label="label" option-value="value"
                      :allow-empty="false" :disabled="!prefs[k]" :aria-label="t('setup.sensitivity', { name: prefLabel(k) })" class="su-level" :data-level="LEVEL_OF[k]" />
      </div>
    </div>
    <template #footer><Button :label="t('common.close')" @click="prefsOpen = false" /></template>
  </Dialog>
  <ConfirmDialog />
</template>

<style>
.su { max-width: 980px; margin: 0 auto; gap: var(--oui-s4); }
.su-head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: var(--oui-s4); align-items: center; }
.su-job { display: grid; gap: 2px; min-width: 0; }
.su-job-name { font-size: var(--oui-text-xl); line-height: 1.2; font-weight: 700; overflow-wrap: anywhere; }
.su-meta { font-size: var(--oui-text-md, 1rem); }
.su-printer { display: grid; justify-items: end; gap: 4px; text-align: end; }
.su-printer-name { font-weight: 700; font-size: var(--oui-text-lg); }
.su-printer-line { display: inline-flex; align-items: center; gap: var(--oui-s2); }
.su-section { font-size: var(--oui-text-sm); font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--oui-muted); text-align: center; margin-bottom: var(--oui-s3); }
.su-body { display: flex; gap: var(--oui-s4); align-items: flex-start; }
.su-cards { list-style: none; margin: 0; padding: 0; flex: 1; display: grid; gap: var(--oui-s3); grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }
.su-cards > li { display: grid; }
.su-card { all: unset; box-sizing: border-box; display: grid; justify-items: center; align-content: start; gap: var(--oui-s2); width: 100%; height: 100%; padding: var(--oui-s2) var(--oui-s2) var(--oui-s3); cursor: pointer;
  border-radius: var(--oui-radius-lg); background: var(--oui-surface); box-shadow: inset 0 0 0 1px var(--oui-border), var(--oui-shadow-panel); }
.su-card:hover:not(:disabled) { box-shadow: inset 0 0 0 2px var(--oui-primary-mark), var(--oui-shadow-panel); }
.su-card:focus-visible { outline: 2px solid var(--oui-primary-mark); outline-offset: 2px; }
.su-card:disabled { cursor: default; opacity: .75; }
.su-card-strip { justify-self: stretch; margin: 0; }
.su-card-top { display: flex; align-items: baseline; gap: 6px; width: 100%; box-sizing: border-box; padding: 0 var(--oui-s2); font-size: var(--oui-text-lg); }
.su-card-g { color: var(--oui-muted); }
.su-card-g { margin-inline-start: auto; font-size: var(--oui-text-sm); }
.su-card-foot { display: flex; align-items: center; gap: var(--oui-s2); width: 100%; padding-inline: var(--oui-s2); box-sizing: border-box; }
.su-card-id { display: grid; min-width: 0; }
.su-card-id > * { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.su-warn-ico { color: var(--oui-warning); vertical-align: -2px; }
.su-empty { font-style: normal; text-decoration: underline dotted; }
.su-hint { font-size: var(--oui-text-sm); color: var(--oui-muted); text-align: center; padding-inline: var(--oui-s2); }
.su-tools { display: flex; flex-wrap: wrap; justify-content: center; gap: var(--oui-s2); margin-top: var(--oui-s3); }
#su-heads-edit:not(:empty) { margin-top: var(--oui-s3); }
.su-opts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--oui-s2) var(--oui-s4); padding-top: var(--oui-s3); border-top: 1px solid var(--oui-border); }
.su-check { display: inline-flex; align-items: center; gap: var(--oui-s2); }
.su-send { display: grid; justify-items: center; gap: var(--oui-s2); }
.su-remember { justify-self: start; font-weight: 600; }
.su-remember-hint { display: block; font-weight: 400; }
.su-actions { display: flex; flex-wrap: wrap; gap: var(--oui-s2); justify-content: center; }
.su-apply.p-button { min-width: 14rem; }
.su-pick { display: grid; gap: 4px; min-width: 15rem; }
.su-pick-head { all: unset; box-sizing: border-box; display: flex; align-items: center; gap: var(--oui-s2); padding: 6px 8px; border-radius: var(--oui-radius); cursor: pointer; }
.su-pick-head:hover, .su-pick-head[aria-checked="true"] { background: var(--oui-primary-soft); }
.su-pick-head:focus-visible { outline: 2px solid var(--oui-primary-mark); }
.su-pick-text { display: grid; flex: 1; min-width: 0; }
.su-pop { display: grid; gap: var(--oui-s2); min-width: 15rem; border: 0; margin: 0; padding: 0; }
.su-slider { display: flex; align-items: center; gap: var(--oui-s3); }
.su-slider-bar { flex: 1; }
.su-prefs { display: grid; gap: var(--oui-s2); min-width: min(28rem, 80vw); }
.su-pref { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--oui-s2); align-items: center; padding-block: var(--oui-s2); border-bottom: 1px solid var(--oui-border); }
.su-level { grid-column: 1 / -1; }
@container oui-page (max-width: 640px) {
  .su-head { grid-template-columns: auto minmax(0, 1fr); }
  .su-printer { grid-column: 1 / -1; justify-items: start; text-align: start; }
  .su-body { flex-direction: column; align-items: stretch; }
  .su-body > .pp { align-self: center; }
  .su-cards { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
}
</style>
