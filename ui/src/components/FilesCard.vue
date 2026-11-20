<script setup lang="ts">
import Button from 'primevue/button';
import { OuiIcon, OuiPanel } from '@orca-plugins/ui-foundation/src/components';
import { files } from '@orca-plugins/ui-foundation/src/icons';
import { s } from '../app/store';
import { t } from '../core/i18n';

// A shortcut widget: the Files tab, one press from the dashboard.
</script>
<template>
  <OuiPanel :icon="files" :title="t('nav.files')" data-test="files-card">
    <div class="oui-row u1-files-card">
      <p class="oui-meta">{{ t('widget.files') }}</p>
      <Button severity="secondary" size="small" :label="t('widget.openFiles')" data-test="open-files" @click="s.tab = 'files'">
        <template #icon><OuiIcon :icon="files" :size="14" /></template></Button>
    </div>
  </OuiPanel>
</template>
<style>
.u1-files-card { justify-content: space-between; }
.u1-files-card > .oui-meta { flex: 1 1 180px; margin: 0; }
</style>
