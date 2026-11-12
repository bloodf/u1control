import { computed, reactive, ref } from 'vue';
import * as bridge from '../core/bridge';
import { message } from '../core/tracker';
import { t, onLangPref } from '../core/i18n';
import { hello, onConfig, onRfid, tracker } from './store';
import type { Config } from './types';

// Settings form: a config message from the plugin never wipes values the user is still editing; "Saved" only
// once the plugin answered; on an error the typed values stay.
export const config = ref<Config | null>(null);
export const form = reactive({ mode: 'automagic', host: '', apiKey: '', name: 'Snapmaker U1', spoolman: '', draft: {} as Record<string, unknown> });
export const saving = ref(false);
let rfidAuto = false;

const savedExpert = (k: string) => (config.value ? (k in config.value.stored ? config.value.stored[k] : config.value.settings[k]) : undefined);
export const valueOf = (key: string) => (key in form.draft ? form.draft[key] : savedExpert(key));
export const dirty = computed(() => {
  const c = config.value;
  if (!c) return false;
  const st = c.settings;
  return form.mode !== c.mode || Object.entries(form.draft).some(([k, v]) => v !== savedExpert(k)) || form.apiKey !== (st.api_key || '')
    || form.host.trim() !== (st.host || '') || form.name.trim() !== (st.printer_name || 'Snapmaker U1') || form.spoolman.trim() !== (st.spoolman_url || '');
});

function fill(m: Config): void {
  const keep = !saving.value && dirty.value;
  config.value = m;
  rfidAuto = !!m.settings.rfid_auto_sync;
  if (keep) return;
  const st = m.settings;
  Object.assign(form, { mode: m.mode, host: st.host || '', apiKey: st.api_key || '', name: st.printer_name || 'Snapmaker U1', spoolman: st.spoolman_url || '', draft: {} });
}

export async function save(): Promise<void> {
  const c = config.value;
  if (!c || saving.value) return;
  const settings: Record<string, unknown> = {
    mode: form.mode, host: form.host.trim(), printer_name: form.name.trim() || 'Snapmaker U1', spoolman_url: form.spoolman.trim(),
    ...Object.fromEntries(Object.entries(form.draft).filter(([k, v]) => form.mode === 'expert' || v !== savedExpert(k))),
  };
  if (form.apiKey !== '••••') settings.api_key = form.apiKey.trim();
  saving.value = true;
  try {
    const r = await bridge.request({ type: 'save_settings', settings });
    form.draft = {};
    if (r?.connect_error) tracker.notify('error', t('settings.savedBut', { error: r.connect_error }));
    else tracker.notify('success', t('ok.settings'));
    void hello();
  } catch (e) {
    tracker.notify('error', t('settings.notSaved', { error: message(e) }));
  } finally {
    saving.value = false;
  }
}

export function installSettings(): () => void {
  onLangPref(value => bridge.post({ type: 'ui_language', value }));
  const a = onConfig(fill);
  const b = onRfid(m => {
    if (rfidAuto) { bridge.post({ type: 'sync_project', auto: true }); return; }
    const names = (m.heads as number[]).map(i => {
      const g = m.tags[i] ?? {};
      return `T${i + 1} ${[g.vendor || g.manufacturer, g.type, g.sub_type].filter(Boolean).join(' ')}`;
    });
    tracker.notify('info', t('ok.rfidRead', { names: names.join(', ') }));
  });
  return () => { a(); b(); };
}
