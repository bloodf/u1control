<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import Message from 'primevue/message';
import Icon from './Icon.vue';
import Thumb from './Thumb.vue';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown, printerName } from '../app/store';
import { newFolder } from '../app/thumbs';
import { ask, choose, prompt } from '../core/dialog';
import { t, fmt } from '../core/i18n';
import { message } from '../core/tracker';
import { moveTargets } from '../core/logic';

interface Entry { name: string; size?: number; modified?: number; time?: number; thumb?: string }
const path = ref('gcodes');
const state = ref<'idle' | 'loading' | 'ok' | 'error'>('idle');
const error = ref('');
const dirs = ref<Entry[]>([]);
const files = ref<Entry[]>([]);
const disk = ref('');
const gen = ref(0);
const root = computed(() => path.value.split('/')[0]);
const roots = computed(() => [{ value: 'gcodes', label: t('files.root.gcodes') }, { value: 'camera', label: t('files.root.camera') }]);
const rootLabel = (r: string) => (r === 'gcodes' ? t('files.root.gcodes') : t('files.root.camera'));

async function load() {
  if (!targetKnown.value || !s.info) { state.value = 'idle'; dirs.value = []; files.value = []; return; }
  const mine = newFolder(), folder = path.value;
  gen.value = mine;
  state.value = 'loading';
  try {
    const r = await bridge.command('files', { path: folder }, s.info.generation);
    if (mine !== gen.value) return;
    dirs.value = r.dirs ?? []; files.value = r.files ?? [];
    disk.value = r.disk ? t('files.free', { size: fmt.bytes(r.disk.free) }) : '';
    state.value = 'ok';
  } catch (e) {
    if (mine !== gen.value) return;
    error.value = message(e); state.value = 'error';
  }
}
watch(() => [s.tab, s.epoch, s.phase], () => { if (s.tab === 'files') void load(); }, { immediate: true });
function open(name: string) { path.value = `${path.value}/${name}`; void load(); }
function up() { if (path.value.includes('/')) { path.value = path.value.split('/').slice(0, -1).join('/'); void load(); } }
function setRoot(r: string) { path.value = r; void load(); }

