<script setup lang="ts">
// One printer's files: the shared OuiFileBrowser over useFileBackend, which reads, shows a failed read with its way out,
// runs a move or delete and reads again. This component gives the storage (the plugin's Moonraker file commands, with the
// printer's own paths as ids: "gcodes/sub/a.gcode") and what the page adds: print and save a file, on its details and its
// context menu. Naming (a new folder, a rename) is typed in the browser itself; moving and deleting a folder are the
// browser's too (its context menus, and the buttons beside the path). FilesView makes a new one for every printer.
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { fuzzyFilter, OuiFileBrowser, OuiHint, OuiIcon, useFileBackend, type OuiFile, type OuiFileBackend, type OuiFileBrowserLabels, type OuiFileMenuItem } from '@orca-plugins/ui-foundation/src/components';
import { download as downloadIcon, folderMove, printer, rename, trash } from '@orca-plugins/ui-foundation/src/icons';
import * as bridge from '../core/bridge';
import { s, run, tracker, printerName } from '../app/store';
import { newFolder, watchThumb } from '../app/thumbs';
import { ask } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import { fileKind, folderTree, rootOf } from '../core/logic';

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
  // Typed in the browser: it checked the name, opens a new folder and follows a renamed one; a refusal is shown under the name.
  async createFolder(parent, name) {
    const path = `${parent}/${name}`;
    await quiet({ key: 'mkdir', label: t('act.mkdir'), cmd: 'mkdir', args: { path }, okText: t('ok.mkdir') });
    return path;
  },
  rename: async (id, name) => (await quiet({ key: `ren:${id}`, label: t('act.rename'), cmd: 'rename', args: { path: id, name }, okText: t('ok.rename') }))?.path ?? `${parentOf(id)}/${name}`,
  // The browser asked first (its own question, with what goes with the folder); a failure says why itself.
  async moveFolder(id, to) {
    const r = await run({ key: `mv:${id}`, label: t('act.move'), cmd: 'move', args: { path: id, folder: to }, okText: t('ok.move') });
    if (!r.ok) throw new Error(r.reason);
    return r.result?.path ?? `${to}/${nameOf(id)}`;
  },
  async removeFolder(id) { if (!(await run({ key: `del:${id}`, label: t('act.delete'), cmd: 'delete', args: { path: id, is_dir: true }, okText: t('ok.delete') })).ok) throw new Error(id); },
};
/** A command whose failure the name field shows (no toast): rejects with the printer's reason. */
async function quiet(o: Parameters<typeof run>[0]) {
  const r = await run({ ...o, quiet: true });
  if (!r.ok) throw new Error(r.reason === 'error' ? r.error ?? '' : t('msg.unknown', { action: o.label, seconds: 20 }));
  return r.result;
}
const parentOf = (id: string) => id.slice(0, Math.max(0, id.lastIndexOf('/')));
// A file that failed has already said why (each, above): nothing to add here.
const files = useFileBackend(backend, { folder: 'gcodes', onError: () => {} });
defineExpose({ reload: () => files.reload({ quiet: true }), disk, loading: computed(() => files.loading) });
const browser = ref<InstanceType<typeof OuiFileBrowser>>();

