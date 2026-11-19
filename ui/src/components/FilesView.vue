<script setup lang="ts">
// The Files tab: the printer's folders as a tree, the open folder's files as a multi-select table and what is selected
// beside it (the shared OuiFileBrowser). This page owns the data and the work: it lists through the plugin (Moonraker's
// file API), and prints, saves, renames, moves and deletes. Ids are the printer's own paths ("gcodes/sub/a.gcode").
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { OuiEmpty, OuiFileBrowser, OuiHint, OuiIcon, OuiPageHeader, OuiPanel, type OuiFile, type OuiFileBrowserLabels } from '../../shared/src/components';
import { download as downloadIcon, edit, folder as folderIcon, move as moveIcon, printer, refresh, trash } from '../../shared/src/icons';
import TimelapsesCard from './TimelapsesCard.vue';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown, printerName } from '../app/store';
import { newFolder, watchThumb } from '../app/thumbs';
import { ask, choose, prompt } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import { message } from '../core/tracker';
import { fileKind, folderTree, moveTargets, rootOf } from '../core/logic';

interface Entry { name: string; size?: number; modified?: number; time?: number; weight?: number | null; thumb?: string }
const ROOTS = ['gcodes', 'camera'];
// The U1 serves its camera folder read only (Moonraker answers 405 to a delete there): its files can only be saved.
const READ_ONLY = ['camera'];
const folder = ref('gcodes');
const selected = ref<string[]>([]);
const state = ref<'idle' | 'loading' | 'ok' | 'error'>('idle');
const error = ref('');
const entries = ref<Entry[]>([]);
const paths = ref<string[]>([...ROOTS]);   // every folder of both roots, as full paths
const thumbs = ref<Record<string, string>>({});
const disk = ref('');
const gen = ref(0);
const filter = ref('');
const root = computed(() => rootOf(folder.value));
const readonly = computed(() => READ_ONLY.includes(root.value));
const rootLabel = (r: string) => (r === 'gcodes' ? t('files.root.gcodes') : t('files.root.camera'));
const idOf = (name: string) => `${folder.value}/${name}`;
const nameOf = (id: string) => id.slice(id.lastIndexOf('/') + 1);

const folders = computed(() => folderTree(paths.value, folder.value, rootLabel, READ_ONLY));
const files = computed<OuiFile[]>(() => {
  const needle = filter.value.trim().toLowerCase();
  return entries.value.filter(e => e.name.toLowerCase().includes(needle)).map(e => ({
    id: idOf(e.name), name: e.name, size: e.size ?? null, sizeText: fmt.bytes(e.size) || undefined, modified: e.modified ?? null, modifiedText: e.modified ? fmt.dateTime(e.modified) : undefined,
    kind: fileKind(e.name), thumb: thumbs.value[idOf(e.name)] ?? null,
    facts: root.value === 'gcodes' ? [{ label: t('files.col.time'), value: e.time ? fmt.duration(e.time) : null }, { label: t('files.col.weight'), value: e.weight ? fmt.grams(e.weight) : null }] : [],
  }));
});
const labels = computed<OuiFileBrowserLabels>(() => ({
  folders: t('files.folders'), files: t('nav.files'), name: t('files.col.name'), size: t('files.col.size'), modified: t('files.col.modified'),
  selectAll: t('files.selectAll'), select: name => t('files.select', { name }), items: n => tn('files.count', n), selected: n => tn('files.selected', n),
  clear: t('files.clear'), moveTo: t('files.moveToFolder'), remove: t('files.delete'), removeTitle: n => tn('files.deleteTitle', n), removeText: t('files.deleteText'),
  andMore: n => t('files.andMore', { n }), cancel: t('common.goBack'),
  empty: filter.value.trim() && entries.value.length ? t('files.noMatch', { filter: filter.value.trim() }) : t('files.empty'), loading: t('files.loading'),
  nothingSelected: t('files.none'), nothingSelectedText: root.value === 'gcodes' ? t('files.noneHint') : undefined,
}));

