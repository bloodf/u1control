// Pure rules of the page (node --test runs this TypeScript directly).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTarget, parseSpeed, heaterPhase, setupWarnings, warningKey, moveTargets, boundHeads, family, overEnglish } from '../../src/core/logic.ts';
import { normalizeLocale, resolveLocale, interpolate } from '../../src/core/i18n-core.ts';

test('a blank target is never 0; 0 typed is Off; out of range refused (U02/B-09)', () => {
  assert.deepEqual(parseTarget('', 320), { kind: 'empty' });
  assert.deepEqual(parseTarget(null, 320), { kind: 'empty' });
  assert.deepEqual(parseTarget(0, 320), { kind: 'off' });
  assert.deepEqual(parseTarget('215,4', 320), { kind: 'heat', value: 215 });
  assert.deepEqual(parseTarget(999, 320), { kind: 'invalid' });
  assert.deepEqual(parseTarget(111, 110), { kind: 'invalid' });
  assert.deepEqual(parseTarget(-1, 320), { kind: 'invalid' });
  assert.deepEqual(parseTarget('abc', 320), { kind: 'invalid' });
  assert.equal(parseSpeed(''), null); assert.equal(parseSpeed(5), null); assert.equal(parseSpeed(120), 120);
});

test('heater phase: an unknown reading or target is never given a phase; target 0 is off', () => {
  assert.equal(heaterPhase(219.6, 220), 'target');
  assert.equal(heaterPhase(131, 240), 'heating');
  assert.equal(heaterPhase(250, 220), 'cooling');
  assert.equal(heaterPhase(60, 0), 'off');
  assert.equal(heaterPhase(null, 0), 'off');
  assert.equal(heaterPhase(null, 220), null);
  assert.equal(heaterPhase(25, null), null);
  assert.equal(heaterPhase(25, undefined), null);
});

test('setup warnings: ids, order and the empty-before-material rule', () => {
  const heads = [0, 1, 2, 3].map(i => ({ index: i, loaded: i !== 2, type: i === 3 ? 'PETG-CF' : 'PLA' }));
  const fils = [{ index: 1, type: 'PETG' }, { index: 0, type: 'PLA+' }];
  const w = setupWarnings(fils, heads, { 0: 2, 1: 1 });
  assert.equal(warningKey(w), 'empty:0:2,material:1:1');
  assert.deepEqual(setupWarnings(fils, heads, { 0: 0, 1: 3 }), []);   // PLA+ ~ PLA, PETG ~ PETG-CF (family)
  assert.equal(family('PA-CF'), 'PA');
});

test('move targets exclude the current folder, the item and its subfolders', () => {
  assert.deepEqual(moveTargets(['gcodes', 'gcodes/a', 'gcodes/a/b', 'gcodes/c'], 'gcodes', 'a'), ['gcodes/c']);
  assert.deepEqual(boundHeads({}, { 0: 7 }), { 7: 'T1' });
  assert.deepEqual(boundHeads({ 1: 9 }, { 0: 7 }), { 9: 'T2' });
});

test('locale: explicit choice, then host (pt_BR), then browser, then English', () => {
  assert.equal(normalizeLocale('pt_BR'), 'pt-BR'); assert.equal(normalizeLocale('pt'), 'pt-BR'); assert.equal(normalizeLocale('fr_FR'), null);
  assert.equal(normalizeLocale('de_DE'), 'de'); assert.equal(normalizeLocale('es'), 'es'); assert.equal(normalizeLocale('es-MX'), 'es');
  assert.equal(normalizeLocale('zh_CN'), 'zh-CN'); assert.equal(normalizeLocale('zh_TW'), 'zh-CN'); assert.equal(normalizeLocale('zh-Hant-TW'), 'zh-CN');
  assert.equal(normalizeLocale('ESP'), null); assert.equal(normalizeLocale(''), null); assert.equal(normalizeLocale(undefined), null);
  assert.equal(resolveLocale('en', 'pt_BR', ['pt-BR']), 'en');
  assert.equal(resolveLocale('de', 'zh_CN', ['es']), 'de'); assert.equal(resolveLocale('zh-CN', 'de', []), 'zh-CN');
  assert.equal(resolveLocale('auto', 'pt_BR', ['en-US']), 'pt-BR');
  assert.equal(resolveLocale('auto', 'es_ES', ['en-US']), 'es');
  assert.equal(resolveLocale('auto', null, ['fr-FR', 'pt-PT']), 'pt-BR');
  assert.equal(resolveLocale('auto', null, ['de-DE', 'pt-PT']), 'de');
  assert.equal(resolveLocale('auto', 'fr_FR', ['fr']), 'en');
  assert.equal(interpolate('T{n} {x}', { n: 2 }), 'T2 {x}');
});

test('PrimeVue labels: a language over English keeps English for any aria label it lacks', () => {
  const english = { accept: 'Yes', aria: { close: 'Close', star: 'Star' } };
  const merged = overEnglish(english, { accept: 'Ja', aria: { close: 'Schließen' } });
  assert.deepEqual(merged, { accept: 'Ja', aria: { close: 'Schließen', star: 'Star' } });
  assert.deepEqual(overEnglish(english, undefined), english);
  assert.equal(english.aria.close, 'Close', 'English itself untouched');
});
