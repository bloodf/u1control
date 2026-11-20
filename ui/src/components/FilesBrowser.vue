<script setup lang="ts">
// One printer's files: the shared OuiFileBrowser over useFileBackend, which reads, shows a failed read with its way out,
// runs a move or delete and reads again. This component gives the storage (the plugin's Moonraker file commands, with the
// printer's own paths as ids: "gcodes/sub/a.gcode") and what the page adds: print, save and rename a file; make a
// folder; rename, move and delete the open one. FilesView makes a new one for every printer.
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { OuiFileBrowser, OuiHint, OuiIcon, useFileBackend, type OuiFile, type OuiFileBackend, type OuiFileBrowserLabels } from '@orca-plugins/ui-foundation/src/components';
import { download as downloadIcon, edit, move as moveIcon, plus, printer, trash } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { s, run, tracker, printerName } from '../app/store';
import { newFolder, watchThumb } from '../app/thumbs';
import { ask, choose, prompt } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import { fileKind, folderTree, moveTargets, rootOf } from '../core/logic';

/** A file as the printer listed it. Its texts, kind, picture and facts are added where it is shown, in the page's language. */
interface Listed extends OuiFile { time?: number; weight?: number | null; rel?: string }
// The U1 serves its camera folder read only (Moonraker answers 405 to a delete there): its files can only be saved.
const READ_ONLY = ['camera'];
const rootLabel = (r: string) => (r === 'gcodes' ? t('files.root.gcodes') : t('files.root.camera'));
const nameOf = (id: string) => id.slice(id.lastIndexOf('/') + 1);
const command = (cmd: string, args: Record<string, unknown>) => bridge.command(cmd, args, s.info?.generation);
const disk = ref('');
let gen = 0;   // the newest listing's turn in the picture queue (app/thumbs): pictures asked for an older one are dropped

// Several files: one command a file, in order. A file that fails says so itself (the tracker's message) and the rest
// still go; one message says how many were done. Rejects when any failed: the list is read again either way.
async function each(ids: string[], done: string, send: (id: string) => Promise<{ ok: boolean }>): Promise<void> {
  let ok = 0;
  for (const id of ids) if ((await send(id)).ok) ok++;
  if (ok) tracker.notify('success', tn(done, ok));
  if (ok < ids.length) throw new Error(`${ok} of ${ids.length}`);
}
const backend: OuiFileBackend = {
  // ponytail: the plugin walks a root one folder at a time (cmd_folders, at most 200 folders a root); the open folder's
  // files are read beside it. One flat server.files.list a root would be a single request, but it leaves empty folders out.
  // A root that can't be walked is still listed: opening it says what is wrong.
  folders: async () => folderTree((await Promise.all(['gcodes', 'camera'].map(root => command('folders', { root }).then(l => (Array.isArray(l) ? l as string[] : [root]), () => [root])))).flat(), rootLabel, READ_ONLY),
  async list(folder) {
    gen = newFolder();
    const r = await command('files', { path: folder });
    disk.value = r.disk ? t('files.free', { size: fmt.bytes(r.disk.free) }) : '';
    return ((r.files ?? []) as { name: string; size?: number; modified?: number; time?: number; weight?: number | null; thumb?: string }[])
      .map((e): Listed => ({ id: `${folder}/${e.name}`, name: e.name, size: e.size ?? null, modified: e.modified ?? null, time: e.time, weight: e.weight, rel: e.thumb }));
  },
  // The browser asked first (its own confirmation, with the count and the names).
  remove: ids => each(ids, 'files.deleted', id => run({ key: `del:${id}`, label: t('act.delete'), cmd: 'delete', args: { path: id } })),
  move: (ids, to) => each(ids, 'files.moved', id => run({ key: `mv:${id}`, label: t('act.move'), cmd: 'move', args: { path: id, folder: to } })),
};
// A file that failed has already said why (each, above): nothing to add here.
const files = useFileBackend(backend, { folder: 'gcodes', onError: () => {} });
defineExpose({ reload: () => files.reload({ quiet: true }), disk, loading: computed(() => files.loading) });

