<script setup lang="ts">
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { dialog, close, restoreFocus } from '../core/dialog';
import { t } from '../core/i18n';

// Every protected decision of the page: a question with both answers named, a question with a field (rename, a
// firmware input) or a list to pick from (move). Focus starts on the way back, or in the field, never on the action.
// foundation-gap: OuiConfirm (5.0.7) has two buttons and no field or choice list, so this stays a PrimeVue Dialog with
// OuiConfirm's hooks (data-dlg yes/no). The file browser's own delete question is OuiConfirm's.
function onVisible(v: boolean) { if (!v) close(dialog.cancelValue); }
function confirm() { close(dialog.input ? dialog.inputValue : true); }
</script>
<template>
  <Dialog :visible="dialog.visible" modal :header="dialog.title" :closable="true" :draggable="false"
          :style="{ width: 'min(440px, calc(100vw - 32px))' }" :close-button-props="{ severity: 'secondary', text: true, rounded: true, 'aria-label': t('common.close') }"
          @update:visible="onVisible" @after-hide="restoreFocus">
    <p class="dlg-text">{{ dialog.text }}</p>
    <form v-if="dialog.input" class="oui-field" @submit.prevent="confirm">
      <label for="dlg-input">{{ dialog.input.label }}</label>
      <InputText id="dlg-input" v-model="dialog.inputValue" :placeholder="dialog.input.placeholder" autofocus />
    </form>
    <ul v-if="dialog.choices" class="dlg-choices" role="list">
      <li v-for="c in dialog.choices" :key="c.value">
        <Button severity="secondary" class="dlg-choice" :label="c.label" @click="close(c.value)" />
      </li>
    </ul>
    <template #footer>
      <Button :label="dialog.no ?? t('common.goBack')" severity="secondary" :autofocus="!dialog.input" data-dlg="no" @click="close(dialog.cancelValue)" />
      <Button v-if="!dialog.choices" :label="dialog.yes ?? t('common.ok')" :severity="dialog.danger ? 'danger' : undefined" data-dlg="yes"
              :disabled="!!dialog.input && !dialog.inputValue.trim()" @click="confirm" />
    </template>
  </Dialog>
</template>
<style>
.dlg-text { white-space: pre-line; margin-bottom: var(--oui-s3); }
.dlg-choices { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--oui-s2); max-height: 300px; overflow: auto; }
.dlg-choice { width: 100%; justify-content: flex-start; }
</style>
