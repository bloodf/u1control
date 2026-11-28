<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiMenu, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { download as downloadIcon, refresh, trash, video } from '@orca-plugins/ui-foundation/src/icons';
import TimelapseCover from './TimelapseCover.vue';
import * as bridge from '../core/bridge';
import { s, run, tracker, targetKnown } from '../app/store';
import { covers } from '../app/thumbs';
import { ask } from '../core/dialog';
import { t, tn, fmt } from '../core/i18n';
import { message } from '../core/tracker';

// The U1's time-lapse videos (cmd_timelapses: one row per video, paired with its cover by the plugin). Saving goes
// to the computer's Downloads folder like every other printer file; deleting takes the video and its pictures and
// always asks first. Neither touches motion, so both stay on while the U1 prints.
interface Video { path: string; file: string; name: string; size?: number | null; modified?: number | null; cover?: string | null }
const state = ref<'idle' | 'loading' | 'ok' | 'error'>('idle');
const error = ref('');
const videos = ref<Video[]>([]);
const supported = ref(true);
const coverGen = ref(covers.reset());
let asked = 0;
const saveKey = (v: Video) => `tl-dl:${v.path}`;
const delKey = (v: Video) => `tl-del:${v.path}`;
const when = (v: Video) => (v.modified ? fmt.dateTime(v.modified) : '');

async function load() {
  const mine = ++asked;
  if (!targetKnown.value || !s.info) { state.value = 'idle'; videos.value = []; return; }
  state.value = 'loading';
  try {
    const r = await bridge.command('timelapses', {}, s.info.generation);
    if (mine !== asked) return;
    videos.value = r.videos ?? []; supported.value = r.supported !== false;
    state.value = 'ok';
  } catch (e) {
    if (mine !== asked) return;
    error.value = message(e); state.value = 'error';
  }
}
let shownEpoch = s.epoch;
watch(() => [s.tab, s.epoch, s.phase], () => {
  // Another printer: none of the old rows or covers, and an answer still on its way for the old one is dropped.
  if (s.epoch !== shownEpoch) { shownEpoch = s.epoch; asked++; state.value = 'idle'; videos.value = []; coverGen.value = covers.reset(); }
  // Only a connected printer is asked: a drop to unreachable keeps the rows instead of an error panel.
  if (s.tab === 'files' && s.phase === 'connected') void load();
}, { immediate: true });

async function save(v: Video) {
  const r = await run({ key: saveKey(v), label: t('act.download'), cmd: 'download', args: { path: v.path }, timeoutMs: 120000 });
  if (r.ok) tracker.notify('success', t('ok.saved', { path: r.result }));
}
async function del(v: Video) {
  if (!await ask({ title: t('files.delete'), text: t('confirm.timelapseDelete.text', { name: v.file }), yes: t('confirm.delete.yes'), no: t('common.goBack'), danger: true })) return;
  const r = await run({ key: delKey(v), label: t('act.timelapseDelete'), cmd: 'timelapse_delete', args: { path: v.path }, okText: t('ok.delete') });
  if (!r.ok && r.reason === 'busy') return;
  await load();   // also after a failure: some of its pictures may be gone
  await nextTick();
  // Delete was off while it ran, so the focus fell to the page: it goes back to the row's Delete when the video is
  // still there (a failure), else to the next video's Delete, else to the page's Refresh, never to the top of the page.
  if (document.activeElement !== document.body) return;
  (document.querySelector<HTMLElement>(`[data-timelapse="${CSS.escape(v.path)}"] .tl-del`) ?? document.querySelector<HTMLElement>('[data-timelapse] .tl-del')
    ?? document.querySelector<HTMLElement>('[data-test="files-refresh"]'))?.focus();
}
// A time-lapse's context menu: what its row's buttons do.
const menu = ref<InstanceType<typeof OuiMenu>>();
// The page's Refresh reads the time-lapses again too (FilesView).
defineExpose({ reload: load, loading: computed(() => state.value === 'loading') });
const rowMenu = (event: MouseEvent, v: Video) => menu.value?.open(event, [
  { label: t('files.save'), icon: downloadIcon, id: 'save', disabled: tracker.isBusy(saveKey(v)) || tracker.isBusy(delKey(v)), run: () => void save(v) },
  { label: t('files.delete'), icon: trash, id: 'delete', danger: true, disabled: tracker.isBusy(saveKey(v)) || tracker.isBusy(delKey(v)), run: () => void del(v) }]);
