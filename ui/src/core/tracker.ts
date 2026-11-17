import { markRaw, reactive } from 'vue';
import { dismissToast, showToast, type OuiToastTone } from '../../shared/src/components/toast.ts';

// Every printer command goes through one tracker: one in flight per action key (double clicks send once), a
// visible "waiting" state, a UI timeout that reports an UNKNOWN outcome (never success, never an automatic retry)
// and errors that stay until dismissed (B-04, B-05, U11). Results are returned, never thrown (B-12).
// What a command answered is a toast on the page's one toast host (foundation 4.2.0).
export type NoticeKind = 'error' | 'unknown' | 'success' | 'info';
export interface Pending { key: string; label: string; startedAt: number }
export type RunResult<T = any> =
  | { ok: true; result: T }
  | { ok: false; reason: 'busy' | 'error' | 'timeout'; error?: string };
export interface RunOptions {
  key: string;
  label: string;
  cmd: string;
  args?: Record<string, unknown>;
  okText?: string;
  timeoutMs?: number;
  /** E-stop: a second press is allowed while the first is still unanswered. */
  allowRepeat?: boolean;
  /** Errors reported by the caller itself (e.g. inline next to a form). */
  quiet?: boolean;
}
type Text = (key: 'msg.unknown' | 'msg.lateOk' | 'msg.lateError' | 'msg.failed', params: Record<string, unknown>) => string;

interface Clock { now: () => number; setTimeout: (fn: () => void, ms: number) => unknown }

export const DEFAULT_TIMEOUT_MS = 20_000;
const TONE: Record<NoticeKind, OuiToastTone> = { error: 'error', unknown: 'warn', success: 'success', info: 'info' };

/** "Pause failed: timeout" reads as a title and its detail (Chinese writes the colon as "："). */
export function split(text: string): [string, string] {
  const m = /: |：/.exec(text);
  return m ? [text.slice(0, m.index + 1), text.slice(m.index + m[0].length)] : [text, ''];
}

export class Tracker {
  readonly pending = reactive(new Map<string, Pending>());

  private readonly send: (cmd: string, args: Record<string, unknown>) => Promise<any>;
  private readonly text: Text;
  private readonly clock: Clock;

  constructor(send: (cmd: string, args: Record<string, unknown>) => Promise<any>, text: Text,
    clock: Clock = { now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms) }) {
    this.send = send; this.text = text; this.clock = clock;
  }

  isBusy(key: string): boolean { return this.pending.has(key); }

  /** A toast; an unknown outcome stays until closed or answered late, like an error (B-05). */
  notify(kind: NoticeKind, text: string): number {
    const [title, body] = split(text);
    return showToast({ tone: TONE[kind], title, body: body || undefined, ...(kind === 'unknown' ? { timeout: 0 } : {}) });
  }

  dismiss(id: number): void { dismissToast(id); }

  async run<T = any>(o: RunOptions): Promise<RunResult<T>> {
    if (this.pending.has(o.key) && !o.allowRepeat) return { ok: false, reason: 'busy' };
    const mine: Pending = markRaw({ key: o.key, label: o.label, startedAt: this.clock.now() });
    this.pending.set(o.key, mine);
    const done = () => { if (this.pending.get(o.key) === mine) this.pending.delete(o.key); };
    const timeoutMs = o.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    let timedOut = false;
    let unknownId = 0;
    const sent = this.send(o.cmd, o.args ?? {});
    const timeout = new Promise<'timeout'>(res => this.clock.setTimeout(() => res('timeout'), timeoutMs));
    try {
      const first = await Promise.race([sent.then(r => ({ r })), timeout]);
      if (first === 'timeout') {
        timedOut = true;
        done();
        unknownId = this.notify('unknown', this.text('msg.unknown', { action: o.label, seconds: Math.round(timeoutMs / 1000) }));
        sent.then(
          () => { this.dismiss(unknownId); this.notify('info', this.text('msg.lateOk', { action: o.label })); },
          e => { this.dismiss(unknownId); this.notify('error', this.text('msg.lateError', { action: o.label, error: message(e) })); },
        );
        return { ok: false, reason: 'timeout' };
      }
      done();
      if (o.okText) this.notify('success', o.okText);
      return { ok: true, result: first.r as T };
    } catch (e) {
      if (timedOut) return { ok: false, reason: 'timeout' };
      done();
      const error = message(e);
      if (!o.quiet) this.notify('error', this.text('msg.failed', { action: o.label, error }));
      return { ok: false, reason: 'error', error };
    }
  }
}

export function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