const root = computed(() => rootOf(files.folder));
const filter = ref('');
const thumbs = ref<Record<string, string>>({});
watch(() => files.folder, () => { thumbs.value = {}; filter.value = ''; });
const shown = computed<OuiFile[]>(() => {
  const needle = filter.value.trim().toLowerCase();
  return (files.files as Listed[]).filter(f => f.name.toLowerCase().includes(needle)).map(f => ({
    id: f.id, name: f.name, size: f.size, sizeText: fmt.bytes(f.size) || undefined, modified: f.modified, modifiedText: f.modified ? fmt.dateTime(f.modified) : undefined,
    kind: fileKind(f.name), thumb: thumbs.value[f.id] ?? null,
    facts: root.value === 'gcodes' ? [{ label: t('files.col.time'), value: f.time ? fmt.duration(f.time) : null }, { label: t('files.col.weight'), value: f.weight ? fmt.grams(f.weight) : null }] : [],
  }));
});
const labels = computed<OuiFileBrowserLabels>(() => ({
  folders: t('files.folders'), files: t('nav.files'), name: t('files.col.name'), size: t('files.col.size'), modified: t('files.col.modified'),
  selectAll: t('files.selectAll'), select: name => t('files.select', { name }), items: n => (filter.value.trim() ? t('files.showing', { shown: n, total: files.files.length }) : tn('files.count', n)), selected: n => tn('files.selected', n),
  clear: t('files.clear'), moveTo: t('files.moveToFolder'), remove: t('files.delete'), removeTitle: n => tn('files.deleteTitle', n), removeText: t('files.deleteText'),
  andMore: n => t('files.andMore', { n }), cancel: t('common.goBack'),
  empty: filter.value.trim() && files.files.length ? t('files.noMatch', { filter: filter.value.trim() }) : t('files.empty'), loading: t('files.loading'),
  nothingSelected: t('files.none'), nothingSelectedText: root.value === 'gcodes' ? t('files.noneHint') : undefined,
  loadFailed: t('files.loadFailed'), retry: t('common.retry'),
}));

// A print file's preview is asked for only once its row is on screen (app/thumbs): the rows are the browser's, found by
// their data-file hook.
const wrap = ref<HTMLElement>();
let unwatch: (() => void)[] = [];
function watchRows() {
  unwatch.forEach(stop => stop()); unwatch = [];
  if (root.value !== 'gcodes') return;
  for (const f of files.files as Listed[]) {
    const el = f.rel && !thumbs.value[f.id] ? wrap.value?.querySelector(`[data-file="${CSS.escape(f.id)}"]`) : null;
    if (el) unwatch.push(watchThumb(el, gen, { path: f.id, thumb: f.rel }, src => { thumbs.value = { ...thumbs.value, [f.id]: src }; }));
  }
}
watch([() => files.files, () => files.loading, filter], () => void nextTick(watchRows), { flush: 'post' });
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
  if (r.ok) void files.reload({ quiet: true });
}

