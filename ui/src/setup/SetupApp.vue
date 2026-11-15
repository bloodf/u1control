<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Select from 'primevue/select';
import ToggleSwitch from 'primevue/toggleswitch';
import { OuiAppBar, OuiBanner, OuiFormRow, OuiIcon, OuiPanel, OuiStatus, OuiSwatch, OuiThumb } from '../../shared/src/components';
import { clipboard, printer, toolhead, upload, wind } from '../../shared/src/icons';
import * as bridge from '../core/bridge';
import { boot } from '../core/boot';
import { t, tn, tMaybe } from '../core/i18n';
import { setupWarnings, warningKey, type SetupFilament, type SetupHead } from '../core/logic';

interface Data { job: { name?: string; time?: string; weight?: number; plate?: string | number; address?: string; thumbnail?: string };
  filaments: SetupFilament[]; heads: SetupHead[]; map: Record<string, number>; prefs: Record<string, boolean>;
  labels: Record<string, string>; purifier: string; auto_purifier: string }
const D = boot.data as Data;
const heads = ref<SetupHead[]>(D.heads);
const map = reactive<Record<string, number>>({ ...D.map });
const touched = new Set<string>();
const prefs = reactive<Record<string, boolean>>({ ...D.prefs });
const purifier = ref(D.purifier);
const sent = ref(false);

const warnings = computed(() => setupWarnings(D.filaments, heads.value, map));
// The acknowledgement belongs to one exact set of warnings: a new mapping or a live toolhead change clears it (U04).
const ackFor = ref('');
const ackReset = ref(false);
const acked = computed({ get: () => !!warnings.value.length && ackFor.value === warningKey(warnings.value),
  set: v => { ackFor.value = v ? warningKey(warnings.value) : ''; ackReset.value = false; } });
watch(() => warningKey(warnings.value), (now, before) => { if (ackFor.value && ackFor.value !== now) { ackFor.value = ''; ackReset.value = true; } if (!now) ackReset.value = false; void before; });
const canSend = computed(() => !sent.value && (!warnings.value.length || acked.value));
const warnText = (w: (typeof warnings.value)[number]) => w.kind === 'empty'
  ? t('setup.warn.empty', { f: w.f + 1, n: w.h + 1 }) : t('setup.warn.material', { f: w.f + 1, a: w.a, n: w.h + 1, b: w.b });

function pick(f: number, h: number) { map[String(f)] = h; touched.add(String(f)); }
function send() {
  if (!canSend.value) return;
  sent.value = true;
  bridge.submit({ map: { ...map }, prefs: { ...prefs }, purifier: purifier.value, acknowledged: warnings.value.map(w => w.id) });
}
const cancel = () => bridge.submit({ cancelled: true });
const purOptions = computed(() => ['auto', 'strong', 'weak', 'keep-warm', 'off'].map(v => ({ value: v, label: t(`purifier.${v}` as any) })));
const meta = computed(() => [D.job.time, D.job.weight && t('setup.grams', { g: D.job.weight }), D.job.plate, D.job.address && t('setup.to', { address: D.job.address })].filter(Boolean).join(' · '));
const prefLabel = (k: string) => tMaybe(`pref.${k}`, D.labels[k] || k);

function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && !e.defaultPrevented && !document.querySelector('.p-select-overlay')) cancel(); }
let timer = 0;
const footer = ref<HTMLElement | null>(null);
let footerObserver: ResizeObserver | undefined;
const updateFooterSpace = () => {
  document.documentElement.style.setProperty('--u1-setup-footer-height', `${footer.value?.getBoundingClientRect().height ?? 0}px`);
};
onMounted(() => {
  updateFooterSpace();
  footerObserver = new ResizeObserver(updateFooterSpace);
  if (footer.value) footerObserver.observe(footer.value);
  bridge.attach();
  bridge.onMessage(m => {   // live toolhead refresh: a spool changed on the touchscreen shows up here; keyed rows keep focus
    if (!m || !Array.isArray(m.heads)) return;
    heads.value = m.heads;
    for (const [f, h] of Object.entries(m.map || {})) if (!touched.has(f)) map[f] = h as number;
  });
  document.addEventListener('keydown', onKey);
  bridge.post({ ready: true });
  timer = window.setInterval(() => bridge.post({ refresh: true }), 3000);
});
onBeforeUnmount(() => {
  clearInterval(timer); document.removeEventListener('keydown', onKey);
  footerObserver?.disconnect(); document.documentElement.style.removeProperty('--u1-setup-footer-height');
});
</script>

