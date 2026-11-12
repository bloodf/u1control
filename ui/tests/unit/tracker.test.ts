// The command tracker (B-04/B-05): one per action, unknown after the timeout, no automatic retry, late answers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Tracker } from '../../src/core/tracker.ts';

function setup() {
  let now = 0;
  const timers: { at: number; fn: () => void }[] = [];
  const sends: { cmd: string; resolve: (v: unknown) => void; reject: (e: unknown) => void }[] = [];
  const clock = { now: () => now, setTimeout: (fn: () => void, ms: number) => { timers.push({ at: now + ms, fn }); return 0; } };
  const tr = new Tracker((cmd) => new Promise((resolve, reject) => sends.push({ cmd, resolve, reject })), (k, p) => `${k} ${JSON.stringify(p)}`, clock);
  const advance = async (ms: number) => { now += ms; for (const t of timers.filter(t => t.at <= now)) { timers.splice(timers.indexOf(t), 1); t.fn(); } await new Promise(r => setImmediate(r)); };
  return { tr, sends, advance };
}

test('a second press while waiting sends nothing; success clears the pending state', async () => {
  const { tr, sends, advance } = setup();
  const a = tr.run({ key: 'pause', label: 'Pause', cmd: 'pause', okText: 'Pausing' });
  assert.deepEqual(await tr.run({ key: 'pause', label: 'Pause', cmd: 'pause' }), { ok: false, reason: 'busy' });
  assert.equal(sends.length, 1); assert.ok(tr.isBusy('pause'));
  sends[0].resolve(true);
  assert.deepEqual(await a, { ok: true, result: true });
  assert.ok(!tr.isBusy('pause'));
  assert.equal(tr.notices[0].kind, 'success');
  await advance(6000);
  assert.equal(tr.notices.length, 0);
});

test('no answer: unknown outcome that stays, no retry; a late answer replaces it', async () => {
  const { tr, sends, advance } = setup();
  const a = tr.run({ key: 'cancel', label: 'Cancel', cmd: 'cancel', timeoutMs: 15000 });
  await advance(15000);
  assert.deepEqual(await a, { ok: false, reason: 'timeout' });
  assert.equal(sends.length, 1, 'never retried');
  assert.equal(tr.notices.length, 1); assert.equal(tr.notices[0].kind, 'unknown');
  await advance(60000);
  assert.equal(tr.notices[0].kind, 'unknown', 'still shown');
  assert.ok(!tr.isBusy('cancel'), 'the user may decide again');
  sends[0].reject(new Error('printer busy'));
  await advance(0);
  assert.equal(tr.notices.length, 1); assert.equal(tr.notices[0].kind, 'error');
  assert.match(tr.notices[0].text, /msg.lateError/);
});

test('errors stay until dismissed; E-stop may be pressed again while waiting', async () => {
  const { tr, sends, advance } = setup();
  const e1 = tr.run({ key: 'estop', label: 'E-stop', cmd: 'emergency_stop', allowRepeat: true });
  const e2 = tr.run({ key: 'estop', label: 'E-stop', cmd: 'emergency_stop', allowRepeat: true });
  assert.equal(sends.length, 2);
  sends[0].reject(new Error('unreachable')); sends[1].resolve(true);
  await e1; await e2;
  await advance(600000);
  const err = tr.notices.find(n => n.kind === 'error');
  assert.ok(err, 'error kept'); tr.dismiss(err.id);
  assert.ok(!tr.notices.some(n => n.kind === 'error'));
});
