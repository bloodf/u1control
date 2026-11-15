// How much of a spool is left, for the drawn spool and the level bar.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spoolFraction } from '../../src/core/spool-level.ts';

test('fraction needs both weights', () => {
  assert.equal(spoolFraction(250, 1000), 0.25);
  assert.equal(spoolFraction(1200, 1000), 1);
  assert.equal(spoolFraction(250, null), null);
  assert.equal(spoolFraction(null, 1000), null);
  assert.equal(spoolFraction(250, 0), null);
});