async function load() {
  if (!targetKnown.value || !s.info) { state.value = 'idle'; entries.value = []; return; }
  const mine = newFolder(), path = folder.value;
  gen.value = mine;
  state.value = 'loading';
  try {
    const r = await bridge.command('files', { path }, s.info.generation);
    if (mine !== gen.value) return;
    entries.value = r.files ?? [];
    // the folders in this listing join the tree at once (the whole tree is read apart, and can be late)
    paths.value = [...new Set([...paths.value, ...((r.dirs ?? []) as Entry[]).map(d => `${path}/${d.name}`)])];
    disk.value = r.disk ? t('files.free', { size: fmt.bytes(r.disk.free) }) : '';
    state.value = 'ok';
  } catch (e) {
    if (mine !== gen.value) return;
    error.value = message(e); state.value = 'error';
  }
}
// ponytail: the plugin walks each root one folder at a time (cmd_folders, at most 200 folders a root). One flat
// server.files.list a root would be a single request, but it leaves empty folders out.
let treeAsked = 0;
async function loadTree() {
  if (!targetKnown.value || !s.info) return;
  const mine = ++treeAsked, generation = s.info.generation;
  // A root that can't be walked keeps what the listings showed: the listing of the open folder reports the failure.
  const lists: string[][] = await Promise.all(ROOTS.map(r => bridge.command('folders', { root: r }, generation).then(l => (Array.isArray(l) ? l : [r]), () => paths.value.filter(p => rootOf(p) === r))));
  if (mine === treeAsked) paths.value = [...new Set([...ROOTS, ...lists.flat()])];
}
function openFolder(id: string) {
  folder.value = id; selected.value = []; entries.value = []; thumbs.value = {};
  void load();
}
const reload = () => { void load(); void loadTree(); };
let shownEpoch = s.epoch;
watch(() => [s.tab, s.epoch, s.phase], () => {
  if (s.epoch !== shownEpoch) {   // another printer: its top folder, none of the old one's folders or pictures
    shownEpoch = s.epoch; folder.value = 'gcodes'; filter.value = ''; selected.value = []; entries.value = []; thumbs.value = {}; paths.value = [...ROOTS]; treeAsked++;
  }
  if (s.tab === 'files') reload();
}, { immediate: true });

// A print file's preview is asked for only once its row is on screen (app/thumbs): the rows are the browser's, found by
// their data-file hook.
const wrap = ref<HTMLElement>();
let unwatch: (() => void)[] = [];
function watchRows() {
  unwatch.forEach(stop => stop()); unwatch = [];
  if (root.value !== 'gcodes') return;
  for (const e of entries.value) {
    const id = idOf(e.name), el = e.thumb && !thumbs.value[id] ? wrap.value?.querySelector(`[data-file="${CSS.escape(id)}"]`) : null;
    if (el) unwatch.push(watchThumb(el, gen.value, { path: id, thumb: e.thumb }, src => { thumbs.value = { ...thumbs.value, [id]: src }; }));
  }
}
watch([entries, filter], () => void nextTick(watchRows), { flush: 'post' });
onBeforeUnmount(() => unwatch.forEach(stop => stop()));

async function print(id: string) {
  if (!await ask({ title: t('act.print'), text: t('confirm.print.text', { name: nameOf(id), printer: printerName.value }), yes: t('confirm.print.yes'), no: t('common.goBack') })) return;
  await run({ key: 'print', label: t('act.print'), cmd: 'print_file', args: { path: id }, okText: t('ok.print'), timeoutMs: 60000 });
}
async function download(id: string) {
  const r = await run({ key: `dl:${id}`, label: t('act.download'), cmd: 'download', args: { path: id }, timeoutMs: 120000 });
  if (r.ok) tracker.notify('success', t('ok.saved', { path: r.result }));
}
const onOpen = (id: string) => (root.value === 'gcodes' ? print(id) : download(id));
/** Ask for a new name; null when the dialog was left or the name was kept. */
async function newName(name: string): Promise<string | null> {
  const n = ((await prompt({ title: t('files.rename'), text: t('files.renameTo', { name }), yes: t('files.rename'), no: t('common.goBack'),
    input: { label: t('files.newName'), value: name } })) || '').trim();
  return n && n !== name ? n : null;
}
async function rename(id: string) {
  const name = await newName(nameOf(id));
  if (!name) return;
  const r = await run({ key: `ren:${id}`, label: t('act.rename'), cmd: 'rename', args: { path: id, name }, okText: t('ok.rename') });
  if (r.ok) void load();
}
// Several files: one command a file, in order. A file that fails says so itself; the rest still go, and one message
// says how many were done.
async function each(ids: string[], send: (id: string) => Promise<{ ok: boolean }>, done: string) {
  let ok = 0;
  for (const id of ids) if ((await send(id)).ok) ok++;
  if (ok) tracker.notify('success', tn(done, ok));
  void load();
}
const onMove = ({ ids, to }: { ids: string[]; to: string }) => each(ids, id => run({ key: `mv:${id}`, label: t('act.move'), cmd: 'move', args: { path: id, folder: to } }), 'files.moved');
// The browser asked first (its own confirmation, with the count and the names).
const onDelete = (ids: string[]) => each(ids, id => run({ key: `del:${id}`, label: t('act.delete'), cmd: 'delete', args: { path: id } }), 'files.deleted');

