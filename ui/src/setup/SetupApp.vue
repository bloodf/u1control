<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Select from 'primevue/select';
import Message from 'primevue/message';
import Icon from '../components/Icon.vue';
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
  <div class="su">
    <header class="su-job">
      <img v-if="D.job.thumbnail" :src="'data:image/png;base64,' + D.job.thumbnail" :alt="t('setup.thumb')" class="su-thumb">
      <div><p class="oui-meta su-kicker">{{ t('setup.title') }}</p><h1>{{ D.job.name || t('setup.title') }}</h1><p class="oui-meta">{{ meta }}</p></div>
    </header>
    <section aria-labelledby="su-map">
      <h2 id="su-map">{{ t('setup.mapping') }}</h2>
      <p class="oui-meta">{{ t('setup.live') }}</p>
      <div v-for="f in D.filaments" :key="f.index" class="su-row" role="group" :aria-labelledby="`su-f-${f.index}`">
        <span :id="`su-f-${f.index}`" class="su-fil"><span class="u1-sw" :style="{ background: f.colour || '#ccc' }" />
          {{ t('setup.filament', { n: f.index + 1, type: f.type }) }}<span v-if="f.weight" class="oui-muted"> · {{ t('setup.grams', { g: f.weight }) }}</span></span>
        <div class="su-heads">
          <Button v-for="h in heads" :key="h.index" :severity="map[f.index] === h.index ? undefined : 'secondary'" :outlined="map[f.index] !== h.index"
                  :aria-pressed="map[f.index] === h.index" :data-f="f.index" :data-t="h.index" class="su-head"
                  :aria-label="t('setup.headBtn', { f: f.index + 1, n: h.index + 1, type: h.loaded ? h.type : t('setup.empty') })"
                  :title="[h.vendor, h.sub_type].filter(Boolean).join(' ')" @click="pick(f.index, h.index)">
            <Icon :name="`toolhead/t${h.index + 1}`" :size="20" /><span class="u1-sw" :style="{ background: h.colour || 'transparent' }" />
            <span>T{{ h.index + 1 }} <em v-if="!h.loaded" class="su-empty">{{ t('setup.empty') }}</em><template v-else>{{ h.type }}</template></span>
          </Button>
        </div>
      </div>
    </section>
    <section v-if="warnings.length" aria-labelledby="su-w" class="su-warn">
      <h2 id="su-w" class="u1-warn"><Icon name="icon/warning" /> {{ t('setup.warnings') }}</h2>
      <div role="alert"><Message v-for="w in warnings" :key="w.id" severity="warn">{{ warnText(w) }}</Message></div>
      <p v-if="ackReset" class="u1-warn" role="status">{{ t('setup.ackReset') }}</p>
      <span class="u1-row"><Checkbox v-model="acked" input-id="su-ack" binary data-test="ack" /><label for="su-ack">{{ t('setup.ack') }}</label></span>
    </section>
    <section aria-labelledby="su-o">
      <h2 id="su-o">{{ t('setup.options') }}</h2>
      <div class="su-opts">
        <span v-for="(v, k) in prefs" :key="k" class="u1-row"><Checkbox v-model="prefs[k]" :input-id="`su-p-${k}`" binary /><label :for="`su-p-${k}`">{{ prefLabel(String(k)) }}</label></span>
      </div>
    </section>
    <section aria-labelledby="su-c">
      <h2 id="su-c">{{ t('setup.cover') }}</h2>
      <div class="u1-row"><label id="su-pur-l">{{ t('setup.coverMode') }}</label>
        <Select v-model="purifier" :options="purOptions" option-label="label" option-value="value" aria-labelledby="su-pur-l" />
        <span class="oui-meta">{{ t('setup.autoPicks', { mode: t(`purifier.${D.auto_purifier}` as any) }) }}</span></div>
    </section>
    <footer ref="footer" class="su-bar">
      <span v-if="!canSend && !sent" class="u1-why" id="su-why">{{ t('setup.needAck') }}</span>
      <span v-if="sent" role="status">{{ t('setup.sending') }}</span>
      <span class="u1-spacer" />
      <Button severity="secondary" outlined :label="t('setup.dontSend')" data-test="cancel" @click="cancel" />
      <Button :severity="warnings.length ? 'warn' : undefined" :disabled="!canSend" aria-describedby="su-why" data-test="send"
              :label="warnings.length ? tn('setup.sendWarn', warnings.length) : t('setup.send')" @click="send" />
    </footer>
  </div>
</template>

<style>
html { scroll-padding-bottom: calc(var(--u1-setup-footer-height, 0px) + 16px); }
body { background: var(--oui-background); }
.su { padding: 16px; display: grid; gap: 16px; max-width: 900px; margin: 0 auto; }
.su h2 { display: flex; gap: 6px; align-items: center; margin: 0 0 8px; }
.su-job { display: flex; gap: 12px; align-items: center; }
.su-job h1 { margin: 0; overflow-wrap: anywhere; }
.su-kicker { margin: 0; }
.su-thumb { width: 72px; height: 72px; object-fit: contain; border: 1px solid var(--oui-border); border-radius: 6px; }
.su-row { display: grid; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr); gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--oui-border); }
.su-fil { display: inline-flex; gap: 6px; align-items: center; overflow-wrap: anywhere; }
.su-heads { display: flex; flex-wrap: wrap; gap: 6px; }
.su-head { gap: 6px; }
.su-empty { font-style: normal; text-decoration: underline dotted; }
.su-warn { border: 1px solid var(--oui-warning); border-radius: 12px; padding: 12px; display: grid; gap: 8px; }
.su-warn [role=alert] { display: grid; gap: 6px; }
.su-opts { display: flex; flex-wrap: wrap; gap: 8px 20px; }
.su-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; position: sticky; bottom: 0; background: var(--oui-background); padding: 12px 0; border-top: 1px solid var(--oui-border); }
.u1-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.u1-spacer { flex: 1; }
.u1-sw { display: inline-block; flex: none; width: 16px; height: 16px; border-radius: 50%; border: 1px solid var(--oui-border); }
.u1-why { color: var(--oui-muted); font-size: 12px; }
.u1-warn { color: var(--oui-warning); }
@media (max-width: 560px) { .su-row { grid-template-columns: minmax(0, 1fr); } }
</style>
