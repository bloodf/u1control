// The command tracker (B-04/B-05): one per action, unknown after the timeout, no automatic retry, late answers.
// What a command answered is a toast on the shared host (foundation 4.2.0 toast.ts).
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { Tracker, split } from '../../src/core/tracker.ts';
import { clearToasts, toastList } from '../../shared/src/components/toast.ts';

function setup() {
  let now = 0;
  const timers: { at: number; fn: () => void }[] = [];
  const sends: { cmd: string; resolve: (v: unknown) => void; reject: (e: unknown) => void }[] = [];
  const clock = { now: () => now, setTimeout: (fn: () => void, ms: number) => { timers.push({ at: now + ms, fn }); return 0; } };
  const tr = new Tracker((cmd) => new Promise((resolve, reject) => sends.push({ cmd, resolve, reject })), (k, p) => `${k}: ${JSON.stringify(p)}`, clock);
  const advance = async (ms: number) => { now += ms; for (const t of timers.filter(t => t.at <= now)) { timers.splice(timers.indexOf(t), 1); t.fn(); } await new Promise(r => setImmediate(r)); };
  return { tr, sends, advance };
}
const toasts = () => toastList.list;
afterEach(() => clearToasts());   // success toasts arm a real 5 s timer

test('a second press while waiting sends nothing; success is a toast that leaves by itself', async () => {
  const { tr, sends } = setup();
  const a = tr.run({ key: 'pause', label: 'Pause', cmd: 'pause', okText: 'Pausing' });
  assert.deepEqual(await tr.run({ key: 'pause', label: 'Pause', cmd: 'pause' }), { ok: false, reason: 'busy' });
  assert.equal(sends.length, 1); assert.ok(tr.isBusy('pause'));
  sends[0].resolve(true);
  assert.deepEqual(await a, { ok: true, result: true });
  assert.ok(!tr.isBusy('pause'));
  assert.equal(toasts().length, 1);
  assert.equal(toasts()[0].tone, 'success'); assert.equal(toasts()[0].title, 'Pausing'); assert.equal(toasts()[0].timeout, 5000);
});

test('no answer: unknown outcome stays (a warning with no timeout), no retry; late answer replaces it', async () => {
  const { tr, sends, advance } = setup();
  const a = tr.run({ key: 'cancel', label: 'Cancel', cmd: 'cancel', timeoutMs: 15000 });
  await advance(15000);
  assert.deepEqual(await a, { ok: false, reason: 'timeout' });
  assert.equal(sends.length, 1, 'never retried');
  assert.equal(toasts().length, 1); assert.equal(toasts()[0].tone, 'warn'); assert.equal(toasts()[0].timeout, 0, 'stays until closed');
  assert.ok(!tr.isBusy('cancel'), 'the user may decide again');
  sends[0].reject(new Error('printer busy'));
  await advance(0);
  assert.equal(toasts().length, 1); assert.equal(toasts()[0].tone, 'error');
  assert.equal(toasts()[0].title, 'msg.lateError:', 'title up to the colon');
  assert.match(toasts()[0].body ?? '', /printer busy/);
});

test('errors stay until closed; E-stop may be pressed again while waiting', async () => {
  const { tr, sends } = setup();
  const e1 = tr.run({ key: 'estop', label: 'E-stop', cmd: 'emergency_stop', allowRepeat: true });
  const e2 = tr.run({ key: 'estop', label: 'E-stop', cmd: 'emergency_stop', allowRepeat: true });
  assert.equal(sends.length, 2);
  sends[0].reject(new Error('unreachable')); sends[1].resolve(true);
  await e1; await e2;
  const err = toasts().find(n => n.tone === 'error');
  assert.ok(err, 'error kept'); assert.equal(err.timeout, 0);
  tr.dismiss(err.id);
  assert.ok(!toasts().some(n => n.tone === 'error'));
});

test('split: title up to the first colon, the rest as the body (Chinese colon too)', () => {
  assert.deepEqual(split('Pause failed: timeout'), ['Pause failed:', 'timeout']);
  assert.deepEqual(split('暂停失败：timeout'), ['暂停失败：', 'timeout']);
  assert.deepEqual(split('Settings saved'), ['Settings saved', '']);
});
