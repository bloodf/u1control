// Locale resolution, kept free of Vue so the unit tests can import it directly.
export const LOCALES = ['en', 'pt-BR', 'es', 'de', 'zh-CN'] as const;
export type Locale = (typeof LOCALES)[number];
export type LangPref = 'auto' | Locale;

// Language subtag -> the page language that serves it. Every Chinese (zh_CN, zh_TW, zh-Hant…) reads zh-CN:
// OrcaSlicer's Traditional Chinese users get Simplified text rather than English.
const BY_LANGUAGE: Record<string, Locale> = { en: 'en', pt: 'pt-BR', es: 'es', de: 'de', zh: 'zh-CN' };

export const isLocale = (value: unknown): value is Locale => (LOCALES as readonly unknown[]).includes(value);

/** OrcaSlicer's or the browser's code ("pt_BR", "de", "zh_CN", "es-MX") → a page language; anything else → null (caller falls back). */
export function normalizeLocale(value: unknown): Locale | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  return BY_LANGUAGE[value.trim().replace(/_/g, '-').toLowerCase().split('-')[0]] ?? null;
}

/** Explicit choice first, then the host's language, then the browser's, then English. */
export function resolveLocale(pref: LangPref, host: unknown, browser: readonly string[]): Locale {
  if (isLocale(pref)) return pref;
  return normalizeLocale(host) ?? browser.map(normalizeLocale).find((l): l is Locale => !!l) ?? 'en';
}

export function interpolate(text: string, params?: Record<string, unknown>): string {
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (_, k: string) => (k in params ? String(params[k]) : `{${k}}`));
}

/** "<base>_one" for the language's singular, "<base>_other" otherwise (Chinese has no singular form). */
export function pluralKey(locale: Locale, base: string, n: number): string {
  return new Intl.PluralRules(locale).select(n) === 'one' ? `${base}_one` : `${base}_other`;
}

/** Number, date and size formats of one language. Units are SI symbols; hours and minutes are words where the language writes them (texts). */
export function formats(locale: Locale, texts: { hm: string; m: string }) {
  const nf = (x: number, max: number, min = 0) => new Intl.NumberFormat(locale, { maximumFractionDigits: max, minimumFractionDigits: min }).format(x);
  return {
    number: (v: number, digits = 0) => nf(v, digits, digits),
    grams: (v: number | null | undefined) => (v == null ? '? g' : `${nf(Math.round(v), 0)} g`),
    bytes: (b: number | null | undefined) => (b == null ? '' : b > 1e9 ? `${nf(b / 1e9, 1)} GB` : b > 1e6 ? `${nf(b / 1e6, 1)} MB` : `${nf(b / 1e3, 0)} kB`),
    duration(s: number | null | undefined): string {
      if (s == null || !isFinite(s)) return '—';
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return interpolate(h ? texts.hm : texts.m, { h, m });
    },
    dateTime: (unix: number) => new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(unix * 1000)),
    time: (unix: number) => new Intl.DateTimeFormat(locale, { timeStyle: 'short' }).format(new Date(unix * 1000)),
  };
}
