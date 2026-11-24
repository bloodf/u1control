import { computed, ref } from 'vue';
import { en, ptBR, type MessageKey } from './messages';
import { es } from './messages-es';
import { de } from './messages-de';
import { zhCN } from './messages-zh';
import { pl } from './messages-pl';
import { cs } from './messages-cs';
import { formats, interpolate, isClock, isLocale, pluralKey, resolveLocale, type ClockPref, type LangPref, type Locale } from './i18n-core';
import { boot } from './boot';

const PREF_KEY = 'u1control.lang';
const dicts: Record<Locale, Record<MessageKey, string>> = { en, 'pt-BR': ptBR, es, de, 'zh-CN': zhCN, pl, cs };

// The explicit choice lives in the plugin's settings (boot "pref"); localStorage is only a fallback cache.
let persist: (value: LangPref) => void = () => {};
export function onLangPref(fn: (value: LangPref) => void): void { persist = fn; }
function readPref(): LangPref {
  const fromHost = (boot as { pref?: unknown }).pref;
  if (isLocale(fromHost)) return fromHost;
  if (fromHost === 'auto') return 'auto';
  try {
    const v = localStorage.getItem(PREF_KEY);
    return isLocale(v) ? v : 'auto';
  } catch { return 'auto'; }
}

export const langPref = ref<LangPref>(readPref());
const hostLang = ref<unknown>(null);
export const locale = computed<Locale>(() => resolveLocale(langPref.value, hostLang.value, navigator.languages ?? [navigator.language]));
export const autoLocale = computed<Locale>(() => resolveLocale('auto', hostLang.value, navigator.languages ?? [navigator.language]));

export function setHostLanguage(value: unknown): void { hostLang.value = value; }
export function setLangPref(value: LangPref): void {
  langPref.value = value;
  persist(value);
  try { if (value === 'auto') localStorage.removeItem(PREF_KEY); else localStorage.setItem(PREF_KEY, value); } catch { /* per-viewer only */ }
}

export function t(key: MessageKey, params?: Record<string, unknown>): string {
  return interpolate(dicts[locale.value][key] ?? en[key] ?? key, params);
}
/** Plural keys come in pairs "<base>_one" / "<base>_other"; Polish adds "_few" and "_many", Czech "_few". */
export function tn(base: string, n: number, params?: Record<string, unknown>): string {
  return t(pluralKey(locale.value, base, n, dicts[locale.value]) as MessageKey, { n, ...params });
}
/** A message key when it exists (state names, codes from Python); otherwise the raw value. */
export function tMaybe(key: string, fallback: string, params?: Record<string, unknown>): string {
  return key in en ? t(key as MessageKey, params) : fallback;
}

// Settings > Language "Clock": the choice lives in the plugin's settings (boot "clock"), 'auto' = the language's usual clock.
export const clockPref = ref<ClockPref>(isClock((boot as { clock?: unknown }).clock) ? (boot as { clock: ClockPref }).clock : 'auto');
let persistClock: (value: ClockPref) => void = () => {};
export function onClockPref(fn: (value: ClockPref) => void): void { persistClock = fn; }
export function setClockPref(value: ClockPref): void {
  if (!isClock(value)) return;
  clockPref.value = value;
  persistClock(value);
}

const f = computed(() => formats(locale.value, { hm: t('dur.hm'), m: t('dur.m') }, clockPref.value));
export const fmt = {
  number: (v: number, digits = 0) => f.value.number(v, digits),
  grams: (v: number | null | undefined) => f.value.grams(v),
  bytes: (b: number | null | undefined) => f.value.bytes(b),
  duration: (s: number | null | undefined) => f.value.duration(s),
  dateTime: (unix: number) => f.value.dateTime(unix),
  time: (unix: number) => f.value.time(unix),
  ago(unix: number | null | undefined, now = Date.now() / 1000): string {
    if (unix == null) return '';
    const s = Math.max(0, Math.round(now - unix));
    return s < 60 ? t('age.seconds', { n: s }) : s < 3600 ? t('age.minutes', { n: Math.round(s / 60) }) : t('age.at', { time: fmt.time(unix) });
  },
};
