import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presetLabel } from '../../src/core/match.ts';

test('a preset is shown without its bundle folder, Spooler/ and @printer', () => {
  assert.equal(presetLabel('Spooler/3D Procer PLA Marrom terra @Snapmaker U1'), '3D Procer PLA Marrom terra');
  assert.equal(presetLabel('_local/spooler/3D Procer PLA Marrom terra @Snapmaker U1'), '3D Procer PLA Marrom terra');
  assert.equal(presetLabel('Generic PLA @System'), 'Generic PLA');
  assert.equal(presetLabel('My PLA'), 'My PLA');
  assert.equal(presetLabel('@U1'), '@U1');
});