</script>
<template>
  <OuiPanel :icon="video" tone="sky" flush aria-labelledby="timelapses-h" data-test="timelapses">
    <template #title><span id="timelapses-h">{{ t('tl.title') }}</span></template>
    <template #meta>{{ state !== 'error' && videos.length ? tn('tl.count', videos.length) : '' }}</template>
    <OuiEmpty v-if="!targetKnown" compact state="offline" :title="t('tl.noTarget')" />
    <OuiEmpty v-else-if="state === 'error'" compact state="error" :title="t('tl.error', { error })">
      <template #actions><Button size="small" severity="secondary" :label="t('common.retry')" @click="load"><template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button></template>
    </OuiEmpty>
    <div v-else-if="videos.length" class="oui-table-wrap">
      <table class="u1-table tl-table">
        <thead><tr><th scope="col" class="tl-cover-col"><span class="oui-sr">{{ t('tl.col.cover') }}</span></th><th scope="col">{{ t('files.col.name') }}</th>
          <th scope="col" class="tl-wide">{{ t('tl.col.date') }}</th><th scope="col" class="tl-wide oui-num">{{ t('files.col.size') }}</th>
          <th scope="col" class="oui-end"><span class="oui-sr">{{ t('files.col.actions') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="v in videos" :key="`${v.path}|${v.cover ?? ''}`" :data-timelapse="v.path" @contextmenu="rowMenu($event, v)">
            <td class="tl-cover-col"><TimelapseCover :gen="coverGen" :path="v.cover" /></td>
            <td :title="v.file"><div class="tl-name oui-strong">{{ v.name }}</div>
              <div class="tl-narrow oui-meta">{{ [when(v), fmt.bytes(v.size)].filter(Boolean).join(' · ') }}</div></td>
            <td class="tl-wide tl-date">{{ when(v) }}</td>
            <td class="tl-wide oui-num">{{ fmt.bytes(v.size) }}</td>
            <td class="oui-end"><div class="tl-acts">
              <Button size="small" severity="secondary" :label="t('files.save')" :aria-label="t('tl.saveLabel', { name: v.file })" :loading="tracker.isBusy(saveKey(v))"
                      :disabled="tracker.isBusy(delKey(v))" @click="save(v)"><template #icon><OuiIcon :icon="downloadIcon" :size="14" /></template></Button>
              <Button size="small" severity="danger" outlined class="tl-del" :aria-label="t('tl.deleteLabel', { name: v.file })" :title="t('files.delete')" :loading="tracker.isBusy(delKey(v))"
                      :disabled="tracker.isBusy(saveKey(v))" @click="del(v)"><template #icon><OuiIcon :icon="trash" :size="14" /></template></Button>
            </div></td>
          </tr>
        </tbody>
      </table>
    </div>
    <OuiEmpty v-else-if="state === 'loading'" compact state="loading" :title="t('tl.loading')" role="status" />
    <OuiEmpty v-else-if="state === 'ok' && !supported" compact tone="sky" :icon="video" :title="t('tl.unsupported')" :text="t('tl.unsupportedHint')" />
    <OuiEmpty v-else-if="state === 'ok'" compact tone="sky" :icon="video" :title="t('tl.empty')" :text="t('tl.emptyHint')" />
    <OuiMenu ref="menu" />
  </OuiPanel>
</template>
<style>
.tl-cover-col { width: 120px; }
.tl-name { overflow-wrap: anywhere; }
.tl-date { white-space: nowrap; }
/* Delete is the destructive one: a red outline, last and a gap away from Save. It always asks first. */
.tl-acts { display: inline-flex; align-items: center; justify-content: flex-end; gap: var(--oui-s1); white-space: nowrap; }
.tl-del { margin-inline-start: var(--oui-s3); }
/* A narrow tab: the date and the size move under the name and the cover shrinks, so the name keeps its room and
   Save and Delete stay on screen. Only one of the two places is ever rendered, also for a screen reader. */
.tl-narrow { display: none; }
@container oui-page (max-width: 720px) {
  .tl-table .tl-wide { display: none; }
  .tl-narrow { display: block; }
  .tl-cover-col { width: 88px; }
  .tl-cover, .tl-cover > img { width: 64px; height: 36px; }
}
</style>
