// The spool picture's level and paint (same rule as Spooler's).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spoolLevel, spoolFraction, spoolPaint } from '../../src/core/spool-level.ts';

test('nearest render; any filament left is never the bare reel', () => {
  assert.deepEqual([1, 0.9, 0.6, 0.36, 0.2, 0.05, 0.001, 0, -1, null, 2, NaN].map(spoolLevel), [1, 2, 4, 5, 6, 7, 7, 8, 8, 8, 1, 8]);
});
test('fraction needs both weights', () => {
  assert.equal(spoolFraction(250, 1000), 0.25);
  assert.equal(spoolFraction(1200, 1000), 1);
  assert.equal(spoolFraction(250, null), null);
  assert.equal(spoolFraction(null, 1000), null);
  assert.equal(spoolFraction(250, 0), null);
});
test('paint: one colour, or every colour side by side', () => {
  assert.equal(spoolPaint('#C8501E'), '#C8501E');
  assert.equal(spoolPaint('#FF0000', ['#FF0000', '#00FF00']), 'linear-gradient(90deg, #FF0000 0% 50%, #00FF00 50% 100%)');
  assert.equal(spoolPaint(null), '');
});