// ---------------------------------------------------------------- folders: a new one, and the open one renamed, moved or deleted
const parent = computed(() => folder.value.slice(0, Math.max(0, folder.value.lastIndexOf('/'))));
/** The open folder went somewhere else (or away): the tree forgets its old place until it is read again. */
function folderNow(was: string, now: string) {
  paths.value = [...paths.value.filter(p => p !== was && !p.startsWith(was + '/')), ...(now ? [now] : [])];
  openFolder(now || rootOf(was));
  void loadTree();
}
async function mkdir() {
  const n = ((await prompt({ title: t('files.newFolder'), text: t('files.newFolderIn', { path: folder.value }), yes: t('files.create'), no: t('common.goBack'),
    input: { label: t('files.folderName'), value: '' } })) || '').trim();
  if (!n) return;
  const path = idOf(n);
  const r = await run({ key: 'mkdir', label: t('act.mkdir'), cmd: 'mkdir', args: { path }, okText: t('ok.mkdir') });
  if (r.ok) { paths.value = [...new Set([...paths.value, path])]; void loadTree(); }
}
async function renameFolder() {
  const was = folder.value, name = await newName(nameOf(was));
  if (!name) return;
  const r = await run({ key: `ren:${was}`, label: t('act.rename'), cmd: 'rename', args: { path: was, name }, okText: t('ok.rename') });
  if (r.ok) folderNow(was, r.result?.path ?? `${parent.value}/${name}`);
}
async function moveFolder() {
  const was = folder.value, name = nameOf(was);
  const items = moveTargets(paths.value.filter(p => rootOf(p) === root.value), parent.value, name)
    .map(f => ({ value: f, label: f === root.value ? t('files.top', { root: rootLabel(root.value) }) : f.slice(root.value.length + 1) }));
  if (!items.length) { tracker.notify('error', t('files.noFolder')); return; }
  const dest = await choose({ title: t('files.move'), text: t('files.moveTo', { name }), choices: items, no: t('common.goBack') });
  if (!dest) return;
  const r = await run({ key: `mv:${was}`, label: t('act.move'), cmd: 'move', args: { path: was, folder: dest }, okText: t('ok.move') });
  if (r.ok) folderNow(was, r.result?.path ?? `${dest}/${name}`);
}
async function deleteFolder() {
  const was = folder.value;
  if (!await ask({ title: t('files.delete'), text: t('confirm.deleteDir.text', { name: nameOf(was) }), yes: t('confirm.delete.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: `del:${was}`, label: t('act.delete'), cmd: 'delete', args: { path: was, is_dir: true }, okText: t('ok.delete') });
  if (r.ok) { paths.value = paths.value.filter(p => p !== was && !p.startsWith(was + '/')); openFolder(parent.value); void loadTree(); }
}
</script>
<template>
  <div class="u1-head">
    <OuiPageHeader :title="t('nav.files')" :meta="disk">
      <template #actions>
        <Button severity="secondary" text :label="t('files.newFolder')" :disabled="state !== 'ok' || readonly" :aria-describedby="readonly ? 'files-ro' : undefined" data-test="files-mkdir" @click="mkdir">
          <template #icon><OuiIcon :icon="folderIcon" :size="14" /></template></Button>
        <Button severity="secondary" :label="t('common.refresh')" :loading="state === 'loading'" :disabled="!targetKnown" data-test="files-refresh" @click="reload">
          <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
      </template>
    </OuiPageHeader>
    <div id="u1-banner-files" />
  </div>
  <OuiPanel v-if="!targetKnown" flush><OuiEmpty compact state="offline" :title="t('files.noTarget')" /></OuiPanel>
  <OuiPanel v-else-if="state === 'error'" flush>
    <OuiEmpty compact state="error" :title="t('files.error', { error })">
      <template #actions>
        <Button v-if="folder !== root" size="small" severity="secondary" text :label="rootLabel(root)" @click="openFolder(root)" />
        <Button size="small" severity="secondary" :label="t('common.retry')" @click="reload"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
      </template>
    </OuiEmpty>
  </OuiPanel>
  <div v-else ref="wrap" class="fv" data-test="files">
    <OuiFileBrowser v-model:selected="selected" :folder="folder" :folders="folders" :files="files" :labels="labels" :loading="state !== 'ok' && !entries.length"
                    :readonly="readonly" :describedby="readonly ? 'files-ro' : undefined" @update:folder="openFolder" @move="onMove" @delete="onDelete" @open="onOpen">
      <template #toolbar>
        <!-- Why Move and Delete are off here is said once, beside the folder's name. -->
        <template v-if="readonly"><span id="files-ro" class="oui-chip">{{ t('files.readOnly') }}</span><OuiHint end :label="t('files.readOnly')" :text="t('files.readOnlyWhy')" /></template>
        <!-- The open folder itself: the tree shows where it is, these act on it. A file root is never renamed, moved or deleted. -->
        <span v-else-if="folder !== root" class="fv-folder" role="group" :aria-label="nameOf(folder)">
          <Button size="small" severity="secondary" text :aria-label="t('files.renameLabel', { name: nameOf(folder) })" :title="t('files.renameLabel', { name: nameOf(folder) })" data-test="folder-rename" @click="renameFolder"><template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
          <Button size="small" severity="secondary" text :aria-label="t('files.moveLabel', { name: nameOf(folder) })" :title="t('files.moveLabel', { name: nameOf(folder) })" data-test="folder-move" @click="moveFolder"><template #icon><OuiIcon :icon="moveIcon" :size="14" /></template></Button>
          <Button size="small" severity="danger" outlined :aria-label="t('files.deleteLabel', { name: nameOf(folder) })" :title="t('files.deleteLabel', { name: nameOf(folder) })" data-test="folder-delete" @click="deleteFolder"><template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
        </span>
        <InputText id="files-filter" v-model="filter" type="search" size="small" :placeholder="t('files.filter')" :aria-label="t('files.filter')" class="fv-q" />
      </template>
      <template #actions="{ file }">
        <Button v-if="root === 'gcodes'" :label="t('files.print')" :aria-label="t('files.printLabel', { name: file.name })" :disabled="!!s.status?.busy" :aria-describedby="s.status?.busy ? 'heads-why' : undefined" data-test="file-print" @click="print(file.id)">
          <template #icon><OuiIcon :icon="printer" :size="14" /></template></Button>
        <Button severity="secondary" :label="t('files.save')" :aria-label="t('files.saveLabel', { name: file.name })" :loading="tracker.isBusy(`dl:${file.id}`)" data-test="file-save" @click="download(file.id)">
          <template #icon><OuiIcon :icon="downloadIcon" :size="14" /></template></Button>
        <Button v-if="!readonly" severity="secondary" text :label="t('files.rename')" :aria-label="t('files.renameLabel', { name: file.name })" data-test="file-rename" @click="rename(file.id)">
          <template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
      </template>
    </OuiFileBrowser>
  </div>
  <TimelapsesCard />
</template>
<style>
/* The browser fills the window under the bars and leaves the time-lapses' header in sight below it. */
.fv { --oui-files-height: clamp(360px, calc(100vh - 300px), 720px); min-width: 0; }
@supports (height: 100dvh) { .fv { --oui-files-height: clamp(360px, calc(100dvh - 300px), 720px); } }
.fv-q { width: 220px; max-width: 100%; }
/* foundation-gap: OuiFileBrowser (5.0.0) gives the date column 132 px, which cuts a date with its time ("11/18/26, 7:04 PM"). */
.fv .oui-files-table th:nth-child(4) { width: 168px; }
.fv-folder { display: inline-flex; align-items: center; gap: var(--oui-s1); }
</style>