// ---------------------------------------------------------------- folders: a new one, and the open one renamed, moved or deleted
const parentOf = (id: string) => id.slice(0, Math.max(0, id.lastIndexOf('/')));
/** The open folder is somewhere else now (or gone: its parent): open that, and read the tree again. */
function folderNow(id: string) { files.folder = id; files.selected = []; void files.reload(); }
async function mkdir() {
  const n = ((await prompt({ title: t('files.newFolder'), text: t('files.newFolderIn', { path: files.folder }), yes: t('files.create'), no: t('common.goBack'),
    input: { label: t('files.folderName'), value: '' } })) || '').trim();
  if (!n) return;
  const r = await run({ key: 'mkdir', label: t('act.mkdir'), cmd: 'mkdir', args: { path: `${files.folder}/${n}` }, okText: t('ok.mkdir') });
  if (r.ok) void files.reload({ quiet: true });
}
async function renameFolder() {
  const was = files.folder, name = await newName(nameOf(was));
  if (!name) return;
  const r = await run({ key: `ren:${was}`, label: t('act.rename'), cmd: 'rename', args: { path: was, name }, okText: t('ok.rename') });
  if (r.ok) folderNow(r.result?.path ?? `${parentOf(was)}/${name}`);
}
async function moveFolder() {
  const was = files.folder, name = nameOf(was);
  const items = moveTargets(files.folders.filter(f => !f.readonly && rootOf(f.id) === root.value).map(f => f.id), parentOf(was), name)
    .map(f => ({ value: f, label: f === root.value ? t('files.top', { root: rootLabel(root.value) }) : f.slice(root.value.length + 1) }));
  if (!items.length) { tracker.notify('error', t('files.noFolder')); return; }
  const dest = await choose({ title: t('files.move'), text: t('files.moveTo', { name }), choices: items, no: t('common.goBack') });
  if (!dest) return;
  const r = await run({ key: `mv:${was}`, label: t('act.move'), cmd: 'move', args: { path: was, folder: dest }, okText: t('ok.move') });
  if (r.ok) folderNow(r.result?.path ?? `${dest}/${name}`);
}
async function deleteFolder() {
  const was = files.folder;
  if (!await ask({ title: t('files.delete'), text: t('confirm.deleteDir.text', { name: nameOf(was) }), yes: t('confirm.delete.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: `del:${was}`, label: t('act.delete'), cmd: 'delete', args: { path: was, is_dir: true }, okText: t('ok.delete') });
  if (r.ok) folderNow(parentOf(was));
}
</script>
<template>
  <div ref="wrap" class="fv" data-test="files">
    <!-- The printer lists its files newest first; any column can still be sorted. -->
    <OuiFileBrowser v-bind="files.props" :files="shown" :labels="labels" :sort="{ key: 'modified', down: true }" :describedby="root === 'camera' ? 'files-ro' : undefined" v-on="files.on" @open="onOpen">
      <!-- The open folder itself: the tree shows where it is, these act on it. A file root is never renamed, moved or
           deleted, and a read-only folder says so once, here. -->
      <template #folder="{ folder }">
        <template v-if="folder?.readonly"><span id="files-ro" class="oui-chip">{{ t('files.readOnly') }}</span><OuiHint :label="t('files.readOnly')" :text="t('files.readOnlyWhy')" /></template>
        <template v-else-if="folder">
          <template v-if="folder.parent">
            <Button size="small" severity="secondary" text :aria-label="t('files.renameLabel', { name: folder.name })" :title="t('files.renameLabel', { name: folder.name })" data-test="folder-rename" @click="renameFolder"><template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
            <Button size="small" severity="secondary" text :aria-label="t('files.moveLabel', { name: folder.name })" :title="t('files.moveLabel', { name: folder.name })" data-test="folder-move" @click="moveFolder"><template #icon><OuiIcon :icon="moveIcon" :size="14" /></template></Button>
            <Button size="small" severity="danger" outlined :aria-label="t('files.deleteLabel', { name: folder.name })" :title="t('files.deleteLabel', { name: folder.name })" data-test="folder-delete" @click="deleteFolder"><template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
          </template>
          <Button size="small" severity="secondary" text :label="t('files.newFolder')" data-test="files-mkdir" @click="mkdir"><template #icon><OuiIcon :icon="plus" :size="14" /></template></Button>
        </template>
      </template>
      <template #toolbar><InputText id="files-filter" v-model="filter" type="search" size="small" :placeholder="t('files.filter')" :aria-label="t('files.search')" class="fv-q" /></template>
      <template #actions="{ file }">
        <Button v-if="root === 'gcodes'" :label="t('files.print')" :aria-label="t('files.printLabel', { name: file.name })" :disabled="!!s.status?.busy" :aria-describedby="s.status?.busy ? 'heads-why' : undefined" data-test="file-print" @click="print(file.id)">
          <template #icon><OuiIcon :icon="printer" :size="14" /></template></Button>
        <Button severity="secondary" :label="t('files.save')" :aria-label="t('files.saveLabel', { name: file.name })" :loading="tracker.isBusy(`dl:${file.id}`)" data-test="file-save" @click="download(file.id)">
          <template #icon><OuiIcon :icon="downloadIcon" :size="14" /></template></Button>
        <Button v-if="root === 'gcodes'" severity="secondary" text :label="t('files.rename')" :aria-label="t('files.renameLabel', { name: file.name })" data-test="file-rename" @click="rename(file.id)">
          <template #icon><OuiIcon :icon="edit" :size="14" /></template></Button>
      </template>
    </OuiFileBrowser>
  </div>
</template>
<style>
/* The browser fills the window under the bars and leaves the time-lapses' header in sight below it. */
.fv { --oui-files-height: clamp(360px, calc(100vh - 300px), 720px); min-width: 0; }
@supports (height: 100dvh) { .fv { --oui-files-height: clamp(360px, calc(100dvh - 300px), 720px); } }
/* A narrow tab stacks the folders, the list and the details: in a short window they need more than what is left under
   the bars, so the browser keeps 560 px and the page scrolls to the time-lapses. */
@container oui-page (max-width: 660px) { .fv { --oui-files-height: clamp(560px, calc(100vh - 300px), 720px); } }
@supports (height: 100dvh) { @container oui-page (max-width: 660px) { .fv { --oui-files-height: clamp(560px, calc(100dvh - 300px), 720px); } } }
.fv-q { width: 220px; max-width: 100%; }
</style>
