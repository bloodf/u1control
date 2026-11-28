// Pure rules of the page (node --test runs this TypeScript directly).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { coverMode, exceptionParts, reprintParts } from '../../src/core/logic.ts';
import { parseTarget, parseSpeed, heaterPhase, setupWarnings, warningKey, moveTargets, folderTree, fileKind, rootOf, boundHeads, withLink, family, overEnglish, colourFar } from '../../src/core/logic.ts';
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

test('setup warnings: a head with filament nobody has named is not called empty', () => {
  const heads = [{ index: 0, loaded: true, type: 'PLA' }, { index: 1, loaded: false, unnamed: true, type: '' }, { index: 2, loaded: false, type: '' }];
  const w = setupWarnings([{ index: 0, type: 'PLA' }, { index: 1, type: 'PLA' }], heads, { 0: 1, 1: 2 });
  assert.equal(warningKey(w), 'unnamed:0:1,empty:1:2');   // the ids u1.warning_ids builds
  assert.deepEqual(w.map(x => x.kind), ['unnamed', 'empty']);
});

test('setup warnings: a nozzle type other than the slice\'s, only when both are known', () => {
  const heads = [{ index: 0, loaded: true, type: 'PLA', nozzle: 'high_flow' }, { index: 1, loaded: true, type: 'PETG', nozzle: '' }];
  const fils = [{ index: 0, type: 'PLA', nozzle: 'standard' }, { index: 1, type: 'PLA', nozzle: 'standard' }];
  assert.equal(warningKey(setupWarnings(fils, heads, { 0: 0, 1: 1 })), 'nozzle:0:0,material:1:1');   // as u1.warning_ids
  assert.deepEqual(setupWarnings([{ index: 0, type: 'PLA' }], heads, { 0: 0 }), []);
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
  assert.equal(normalizeLocale('pl_PL'), 'pl'); assert.equal(normalizeLocale('pl-PL'), 'pl'); assert.equal(normalizeLocale('PL'), 'pl');
  assert.equal(resolveLocale('auto', 'pl_PL', ['en-US']), 'pl'); assert.equal(resolveLocale('pl', 'de', []), 'pl');
  assert.equal(normalizeLocale('cs_CZ'), 'cs'); assert.equal(normalizeLocale('cs-CZ'), 'cs'); assert.equal(resolveLocale('auto', 'cs_CZ', ['en-US']), 'cs');
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

test('colourFar: the print setup hints only at clearly different colours', () => {
  assert.equal(colourFar('#E5484D', '#e5484dff'), false);       // same colour, alpha ignored
  assert.equal(colourFar('#E5484D', '#D9434A'), false);         // near shade
  assert.equal(colourFar('#E5484D', '#3E63DD'), true);          // red vs blue
  assert.equal(colourFar('#FFFFFF', '#000000'), true);
  assert.equal(colourFar(undefined, '#000000'), false);         // unknown: nothing to compare
  assert.equal(colourFar('#fff', '#000000'), false);
});

test('the folder tree: parents from paths, roots named and in the order given, a read-only root read only throughout', () => {
  const name = (r: string) => ({ gcodes: 'Print files', camera: 'Camera' } as Record<string, string>)[r] ?? r;
  const tree = folderTree(['gcodes', 'camera', 'gcodes/b/deep', 'gcodes/a', 'camera/shots'], name, ['camera']);
  // gcodes/b was never listed: added as a parent
  assert.deepEqual(tree.map(f => f.id), ['gcodes', 'gcodes/a', 'gcodes/b', 'gcodes/b/deep', 'camera', 'camera/shots']);
  assert.deepEqual(tree.map(f => [f.name, f.parent]), [['Print files', null], ['a', 'gcodes'], ['b', 'gcodes'], ['deep', 'gcodes/b'], ['Camera', null], ['shots', 'camera']]);
  assert.deepEqual(tree.filter(f => f.readonly).map(f => f.id), ['camera', 'camera/shots']);
  assert.equal(rootOf('gcodes/sub/a.gcode'), 'gcodes');
});

test('a file\'s kind is G-code for a print file, else its extension in capitals', () => {
  assert.equal(fileKind('benchy.gcode'), 'G-code');
  assert.equal(fileKind('old.GCO'), 'G-code');
  assert.equal(fileKind('plate.3mf'), '3MF');
  assert.equal(fileKind('a.b.MP4'), 'MP4');
  assert.equal(fileKind('README'), undefined);
  assert.equal(fileKind('odd.name with spaces'), undefined);
});

test('a chosen spool shows on its head at once and leaves the head it was on; unlinking drops the head', () => {
  const was = { '0': 3, '1': 7 };
  assert.deepEqual(withLink(was, 2, 7), { '0': 3, '2': 7 });
  assert.deepEqual(withLink(was, 0, 9), { '0': 9, '1': 7 });
  assert.deepEqual(withLink(was, 1, null), { '0': 3 });
  assert.deepEqual(was, { '0': 3, '1': 7 });   // the old links are kept, for the rollback
});

test('printer records are said in words: an error by its text and code, a power cut by its file and layer', () => {
  assert.deepEqual(exceptionParts({ code: 522, level: 2, msg: 'filament_entangle' }), { name: 'Filament entangle', code: '522' });
  assert.deepEqual(exceptionParts({ id: 'E7', message: 'Nozzle  clogged' }), { name: 'Nozzle clogged', code: 'E7' });
  assert.deepEqual(exceptionParts({ code: 7 }), { name: '', code: '7' });
  assert.deepEqual(exceptionParts('heater_fault'), { name: 'Heater fault', code: '' });
  assert.deepEqual(exceptionParts({ level: 2, nested: { a: 1 } }), { name: '', code: '' });   // nothing it can say: never the record
  assert.deepEqual(exceptionParts(null), { name: '', code: '' });
  assert.deepEqual(reprintParts({ file: 'gcodes/sub/part.gcode', layer: 41 }), { file: 'part.gcode', layer: 41 });
  assert.deepEqual(reprintParts({ file_path: 'C:\\x\\part.gcode' }), { file: 'part.gcode', layer: null });
  assert.deepEqual(reprintParts({ current_layer: 3 }), { file: '', layer: 3 });
  assert.deepEqual(reprintParts('x'), { file: '', layer: null });
});

test('the top cover mode as the printer reports it; cooling does not say how hard', () => {
  assert.equal(coverMode(0), 'idle'); assert.equal(coverMode(1), 'cooling');
  assert.equal(coverMode(2), 'keep-warm'); assert.equal(coverMode(3), 'keep-warm'); assert.equal(coverMode('keep-warm'), 'keep-warm');
  assert.equal(coverMode(undefined), ''); assert.equal(coverMode(true), ''); assert.equal(coverMode(9), '');
});