async function del(name: string, dir: boolean) {
  if (!await ask({ title: t('files.delete'), text: t(dir ? 'confirm.deleteDir.text' : 'confirm.delete.text', { name }), yes: t('confirm.delete.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: `del:${name}`, label: t('act.delete'), cmd: 'delete', args: { path: `${path.value}/${name}`, ...(dir ? { is_dir: true } : {}) }, okText: t('ok.delete') });
  if (r.ok) void load();
}
async function print(name: string) {
  if (!await ask({ title: t('act.print'), text: t('confirm.print.text', { name, printer: printerName.value }), yes: t('confirm.print.yes'), no: t('common.goBack') })) return;
  await run({ key: 'print', label: t('act.print'), cmd: 'print_file', args: { path: `${path.value}/${name}` }, okText: t('ok.print'), timeoutMs: 60000 });
}
async function download(name: string) {
  const r = await run({ key: `dl:${name}`, label: t('act.download'), cmd: 'download', args: { path: `${path.value}/${name}` }, timeoutMs: 120000 });
  if (r.ok) tracker.notify('success', t('ok.saved', { path: r.result }));
}
async function move(name: string) {
  let folders: string[];
  try { folders = await bridge.command('folders', { root: root.value }, s.info?.generation); }
  catch (e) { tracker.notify('error', t('msg.failed', { action: t('act.move'), error: message(e) })); return; }
  const items = moveTargets(folders, path.value, name).map(f => ({ value: f, label: f === root.value ? t('files.top', { root: rootLabel(root.value) }) : f.slice(root.value.length + 1) }));
  if (!items.length) { tracker.notify('error', t('files.noFolder')); return; }
  const dest = await choose({ title: t('files.move'), text: t('files.moveTo', { name }), choices: items, no: t('common.goBack') });
  if (dest) await moveTo(name, dest);
}
async function moveTo(name: string, folder: string) {
  const r = await run({ key: `mv:${name}`, label: t('act.move'), cmd: 'move', args: { path: `${path.value}/${name}`, folder }, okText: t('ok.move') });
  if (r.ok) void load();
}
async function mkdir() {
  const n = ((await prompt({ title: t('files.newFolder'), text: t('files.newFolderIn', { path: path.value }), yes: t('files.create'), no: t('common.goBack'),
    input: { label: t('files.folderName'), value: '' } })) || '').trim();
  if (!n) return;
  const r = await run({ key: 'mkdir', label: t('act.mkdir'), cmd: 'mkdir', args: { path: `${path.value}/${n}` }, okText: t('ok.mkdir') });
  if (r.ok) void load();
}
// Drag a row onto a folder row (or onto Up) to move it there.
const dragName = ref<string | null>(null);
const dropOn = ref<string | null>(null);
function drop(dir: string | null) {
  const name = dragName.value; dragName.value = null; dropOn.value = null;
  if (!name || name === dir) return;
  void moveTo(name, dir === null ? path.value.split('/').slice(0, -1).join('/') : `${path.value}/${dir}`);
}
</script>
<template>
  <section class="u1-card" aria-labelledby="files-h">
    <h2 id="files-h" class="fv-sr"><Icon name="icon/files" /> {{ t('nav.files') }}</h2>
    <div class="u1-row fv-bar">
      <label id="fv-root-l" class="fv-sr-only">{{ t('files.root') }}</label>
      <Select :model-value="root" :options="roots" option-label="label" option-value="value" aria-labelledby="fv-root-l" @update:model-value="setRoot" />
      <strong class="fv-path">{{ path }}</strong><span class="u1-spacer" /><span class="oui-meta">{{ disk }}</span>
      <Button severity="secondary" outlined :disabled="state !== 'ok'" @click="mkdir"><Icon name="icon/folder" /><span>{{ t('files.newFolder') }}</span></Button>
      <Button severity="secondary" outlined :disabled="!path.includes('/')" data-test="up" @click="up"
              @dragover="e => { if (dragName && path.includes('/')) e.preventDefault(); }" @drop.prevent="drop(null)">
        <Icon name="icon/folder" /><span>{{ t('files.up') }}</span></Button>
      <Button severity="secondary" outlined :label="t('common.refresh')" :loading="state === 'loading'" :disabled="!targetKnown" @click="load" />
    </div>
    <p v-if="!targetKnown" class="oui-muted">{{ t('files.noTarget') }}</p>
    <p v-else-if="state === 'loading' && !dirs.length && !files.length" class="oui-muted" role="status">{{ t('files.loading') }}</p>
    <Message v-else-if="state === 'error'" severity="error">{{ t('files.error', { error }) }}
      <div><Button size="small" severity="secondary" outlined :label="t('common.retry')" @click="load" /></div></Message>
    <div v-else-if="state === 'ok'" class="oui-table-wrap">
      <table class="u1-table">
        <thead><tr><th scope="col"><span class="fv-sr-only">{{ t('files.col.thumb') }}</span></th><th scope="col">{{ t('files.col.name') }}</th>
          <th scope="col">{{ t('files.col.size') }}</th><th scope="col">{{ t('files.col.modified') }}</th><th scope="col">{{ t('files.col.time') }}</th>
          <th scope="col">{{ t('files.col.actions') }}</th></tr></thead>
        <tbody>
          <tr v-for="d in dirs" :key="'d:' + d.name" draggable="true" :class="{ drop: dropOn === d.name }"
              @dragstart="dragName = d.name" @dragover="e => { if (dragName && dragName !== d.name) { e.preventDefault(); dropOn = d.name; } }"
              @dragleave="dropOn = null" @drop.prevent="drop(d.name)">
            <td><Icon name="icon/folder" :size="24" /></td>
            <td><Button text :label="d.name" :aria-label="t('files.open', { name: d.name })" class="fv-open" @click="open(d.name)" /></td>
            <td /><td /><td />
            <td class="fv-acts"><Button size="small" severity="secondary" outlined @click="move(d.name)"><Icon name="icon/folder" /><span>{{ t('files.move') }}</span></Button>
              <Button size="small" severity="danger" outlined @click="del(d.name, true)"><Icon name="icon/delete" /><span>{{ t('files.delete') }}</span></Button></td>
          </tr>
          <tr v-for="f in files" :key="'f:' + f.name" draggable="true" @dragstart="dragName = f.name">
            <td><Thumb v-if="root === 'gcodes'" :gen="gen" :path="`${path}/${f.name}`" :rel="f.thumb" /></td>
            <td class="fv-name">{{ f.name }}</td><td class="u1-num">{{ fmt.bytes(f.size) }}</td>
            <td>{{ f.modified ? fmt.dateTime(f.modified) : '' }}</td><td class="u1-num">{{ f.time ? fmt.duration(f.time) : '' }}</td>
            <td class="fv-acts">
              <Button v-if="root === 'gcodes'" size="small" :disabled="!!s.status?.busy" @click="print(f.name)"><Icon name="icon/print-setup" /><span>{{ t('files.print') }}</span></Button>
              <Button v-else size="small" severity="secondary" outlined :loading="tracker.isBusy(`dl:${f.name}`)" @click="download(f.name)"><Icon name="icon/download" /><span>{{ t('files.save') }}</span></Button>
              <Button size="small" severity="secondary" outlined @click="move(f.name)"><Icon name="icon/folder" /><span>{{ t('files.move') }}</span></Button>
              <Button size="small" severity="danger" outlined @click="del(f.name, false)"><Icon name="icon/delete" /><span>{{ t('files.delete') }}</span></Button></td>
          </tr>
          <tr v-if="!dirs.length && !files.length"><td colspan="6"><div class="fv-empty"><Icon name="spot/no-files" :size="96" /><span>{{ t('files.empty') }}</span></div></td></tr>
        </tbody>
      </table>
      <p class="oui-meta">{{ t('files.dragHint') }}</p>
    </div>
  </section>
</template>
<style scoped>
.fv-sr { margin: 0 0 12px; }
.fv-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.fv-bar { margin-bottom: 12px; }
.fv-path, .fv-name { overflow-wrap: anywhere; }
.fv-open { padding: 0; }
.fv-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.fv-empty { display: grid; justify-items: center; gap: 8px; padding: 16px; color: var(--oui-muted); }
tr.drop td { background: var(--oui-success-bg, rgba(0, 103, 91, .12)); }
</style>
