<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import InputText from 'primevue/inputtext';
import { OuiEmpty, OuiIcon, OuiPanel, OuiToolbar } from '../../shared/src/components';
import { download as downloadIcon, edit, files as filesIcon, folder, move as moveIcon, plus, printer, refresh, trash, undo } from '../../shared/src/icons';
import Thumb from './Thumb.vue';
import TimelapsesCard from './TimelapsesCard.vue';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown, printerName } from '../app/store';
import { newFolder } from '../app/thumbs';
import { ask, choose, prompt } from '../core/dialog';
import { t, fmt } from '../core/i18n';
import { message } from '../core/tracker';
import { moveTargets } from '../core/logic';

interface Entry { name: string; size?: number; modified?: number; time?: number; weight?: number | null; thumb?: string }
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
const filter = ref('');
const match = (e: Entry) => e.name.toLowerCase().includes(filter.value.trim().toLowerCase());
const shownDirs = computed(() => dirs.value.filter(match));
const shownFiles = computed(() => files.value.filter(match));

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
let shownEpoch = s.epoch;
watch(() => [s.tab, s.epoch, s.phase], () => {
  if (s.epoch !== shownEpoch) { shownEpoch = s.epoch; path.value = 'gcodes'; filter.value = ''; }   // another printer: its top folder
  if (s.tab === 'files') void load();
}, { immediate: true });
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
async function rename(name: string) {
  const n = ((await prompt({ title: t('files.rename'), text: t('files.renameTo', { name }), yes: t('files.rename'), no: t('common.goBack'),
    input: { label: t('files.newName'), value: name } })) || '').trim();
  if (!n || n === name) return;
  const r = await run({ key: `ren:${name}`, label: t('act.rename'), cmd: 'rename', args: { path: `${path.value}/${name}`, name: n }, okText: t('ok.rename') });
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
  <OuiPanel :icon="filesIcon" flush aria-labelledby="files-h">
    <template #title><span id="files-h">{{ t('nav.files') }}</span></template>
    <template #meta>{{ disk }}</template>
    <template #actions>
      <Button severity="secondary" size="small" :label="t('files.newFolder')" :disabled="state !== 'ok'" @click="mkdir"><template #icon><OuiIcon :icon="plus" :size="14" /></template></Button>
      <Button severity="secondary" size="small" :label="t('files.up')" :disabled="!path.includes('/')" data-test="up" @click="up"
              @dragover="e => { if (dragName && path.includes('/')) e.preventDefault(); }" @drop.prevent="drop(null)"><template #icon><OuiIcon :icon="undo" :size="14" /></template></Button>
      <Button severity="secondary" size="small" :label="t('common.refresh')" :loading="state === 'loading'" :disabled="!targetKnown" @click="load"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
    </template>
    <OuiToolbar class="fv-bar" :label="t('files.root')">
      <Select :model-value="root" :options="roots" option-label="label" option-value="value" size="small" :aria-label="t('files.root')" @update:model-value="setRoot" />
      <strong class="fv-path oui-mono">{{ path }}</strong>
      <template #end><InputText id="files-filter" v-model="filter" type="search" size="small" :placeholder="t('files.filter')" :aria-label="t('files.filter')" class="fv-q" /></template>
    </OuiToolbar>
    <OuiEmpty v-if="!targetKnown" state="offline" :title="t('files.noTarget')" />
    <OuiEmpty v-else-if="state === 'loading' && !dirs.length && !files.length" state="loading" :title="t('files.loading')" role="status" />
    <OuiEmpty v-else-if="state === 'error'" state="error" :title="t('files.error', { error })">
      <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="load"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
    </OuiEmpty>
    <OuiEmpty v-else-if="state === 'ok' && !dirs.length && !files.length" :icon="folder" :title="t('files.empty')" />
    <div v-else-if="state === 'ok'" class="oui-table-wrap">
      <table class="u1-table fv-table">
        <thead><tr><th scope="col" class="fv-thumb"><span class="oui-sr">{{ t('files.col.thumb') }}</span></th><th scope="col">{{ t('files.col.name') }}</th>
          <th scope="col" class="oui-num">{{ t('files.col.size') }}</th><th scope="col">{{ t('files.col.modified') }}</th><th scope="col" class="oui-num">{{ t('files.col.time') }}</th>
          <th scope="col" class="oui-num">{{ t('files.col.weight') }}</th><th scope="col" class="oui-end"><span class="oui-sr">{{ t('files.col.actions') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="d in shownDirs" :key="'d:' + d.name" draggable="true" :class="{ drop: dropOn === d.name }"
              @dragstart="dragName = d.name" @dragover="e => { if (dragName && dragName !== d.name) { e.preventDefault(); dropOn = d.name; } }"
              @dragleave="dropOn = null" @drop.prevent="drop(d.name)">
            <td class="fv-thumb"><OuiIcon :icon="folder" :size="20" tile soft /></td>
            <td><Button text severity="secondary" :label="d.name" :aria-label="t('files.open', { name: d.name })" class="fv-open" @click="open(d.name)" /></td>
            <td /><td /><td /><td />
            <td class="oui-end"><div class="fv-acts">
              <Button size="small" severity="secondary" text :aria-label="t('files.renameLabel', { name: d.name })" :title="t('files.rename')" @click="rename(d.name)"><template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
              <Button size="small" severity="secondary" text :aria-label="t('files.moveLabel', { name: d.name })" :title="t('files.move')" @click="move(d.name)"><template #icon><OuiIcon :icon="moveIcon" :size="14" /></template></Button>
              <Button size="small" severity="danger" text class="fv-del" :aria-label="t('files.deleteLabel', { name: d.name })" :title="t('files.delete')" @click="del(d.name, true)"><template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
            </div></td>
          </tr>
          <tr v-for="f in shownFiles" :key="'f:' + f.name" draggable="true" @dragstart="dragName = f.name">
            <td class="fv-thumb"><Thumb v-if="root === 'gcodes'" :gen="gen" :path="`${path}/${f.name}`" :rel="f.thumb" /></td>
            <td class="fv-name oui-strong">{{ f.name }}</td><td class="oui-num">{{ fmt.bytes(f.size) }}</td>
            <td>{{ f.modified ? fmt.dateTime(f.modified) : '' }}</td><td class="oui-num">{{ f.time ? fmt.duration(f.time) : '' }}</td>
            <td class="oui-num">{{ f.weight ? fmt.grams(f.weight) : '' }}</td>
            <td class="oui-end"><div class="fv-acts">
              <Button v-if="root === 'gcodes'" size="small" severity="secondary" :label="t('files.print')" :aria-label="t('files.printLabel', { name: f.name })" :disabled="!!s.status?.busy"
                      :aria-describedby="s.status?.busy ? 'heads-why' : undefined" @click="print(f.name)"><template #icon><OuiIcon :icon="printer" :size="14" /></template></Button>
              <Button v-else size="small" severity="secondary" :label="t('files.save')" :aria-label="t('files.saveLabel', { name: f.name })" :loading="tracker.isBusy(`dl:${f.name}`)" @click="download(f.name)">
                <template #icon><OuiIcon :icon="downloadIcon" :size="14" /></template></Button>
              <Button size="small" severity="secondary" text :aria-label="t('files.renameLabel', { name: f.name })" :title="t('files.rename')" @click="rename(f.name)"><template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
              <Button size="small" severity="secondary" text :aria-label="t('files.moveLabel', { name: f.name })" :title="t('files.move')" @click="move(f.name)"><template #icon><OuiIcon :icon="moveIcon" :size="14" /></template></Button>
              <Button size="small" severity="danger" text class="fv-del" :aria-label="t('files.deleteLabel', { name: f.name })" :title="t('files.delete')" @click="del(f.name, false)"><template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
            </div></td>
          </tr>
          <tr v-if="!shownDirs.length && !shownFiles.length"><td colspan="7" class="oui-muted">{{ t('files.noMatch', { filter: filter.trim() }) }}</td></tr>
        </tbody>
      </table>
    </div>
    <template v-if="state === 'ok' && (dirs.length || files.length)" #footer><p class="oui-meta">{{ t('files.dragHint') }}</p></template>
  </OuiPanel>
  <TimelapsesCard />
</template>
<style>
.fv-bar { border-bottom: 1px solid var(--oui-border); }
.fv-path, .fv-name { overflow-wrap: anywhere; }
.fv-q { width: 220px; max-width: 100%; }
.fv-thumb { width: 64px; }
.fv-open.p-button { padding-inline: 0; font-weight: 600; }
/* Delete is the destructive one: red, last, and a gap away from the actions used all the time. It always asks first. */
.fv-acts { display: inline-flex; align-items: center; justify-content: flex-end; gap: var(--oui-s1); white-space: nowrap; }
.fv-del { margin-inline-start: var(--oui-s3); }
.fv-table tr.drop > td { background: var(--oui-success-bg); }
</style>
