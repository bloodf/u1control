// The print setup's top view: the run-length map preview.top_view sends, decoded.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decode, NONE } from '../../src/setup/top-view.ts';

const runs = (...quads: number[][]) => btoa(String.fromCharCode(...quads.flat()));

test('runs fill the cells row by row', () => {
  const c = decode({ w: 3, h: 2, bounds: [0, 0, 3, 2], runs: runs([2, 255, 0, 0], [3, 1, 200, 3], [1, 0, 255, 1]) });
  assert.deepEqual([...c.tool], [NONE, NONE, 1, 1, 1, 0]);
  assert.deepEqual([...c.height], [0, 0, 200, 200, 200, 255]);
  assert.deepEqual([...c.tools], [0, 0, 3, 3, 3, 1]);
});

test('a short, long or broken map stays the right size', () => {
  assert.deepEqual([...decode({ w: 2, h: 1, bounds: [0, 0, 2, 1], runs: runs([1, 2, 9, 4]) }).tool], [2, NONE]);
  assert.deepEqual([...decode({ w: 2, h: 1, bounds: [0, 0, 2, 1], runs: runs([9, 2, 9, 4]) }).tool], [2, 2]);
  assert.deepEqual([...decode({ w: 2, h: 1, bounds: [0, 0, 2, 1], runs: '%%' }).tool], [NONE, NONE]);
});
