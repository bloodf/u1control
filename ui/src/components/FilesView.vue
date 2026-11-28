<script setup lang="ts">
// The Files tab: the page header, the file browser of the connected printer (a new one for every printer, made the
// first time the tab shows) and the time-lapses under it.
import { ref, watch } from 'vue';
import Button from 'primevue/button';
import { OuiEmpty, OuiIcon, OuiPageHeader, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { refresh } from '@orca-plugins/ui-foundation/src/icons';
import FilesBrowser from './FilesBrowser.vue';
import TimelapsesCard from './TimelapsesCard.vue';
import { s } from '../app/store';
import { t } from '../core/i18n';

const browser = ref<InstanceType<typeof FilesBrowser> | null>(null);
const timelapses = ref<InstanceType<typeof TimelapsesCard> | null>(null);
// One Refresh for the page: the files and the time-lapses under them.
function reload() { void browser.value?.reload(); void timelapses.value?.reload(); }
// Nothing is read from the printer before the tab is looked at; coming back to it reads again.
const seen = ref(s.tab === 'files');
watch(() => s.epoch, () => { seen.value = s.tab === 'files'; });
watch(() => s.tab, tab => { if (tab !== 'files') return; if (seen.value) void browser.value?.reload(); seen.value = true; });
</script>
<template>
  <div class="u1-head">
    <OuiPageHeader :title="t('nav.files')" :meta="browser?.disk">
      <template #actions>
        <Button severity="secondary" :label="t('common.refresh')" :loading="!!browser?.loading || !!timelapses?.loading" :disabled="!browser" data-test="files-refresh" @click="reload">
          <template #icon><OuiIcon :icon="refresh" :size="14" /></template></Button>
      </template>
    </OuiPageHeader>
    <div id="u1-banner-files" />
  </div>
  <FilesBrowser v-if="s.info && seen" ref="browser" :key="s.epoch" />
  <OuiPanel v-else-if="!s.info" flush><OuiEmpty compact state="offline" :title="t('files.noTarget')" /></OuiPanel>
  <TimelapsesCard ref="timelapses" />
</template>
