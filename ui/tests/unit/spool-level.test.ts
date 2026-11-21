// How much of a spool is left, for the drawn spool and the level bar.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { headColours, headFraction, levelTone, present, spoolFraction } from '../../src/core/spool-level.ts';

test('fraction needs both weights', () => {
  assert.equal(spoolFraction(250, 1000), 0.25);
  assert.equal(spoolFraction(1200, 1000), 1);
  assert.equal(spoolFraction(250, null), null);
  assert.equal(spoolFraction(null, 1000), null);
  assert.equal(spoolFraction(250, 0), null);
});

test('a toolhead is drawn from its linked spool, else as the bare reel', () => {
  assert.equal(headFraction(true, { remaining: 640, initial: 1000 }), 0.64);
  assert.equal(headFraction(true, null), null);                               // no Spoolman spool: no amount, not 0.6
  assert.equal(headFraction(true, { remaining: 640, initial: null }), null);  // spool without a full weight
  assert.equal(headFraction(true, { remaining: null, initial: 1000 }), null);
  assert.equal(headFraction(false, { remaining: 640, initial: 1000 }), null); // nothing loaded, whatever is still linked
  assert.equal(headFraction(true, { remaining: 0, initial: 1000 }), 0);
});

test('a level bar is green, amber when Spoolman says low, red when almost empty', () => {
  assert.equal(levelTone(0.6), 'normal');
  assert.equal(levelTone(0.6, true), 'low');
  assert.equal(levelTone(0.04, false), 'critical');   // under 5 % is red whatever the low flag says
  assert.equal(levelTone(0.04, true), 'critical');
  assert.equal(levelTone(null, true), 'low');         // weight unknown: only the flag is known
  assert.equal(levelTone(null), 'normal');
});

test('a head nobody has named still has filament in it', () => {
  assert.equal(present({ loaded: true }), true);
  assert.equal(present({ loaded: false, unnamed: true }), true);
  assert.equal(present({ loaded: false }), false);
  assert.equal(present(undefined), false);
});

test('every colour of a multi-colour spool: the linked spool\'s, else the printer\'s own record', () => {
  const rgb = ['#FF0000', '#00FF00', '#0000FF'];
  assert.deepEqual(headColours(null, { colours: rgb }), rgb);
  assert.equal(headColours(null, { colours: ['#FF0000'] }), null);                         // one colour: no segments
  assert.equal(headColours({ colour: '#111111', colours: [] }, { colours: rgb }), null);     // the linked spool's single colour wins
  assert.deepEqual(headColours({ colour: '#111111', colours: ['#111111', '#EEEEEE'] }, { colours: rgb }), ['#111111', '#EEEEEE']);
  assert.deepEqual(headColours({ colours: [] }, { colours: rgb }), rgb);                     // a spool without a colour says nothing
  assert.equal(headColours(null, undefined), null);
});
