// What each spool of the drawn printer shows: Spoolman spool, else printer colour, else an empty reel.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { colourName, figureSpools, parseHex } from '../../src/core/figure.ts';
import type { Head, Spool } from '../../src/app/types.ts';

const head = (type: string, colour = '#112233'): Head => ({ loaded: !!type, type, vendor: 'G', sub_type: 'B', colour });
const spool = (id: number, extra: Partial<Spool> = {}): Spool => ({ id, name: 'S', vendor: 'V', material: 'PETG', colour: '#ff7a00', remaining: 250, initial: 1000, ...extra });

test('the Spoolman spool wins over the printer colour and sets the fill', () => {
  const [t1] = figureSpools([head('PLA', '#00ff00')], { 0: 7 }, [spool(7)]);
  assert.deepEqual(t1, { n: 1, empty: false, colour: '#ff7a00', colours: null, fraction: 0.25, material: 'PETG', name: 'orange', source: 'spoolman' });
});

test('no linked spool: the printer-reported colour, fill unknown', () => {
  const [, t2] = figureSpools([head(''), head('PLA', '#3e63dd')], {}, []);
  assert.equal(t2.source, 'printer'); assert.equal(t2.colour, '#3e63dd'); assert.equal(t2.fraction, null); assert.equal(t2.name, 'blue'); assert.equal(t2.empty, false);
});

test('nothing loaded and nothing linked: an empty reel; missing heads too', () => {
  const out = figureSpools([head('')], {}, []);
  assert.equal(out.length, 4);
  for (const sp of out) { assert.equal(sp.empty, true); assert.equal(sp.colour, null); assert.equal(sp.source, 'none'); }
  assert.deepEqual(out.map(sp => sp.n), [1, 2, 3, 4]);
});

test('a link to a spool that is gone, or has no colour, falls back to the printer', () => {
  const [t1, t2] = figureSpools([head('PLA', '#111111'), head('PLA', '#ffffff')], { 0: 99, 1: 8 }, [spool(8, { colour: '' })]);
  assert.equal(t1.source, 'printer'); assert.equal(t1.name, 'black');
  assert.equal(t2.source, 'printer'); assert.equal(t2.name, 'white');
});

test('multi-colour spools keep every colour, painted side by side', () => {
  const four = [head('PLA'), head('PLA'), head('PLA'), head('PLA')];
  const [, , , t4] = figureSpools(four, { 3: 12 }, [spool(12, { colour: '#e5484d', colours: ['#e5484d', '#f5d90a', '#3e63dd'], remaining: null })]);
  assert.deepEqual(t4.colours, ['#e5484d', '#f5d90a', '#3e63dd']);
  assert.equal(t4.name, 'multi'); assert.equal(t4.fraction, null); assert.equal(t4.empty, false);
  const [one] = figureSpools(four, { 0: 3 }, [spool(3, { colours: ['#3e63dd'] })]);
  assert.equal(one.colours, null, 'a one-colour list is a plain colour');
});

test('a 0 g linked spool on a loaded head is still loaded, in its colour', () => {
  const [t1] = figureSpools([head('PLA')], { 0: 7 }, [spool(7, { remaining: 0 })]);
  assert.equal(t1.empty, false); assert.equal(t1.fraction, 0); assert.equal(t1.colour, '#ff7a00');
});

test('a spool still linked to an unloaded head is not painted: empty reel', () => {
  const [t1] = figureSpools([head('')], { 0: 7 }, [spool(7)]);
  assert.equal(t1.empty, true); assert.equal(t1.colour, null); assert.equal(t1.source, 'none');
});

test('invalid Spoolman colours are dropped', () => {
  const [t1, t2, t3] = figureSpools([head('PLA'), head('PLA', '#3e63dd'), head('PLA')], { 0: 1, 1: 2, 2: 3 },
    [spool(1, { colour: 'not a colour', colours: ['#e5484d', 'nope', '#3e63dd'] }), spool(2, { colour: 'url(x)', colours: ['junk'] }), spool(3, { colour: 'red; x', colours: ['#30a46c'] })]);
  assert.deepEqual(t1.colours, ['#e5484d', '#3e63dd']); assert.equal(t1.colour, '#e5484d'); assert.equal(t1.name, 'multi');
  assert.equal(t2.source, 'printer', 'nothing valid on the spool: the printer colour'); assert.equal(t2.colour, '#3e63dd');
  assert.equal(t3.colour, '#30a46c'); assert.equal(t3.colours, null); assert.equal(t3.name, 'green');
});

test('the printer colour must be a colour', () => {
  const [t1] = figureSpools([head('PLA', 'nope')], {}, []);
  assert.equal(t1.colour, null); assert.equal(t1.name, null); assert.equal(t1.empty, false);
});

test('hex parsing and plain colour words', () => {
  assert.deepEqual(parseHex('#fa0'), [255, 170, 0]);
  assert.deepEqual(parseHex('11223344'), [17, 34, 51]);
  assert.equal(parseHex('#12'), null);
  const names = { '#000000': 'black', '#ffffff': 'white', '#808080': 'grey', '#e5484d': 'red', '#ff7a00': 'orange', '#6b3e1e': 'brown',
    '#f5d90a': 'yellow', '#30a46c': 'green', '#00c2d7': 'cyan', '#3e63dd': 'blue', '#8e4ec6': 'purple', '#f78fb3': 'pink' };
  for (const [hex, name] of Object.entries(names)) assert.equal(colourName(hex), name, hex);
});
