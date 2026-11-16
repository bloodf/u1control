// Five complete dictionaries with the same placeholders, plural pairs and the number/date/duration formats.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { en, ptBR } from '../../src/core/messages.ts';
import { es } from '../../src/core/messages-es.ts';
import { de } from '../../src/core/messages-de.ts';
import { zhCN } from '../../src/core/messages-zh.ts';
import { formats, pluralKey, LOCALES, type Locale } from '../../src/core/i18n-core.ts';

const DICTS: Record<Locale, Record<string, string>> = { en, 'pt-BR': ptBR, es, de, 'zh-CN': zhCN };
const holes = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();

test('every language has every key, no extra key, no empty text', () => {
  const keys = Object.keys(en).sort();
  for (const l of LOCALES) {
    assert.deepEqual(Object.keys(DICTS[l]).sort(), keys, l);
    for (const k of keys) assert.ok(DICTS[l][k].trim(), `${l} ${k} empty`);
  }
});

test('every translation keeps the English placeholders', () => {
  for (const l of LOCALES) for (const [k, v] of Object.entries(en)) assert.deepEqual(holes(DICTS[l][k]), holes(v), `${l} ${k}`);
});

test('new languages are really translated (most texts differ from English)', () => {
  for (const l of ['es', 'de', 'zh-CN'] as const) {
    const same = Object.keys(en).filter(k => DICTS[l][k] === (en as Record<string, string>)[k] && /[a-z]{4}/.test(DICTS[l][k]));
    assert.ok(same.length < Object.keys(en).length * 0.05, `${l}: ${same.length} same as English: ${same.slice(0, 20).join(', ')}`);
  }
  for (const v of Object.values(zhCN)) assert.ok(!/[一-鿿][,:;!?]/.test(v), 'Chinese punctuation after Chinese text: ' + v);
});

test('plural keys exist in pairs; Chinese uses the "other" form', () => {
  const bases = Object.keys(en).filter(k => k.endsWith('_one')).map(k => k.slice(0, -4));
  assert.ok(bases.length > 0);
  for (const b of bases) assert.ok(`${b}_other` in en, b);
  assert.equal(pluralKey('en', 'x', 1), 'x_one'); assert.equal(pluralKey('de', 'x', 2), 'x_other');
  assert.equal(pluralKey('es', 'x', 1), 'x_one'); assert.equal(pluralKey('zh-CN', 'x', 1), 'x_other');
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
  assert.match(f('de').dateTime(day), /16\.11\.26/); assert.match(f('zh-CN').dateTime(day), /2026\/11\/16/);
});
