// Seven complete dictionaries (Polish adds "_few" / "_many" plural forms, Czech "_few") with the same placeholders, plural pairs and the number/date/duration formats.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { en, ptBR } from '../../src/core/messages.ts';
import { es } from '../../src/core/messages-es.ts';
import { de } from '../../src/core/messages-de.ts';
import { zhCN } from '../../src/core/messages-zh.ts';
import { pl } from '../../src/core/messages-pl.ts';
import { cs } from '../../src/core/messages-cs.ts';
import { formats, pluralKey, LOCALES, type Locale } from '../../src/core/i18n-core.ts';

const DICTS: Record<Locale, Record<string, string>> = { en, 'pt-BR': ptBR, es, de, 'zh-CN': zhCN, pl, cs };
const holes = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();

test('every language has every key, no extra key, no empty text', () => {
  const keys = Object.keys(en).sort();
  // Polish adds "_few" and "_many" next to every "_one" / "_other" pair
  const plural = Object.keys(en).filter(k => k.endsWith('_one')).flatMap(k => [k.replace(/_one$/, '_few'), k.replace(/_one$/, '_many')]);
  for (const l of LOCALES) {
    const extra = l === 'pl' ? plural : l === 'cs' ? plural.filter(k => k.endsWith('_few')) : [];
    assert.deepEqual(Object.keys(DICTS[l]).sort(), [...keys, ...extra].sort(), l);
    for (const k of extra) assert.deepEqual(holes(DICTS[l][k]), holes((en as Record<string, string>)[k.replace(/_(few|many)$/, '_other')]), `${l} ${k}`);
    for (const k of keys) assert.ok(DICTS[l][k].trim(), `${l} ${k} empty`);
  }
});

test('every translation keeps the English placeholders', () => {
  for (const l of LOCALES) for (const [k, v] of Object.entries(en)) assert.deepEqual(holes(DICTS[l][k]), holes(v), `${l} ${k}`);
});

test('new languages are really translated (most texts differ from English)', () => {
  for (const l of ['es', 'de', 'zh-CN', 'pl', 'cs'] as const) {
    const same = Object.keys(en).filter(k => DICTS[l][k] === (en as Record<string, string>)[k] && /[a-z]{4}/.test(DICTS[l][k]));
    assert.ok(same.length < Object.keys(en).length * 0.05, `${l}: ${same.length} same as English: ${same.slice(0, 20).join(', ')}`);
  }
  for (const v of Object.values(zhCN)) assert.ok(!/[一-鿿][,:;!?]/.test(v), 'Chinese punctuation after Chinese text: ' + v);
});

test('plural keys exist in pairs; Chinese uses the "other" form', () => {
  const bases = Object.keys(en).filter(k => k.endsWith('_one')).map(k => k.slice(0, -4));
  assert.ok(bases.length > 0);
  for (const b of bases) assert.ok(`${b}_other` in en, b);
  assert.equal(pluralKey('pt-BR', 'x', 0), 'x_other', 'Portuguese 0 is "one" by CLDR, but "_one" says 1'); assert.equal(pluralKey('pt-BR', 'x', 1), 'x_one');
  assert.equal(pluralKey('en', 'x', 1), 'x_one'); assert.equal(pluralKey('de', 'x', 2), 'x_other');
  assert.equal(pluralKey('es', 'x', 1), 'x_one'); assert.equal(pluralKey('zh-CN', 'x', 1), 'x_other');
});

test('Polish plurals: one, few and many by Intl.PluralRules(\'pl\')', () => {
  const dict = pl as Record<string, string>;
  const say = (base: string, n: number) => dict[pluralKey('pl', base, n, dict)].replace('{n}', String(n));
  assert.equal(say('tl.count', 1), '1 nagranie');
  assert.equal(say('tl.count', 2), '2 nagrania');
  assert.equal(say('tl.count', 5), '5 nagrań');
  assert.equal(say('tl.count', 12), '12 nagrań');
  assert.equal(say('tl.count', 22), '22 nagrania');
  assert.equal(say('setup.sendWarn', 22), 'Wyślij do U1 z 22 ostrzeżeniami');
  assert.equal(say('usage.count', 0), '0 niepotwierdzonych zużyć');
  // a dictionary without the extra forms keeps its one/other pair
  assert.equal(pluralKey('pl', 'tl.count', 5), 'tl.count_other');
  assert.equal(pluralKey('de', 'tl.count', 1, de as Record<string, string>), 'tl.count_one');
});

test('Czech plurals: one, few and other by Intl.PluralRules(\'cs\')', () => {
  const dict = cs as Record<string, string>;
  const say = (base: string, n: number) => dict[pluralKey('cs', base, n, dict)].replace('{n}', String(n));
  assert.equal(say('tl.count', 1), '1 video');
  assert.equal(say('tl.count', 3), '3 videa');
  assert.equal(say('tl.count', 5), '5 videí');
  assert.equal(say('files.count', 22), '22 souborů');
  assert.equal(say('setup.layers', 4), '4 vrstvy');
});

test('numbers, sizes, durations and dates follow the language', () => {
  const f = (l: Locale) => formats(l, { hm: DICTS[l]['dur.hm'], m: DICTS[l]['dur.m'] });
  assert.equal(f('de').number(1234.5, 1), '1.234,5'); assert.equal(f('en').number(1234.5, 1), '1,234.5');
  assert.equal(f('es').number(0.5, 1), '0,5');
  assert.equal(f('de').grams(1234.4), '1.234 g'); assert.equal(f('zh-CN').grams(null), '? g');
  assert.equal(f('de').bytes(2_500_000), '2,5 MB'); assert.equal(f('en').bytes(2_500_000_000), '2.5 GB');
  assert.equal(f('zh-CN').duration(3900), '1 小时 5 分钟'); assert.equal(f('de').duration(300), '5 min');
  assert.equal(f('es').duration(null), '—');
  const day = Date.UTC(2026, 10, 16, 12) / 1000;
  assert.match(f('de').dateTime(day), /16\.11\.26/); assert.match(f('pl').dateTime(day), /16\.11\.2026/);
  assert.equal(f('pl').number(1234.5, 1), '1234,5'); assert.equal(f('pl').duration(3900), '1 h 5 min');
  const at = Date.UTC(2026, 10, 16, 14, 30) / 1000, local = new Date(at * 1000);
  const h24 = `${local.getHours()}:${String(local.getMinutes()).padStart(2, '0')}`;
  assert.match(formats('en', { hm: '', m: '' }, '24').time(at), new RegExp(`^0?${h24}$`));   // Settings > Language > Clock
  assert.match(formats('de', { hm: '', m: '' }, '12').time(at), /AM|PM|vorm|nachm/i);
  assert.equal(formats('en', { hm: '', m: '' }, 'auto').time(at), formats('en', { hm: '', m: '' }).time(at));
  assert.match(f('cs').number(1234.5, 1), /^1\s234,5$/); assert.match(f('cs').dateTime(day), /16\.\s?11\.\s?26/); assert.match(f('zh-CN').dateTime(day), /2026\/11\/16/);
});