const root = computed(() => rootOf(files.folder));
const filter = ref('');
const thumbs = ref<Record<string, string>>({});
watch(() => files.folder, () => { thumbs.value = {}; filter.value = ''; });
// The filter is fuzzy (case, accents and separators do not matter; the letters in order): best match first, matches marked.
const ranked = computed(() => !!filter.value.trim());
// The kind tag only tells files apart in a folder that holds more than one kind (print files are all G-code).
const mixed = computed(() => new Set((files.files as Listed[]).map(f => fileKind(f.name))).size > 1);
const shown = computed<OuiFile[]>(() => {
  const found = ranked.value ? fuzzyFilter(files.files as Listed[], filter.value, f => f.name) : (files.files as Listed[]).map(item => ({ item, match: null }));
  return found.map(({ item: f, match }) => ({ match: match?.hits,
    id: f.id, name: f.name, size: f.size, sizeText: fmt.bytes(f.size) || undefined, modified: f.modified, modifiedText: f.modified ? fmt.dateTime(f.modified) : undefined,
    kind: mixed.value ? fileKind(f.name) : undefined, thumb: thumbs.value[f.id] ?? null,
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
  newFolder: t('files.newFolder'), folderName: t('files.newName'), folderError: reason => t(`files.nameErr.${reason}` as const),
  rename: t('files.rename'), move: t('files.move'), moveTitle: () => t('files.moveToFolder'), removeFolderTitle: name => t('confirm.deleteDir.text', { name }), removeFolderText: t('files.deleteText'),
  listView: t('files.view.list'), gridView: t('files.view.grid'), refresh: t('common.refresh'),
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
// The grid draws new elements for the same files: their pictures are watched again.
const onView = () => void nextTick(watchRows);
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
// A file's (the selection's) context menu starts with what the page adds: print it, save it.
const fileMenu = (ids: string[]): OuiFileMenuItem[] => ids.length !== 1 ? [] : [
  ...(root.value === 'gcodes' ? [{ label: t('files.print'), icon: printer, disabled: !!s.status?.busy, run: () => void print(ids[0]) }] : []),
  { label: t('files.save'), icon: downloadIcon, run: () => void download(ids[0]) }];
</script>
<template>
  <div ref="wrap" class="fv" data-test="files">
    <!-- The printer lists its files newest first; any column can still be sorted. -->
    <OuiFileBrowser ref="browser" v-bind="files.props" :files="shown" :ranked="ranked" :labels="labels" :sort="{ key: 'modified', down: true }" :describedby="root === 'camera' ? 'files-ro' : undefined"
      :file-menu="fileMenu" view-key="u1control" v-on="files.on" @open="onOpen" @update:view="onView">
      <!-- The open folder itself: the tree shows where it is, these act on it. A file root is never renamed, moved or
           deleted, and a read-only folder says so once, here. -->
      <template #folder="{ folder }">
        <template v-if="folder?.readonly"><span id="files-ro" class="oui-chip">{{ t('files.readOnly') }}</span><OuiHint :label="t('files.readOnly')" :text="t('files.readOnlyWhy')" /></template>
        <template v-else-if="folder">
          <template v-if="folder.parent">
            <Button size="small" severity="secondary" text :aria-label="t('files.renameLabel', { name: folder.name })" :title="t('files.renameLabel', { name: folder.name })" data-test="folder-rename" @click="browser?.rename(folder.id)"><template #icon><OuiIcon :icon="rename" :size="16" /></template></Button>
            <Button size="small" severity="secondary" text :aria-label="t('files.moveLabel', { name: folder.name })" :title="t('files.moveLabel', { name: folder.name })" data-test="folder-move" @click="browser?.moveFolder(folder.id)"><template #icon><OuiIcon :icon="folderMove" :size="16" /></template></Button>
            <Button size="small" severity="danger" text :aria-label="t('files.deleteLabel', { name: folder.name })" :title="t('files.deleteLabel', { name: folder.name })" data-test="folder-delete" @click="browser?.deleteFolder(folder.id)"><template #icon><OuiIcon :icon="trash" :size="16" /></template></Button>
          </template>
        </template>
      </template>
      <template #toolbar><InputText id="files-filter" v-model="filter" type="search" size="small" :placeholder="t('files.filter')" :aria-label="t('files.search')" class="fv-q" /></template>
      <template #actions="{ file }">
        <Button v-if="root === 'gcodes'" :label="t('files.print')" :aria-label="t('files.printLabel', { name: file.name })" :disabled="!!s.status?.busy" :aria-describedby="s.status?.busy ? 'heads-why' : undefined" data-test="file-print" @click="print(file.id)">
          <template #icon><OuiIcon :icon="printer" :size="14" /></template></Button>
        <Button severity="secondary" :label="t('files.save')" :aria-label="t('files.saveLabel', { name: file.name })" :loading="tracker.isBusy(`dl:${file.id}`)" data-test="file-save" @click="download(file.id)">
          <template #icon><OuiIcon :icon="downloadIcon" :size="14" /></template></Button>
        <Button v-if="root === 'gcodes'" severity="secondary" text :label="t('files.rename')" :aria-label="t('files.renameLabel', { name: file.name })" data-test="file-rename" @click="browser?.rename(file.id)">
          <template #icon><OuiIcon :icon="rename" :size="14" /></template></Button>
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
