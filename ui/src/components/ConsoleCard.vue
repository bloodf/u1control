<script lang="ts">
import { ref } from 'vue';
// The log outlives the widget (removed and added again, another layout): it is the page's, not the card's.
export interface Line { id: number; text: string; kind: 'in' | 'out' | 'err' }
const lines = ref<Line[]>([]);
let next = 0;
</script>
<script setup lang="ts">
import { nextTick, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { OuiIcon, OuiPanel, OuiWidgetMaximize } from '@orca-plugins/ui-foundation/src/components';
import { terminal } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { s, run, targetKnown, printerName } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import { message } from '../core/tracker';

// The G-code console, a dashboard widget: the command line over the log (role=log, append-only). The log takes the rest
// of the widget's height, so a taller widget shows more lines; `lines` (its setting) is how many it keeps.
const props = withDefaults(defineProps<{ config?: { lines?: number } }>(), { config: () => ({}) });
const cmd = ref('');
const sending = ref(false);
const box = ref<HTMLElement | null>(null);
const keep = () => props.config.lines ?? 400;
watch(keep, n => { lines.value = lines.value.slice(-n); });
function out(text: string, kind: Line['kind'] = 'out') {
  lines.value = [...lines.value, { id: ++next, text, kind }].slice(-keep());
  void nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight; });
}
function clear() { lines.value = []; }
async function send() {
  const c = cmd.value.trim();
  if (!c || sending.value) return;
  cmd.value = '';
  out('> ' + c, 'in');
  if (/(^|\n)\s*M112\b/i.test(c)) {   // same urgent path and confirmation as the E-stop button
    if (!await ask({ title: t('confirm.estop.title'), text: t('confirm.estop.text', { printer: printerName.value }), yes: t('confirm.estop.yes'), no: t('common.goBack'), danger: true })) {
      out(t('console.cancelled')); return;
    }
    const r = await run({ key: 'estop', label: t('act.estop'), cmd: 'emergency_stop', timeoutMs: 10000, allowRepeat: true, okText: t('ok.estop') });
    out(r.ok ? t('console.estopSent') : `!! ${r.error ?? r.reason}`, r.ok ? 'out' : 'err');
    return;
  }
  sending.value = true;
  try {
    const r = await bridge.command('gcode', { script: c }, s.info?.generation);
    out(t('console.accepted'));
    for (const l of r.output ?? []) out('  ' + l);
    if (r.note) out(`  (${r.note})`);
  } catch (e) {
    out('!! ' + message(e), 'err');
  } finally {
    sending.value = false;
  }
}
</script>
<template>
  <OuiPanel :icon="terminal" aria-labelledby="console-h" :meta="targetKnown ? printerName : t('console.noTarget')" :hint="t('console.help')" hint-id="console-help" :hint-label="t('console.title')" data-test="console">
    <template #title><span id="console-h">{{ t('console.title') }}</span></template>
    <template #actions>
      <Button severity="secondary" text size="small" :label="t('console.clear')" :disabled="!lines.length" data-test="console-clear" @click="clear" />
      <OuiWidgetMaximize />
    </template>
    <div class="cv">
      <form class="oui-row cv-form" @submit.prevent="send">
        <InputText id="console-cmd" v-model="cmd" class="cv-in oui-mono" :aria-label="t('console.title')" aria-describedby="console-help" :placeholder="t('console.placeholder')" :disabled="!targetKnown" />
        <Button type="submit" :label="t('console.send')" :disabled="!targetKnown || !cmd.trim()" :loading="sending"><template #icon><OuiIcon :icon="terminal" :size="14" /></template></Button>
      </form>
      <div ref="box" class="cv-log oui-well" role="log" aria-live="polite" :aria-label="t('console.log')" tabindex="0" data-test="console-log">
        <p v-if="!lines.length" class="oui-muted">{{ t('console.empty') }}</p>
        <div v-for="l in lines" :key="l.id" :class="['cv-line', l.kind]">{{ l.text }}</div>
      </div>
    </div>
  </OuiPanel>
</template>
<style>
/* The log fills what the widget leaves under the command line; in the narrow single column it has its own height. */
.cv { display: flex; flex-direction: column; gap: var(--oui-s3); height: 100%; min-height: 0; }
.cv-form { flex: none; }
.cv-in { flex: 1 1 200px; min-width: 0; }
.cv-log { flex: 1 1 0; min-height: 96px; overflow: auto; padding: var(--oui-s2) var(--oui-s3); font-family: var(--oui-mono); font-size: var(--oui-text-sm); line-height: 1.5; box-shadow: inset 0 0 0 1px var(--oui-border); }
.oui-dash-grid[data-narrow] .cv-log { flex: none; height: 240px; }
.cv-line { white-space: pre-wrap; overflow-wrap: anywhere; }
.cv-line.in { font-weight: 700; }
.cv-line.err { color: var(--oui-danger); }
</style>
