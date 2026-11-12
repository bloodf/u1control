import { createApp, watch } from 'vue';
import { installOrcaUI } from '../shared/src';
import { boot } from './core/boot';
import { locale, setHostLanguage } from './core/i18n';
import { followHostTheme } from './core/theme';
import { primeVueOptions } from '../shared/src';
import App from './App.vue';
import SetupApp from './setup/SetupApp.vue';

document.body.classList.add('orca-ui');
setHostLanguage(boot.lang);
followHostTheme();
const app = createApp(boot.mode === 'setup' ? SetupApp : App);
installOrcaUI(app, 'en');
// PrimeVue's own labels (dialog close, select filter…) follow the page language too.
const prime = app.config.globalProperties.$primevue;
const english = { ...prime.config.locale };
watch(locale, l => {
  document.documentElement.lang = l;
  prime.config.locale = { ...english, ...(primeVueOptions(l).locale ?? {}) } as NonNullable<typeof prime.config.locale>;
}, { immediate: true });
app.mount('#app');