<template>
  <OuiAppBar :name="t('setup.title')">
    <template #mark>
      <svg viewBox="0 0 256 256" fill="currentColor"><path d="M40 96H72V160A32 32 0 0 0 104 192H152A32 32 0 0 0 184 160V96H216V160A64 64 0 0 1 152 224H104A64 64 0 0 1 40 160Z" /><rect x="40" y="40" width="32" height="64" rx="8" /><rect x="88" y="40" width="32" height="64" rx="8" /><rect x="136" y="40" width="32" height="64" rx="8" /><rect x="184" y="40" width="32" height="64" rx="8" /></svg>
    </template>
  </OuiAppBar>
  <main class="oui-page su">
    <!-- The page's hero: the print that is about to be sent. -->
    <header class="oui-hero oui-on-band su-job">
      <OuiThumb :src="D.job.thumbnail ? 'data:image/png;base64,' + D.job.thumbnail : null" :alt="t('setup.thumb')" :size="72" :icon="printer" />
      <div class="su-job-id"><h1 class="su-job-name">{{ D.job.name || t('setup.title') }}</h1><p class="su-job-meta oui-num">{{ meta }}</p></div>
    </header>

    <OuiPanel :icon="toolhead" tone="magenta" flush aria-labelledby="su-map">
      <template #title><span id="su-map">{{ t('setup.mapping') }}</span></template>
      <template #meta>{{ t('setup.live') }}</template>
      <div class="su-rows">
        <div v-for="f in D.filaments" :key="f.index" class="su-row" role="group" :aria-labelledby="`su-f-${f.index}`">
          <span :id="`su-f-${f.index}`" class="su-fil"><OuiSwatch :color="f.colour" :size="16" />
            <span class="oui-strong">{{ t('setup.filament', { n: f.index + 1, type: f.type }) }}</span><span v-if="f.weight" class="oui-muted oui-num">{{ t('setup.grams', { g: f.weight }) }}</span></span>
          <div class="su-heads">
            <Button v-for="h in heads" :key="h.index" :severity="map[f.index] === h.index ? undefined : 'secondary'"
                    :aria-pressed="map[f.index] === h.index" :data-f="f.index" :data-t="h.index" class="su-head"
                    :aria-label="t('setup.headBtn', { f: f.index + 1, n: h.index + 1, type: h.loaded ? h.type : t('setup.empty') })"
                    :title="[h.vendor, h.sub_type].filter(Boolean).join(' ')" @click="pick(f.index, h.index)">
              <span class="u1-tool" :data-tool="h.index + 1">T{{ h.index + 1 }}</span><OuiSwatch :color="h.loaded ? h.colour : null" :size="14" />
              <span class="oui-strong"><em v-if="!h.loaded" class="su-empty">{{ t('setup.empty') }}</em><template v-else>{{ h.type }}</template></span>
            </Button>
          </div>
        </div>
      </div>
    </OuiPanel>

    <section v-if="warnings.length" class="oui-stack su-warn" aria-labelledby="su-w">
      <h2 id="su-w" class="oui-sr">{{ t('setup.warnings') }}</h2>
      <div role="alert" class="u1-live"><OuiBanner v-for="w in warnings" :key="w.id" tone="warn" :title="warnText(w)" /></div>
      <p v-if="ackReset" class="u1-note" data-tone="warn" role="status">{{ t('setup.ackReset') }}</p>
      <label class="su-ack" for="su-ack"><Checkbox v-model="acked" input-id="su-ack" binary data-test="ack" />{{ t('setup.ack') }}</label>
    </section>

    <OuiPanel :icon="clipboard" tone="cobalt" flush aria-labelledby="su-o">
      <template #title><span id="su-o">{{ t('setup.options') }}</span></template>
      <div class="su-rows">
        <OuiFormRow v-for="(v, k) in prefs" :key="k" :label="prefLabel(String(k))" :for="`su-p-${k}`"><ToggleSwitch v-model="prefs[k]" :input-id="`su-p-${k}`" /></OuiFormRow>
        <OuiFormRow :label="t('setup.coverMode')" :hint="t('setup.autoPicks', { mode: t(`purifier.${D.auto_purifier}` as any) })">
          <Select v-model="purifier" :options="purOptions" option-label="label" option-value="value" :aria-label="t('setup.coverMode')" />
        </OuiFormRow>
      </div>
    </OuiPanel>
  </main>
  <footer ref="footer" class="su-bar">
    <div class="su-bar-in">
      <span v-if="!canSend && !sent" id="su-why" class="u1-note" data-tone="warn">{{ t('setup.needAck') }}</span>
      <OuiStatus v-if="sent" state="busy" role="status">{{ t('setup.sending') }}</OuiStatus>
      <span class="oui-spacer" />
      <Button severity="secondary" :label="t('setup.dontSend')" data-test="cancel" @click="cancel" />
      <Button :severity="warnings.length ? 'warn' : undefined" :disabled="!canSend" aria-describedby="su-why" data-test="send"
              :label="warnings.length ? tn('setup.sendWarn', warnings.length) : t('setup.send')" @click="send"><template #icon><OuiIcon :icon="upload" :size="14" /></template></Button>
    </div>
  </footer>
</template>

<style>
html { scroll-padding-bottom: calc(var(--u1-setup-footer-height, 0px) + 16px); }
.su { max-width: 900px; margin: 0 auto; }
.su-job { display: flex; grid-template-columns: none; align-items: center; gap: var(--oui-s4); }
.su-job-id { display: grid; gap: 2px; min-width: 0; }
.su-job-name { font-size: var(--oui-text-xl); line-height: 1.2; font-weight: 700; overflow-wrap: anywhere; }
.su-job-meta { font-size: var(--oui-text-sm); }
.su-rows > * + * { border-top: 1px solid var(--oui-border); }
.su-row { display: grid; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr); gap: var(--oui-s2) var(--oui-s4); align-items: center; padding: var(--oui-s2) var(--oui-s4); }
.su-fil { display: inline-flex; flex-wrap: wrap; gap: 6px; align-items: center; overflow-wrap: anywhere; }
.su-heads { display: flex; flex-wrap: wrap; gap: 6px; }
.su-head.p-button { gap: 6px; padding-inline: 8px 12px; }
.su-empty { font-style: normal; text-decoration: underline dotted; }
.su-ack { display: inline-flex; align-items: center; gap: var(--oui-s2); font-weight: 600; }
.su-bar { position: sticky; bottom: 0; z-index: 5; background: var(--oui-surface); border-top: 1px solid var(--oui-border); box-shadow: 0 -6px 16px rgb(0 0 0 / .12); }
.su-bar-in { display: flex; flex-wrap: wrap; gap: var(--oui-s2); align-items: center; max-width: 900px; margin: 0 auto; padding: var(--oui-s2) var(--oui-s4); }
@container oui-page (max-width: 560px) { .su-row { grid-template-columns: minmax(0, 1fr); } }
</style>
