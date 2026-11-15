<script setup lang="ts">
import { nextTick, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { OuiIcon, OuiPanel } from '../../shared/src/components';
import { terminal } from '../../shared/src/icons';
import * as bridge from '../core/bridge';
import { s, run, targetKnown, printerName } from '../app/store';
import { ask } from '../core/dialog';
import { t } from '../core/i18n';
import { message } from '../core/tracker';

// The log is a list of entries (role=log, append-only), capped like the previous page's 20 000 characters.
interface Line { id: number; text: string; kind: 'in' | 'out' | 'err' }
const MAX_LINES = 400;
const cmd = ref('');
const lines = ref<Line[]>([]);
const sending = ref(false);
const box = ref<HTMLElement | null>(null);
let next = 0;
function out(text: string, kind: Line['kind'] = 'out') {
  lines.value = [...lines.value, { id: ++next, text, kind }].slice(-MAX_LINES);
  void nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight; });
}
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
  <OuiPanel :icon="terminal" aria-labelledby="console-h">
    <template #title><span id="console-h">{{ t('console.title') }}</span></template>
    <div class="oui-stack">
      <form class="oui-row" @submit.prevent="send">
        <InputText id="console-cmd" v-model="cmd" class="cv-in oui-mono" aria-labelledby="console-h" aria-describedby="console-help" :placeholder="t('console.placeholder')" :disabled="!targetKnown" />
        <Button type="submit" :label="t('console.send')" :disabled="!targetKnown || !cmd.trim()" :loading="sending"><template #icon><OuiIcon :icon="terminal" :size="14" /></template></Button>
        <Button severity="secondary" text :label="t('console.clear')" :disabled="!lines.length" @click="lines = []" />
      </form>
      <p id="console-help" class="oui-meta">{{ targetKnown ? t('console.help') : t('console.noTarget') }}</p>
      <div ref="box" class="cv-log oui-well" role="log" aria-live="polite" :aria-label="t('console.log')" tabindex="0">
        <p v-if="!lines.length" class="oui-muted">{{ t('console.empty') }}</p>
        <div v-for="l in lines" :key="l.id" :class="['cv-line', l.kind]">{{ l.text }}</div>
      </div>
    </div>
  </OuiPanel>
</template>
<style>
.cv-in { flex: 1 1 280px; min-width: 0; }
.cv-log { min-height: 160px; max-height: 420px; overflow: auto; padding: var(--oui-s3); font-family: var(--oui-mono); font-size: var(--oui-text-sm); line-height: 1.5; box-shadow: inset 0 0 0 1px var(--oui-border); }
.cv-line { white-space: pre-wrap; overflow-wrap: anywhere; }
.cv-line.in { font-weight: 700; }
.cv-line.err { color: var(--oui-danger); }
</style>
