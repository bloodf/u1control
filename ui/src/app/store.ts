import { computed, reactive } from 'vue';
import * as bridge from '../core/bridge';
import { Tracker, message, type RunOptions } from '../core/tracker';
import { t } from '../core/i18n';
import { cancelDialog } from '../core/dialog';
import type { Config, Info, Spool, Status, StockView, UsageView } from './types';

export type Phase = 'connecting' | 'connected' | 'noTarget' | 'unreachable';
export const LIMITS = { hotend: 320, bed: 110 };
export const STALE_STATUS_S = 10;

export const s = reactive({
  phase: 'connecting' as Phase,
  epoch: 0,
  info: null as Info | null,
  error: '',
  offline: '',
  status: null as Status | null,
  statusAt: 0,
  now: Date.now(),
  limits: { ...LIMITS },
  spools: [] as Spool[],
  bindings: {} as Record<string, number>,
  spoolsVia: '',
  spoolsError: '',
  spoolsLoaded: false,
  config: null as Config | null,
  tab: 'dash',
  hidden: document.hidden,
  camOn: false,
  frame: '',
  camError: '',
  scrOn: false,
  screen: '',
  screenError: '',
  stock: null as StockView | null,
  stockError: '',
  stockLoading: false,
  usage: null as UsageView | null,
  usageError: '',
});

export const tracker = new Tracker(
  (cmd, args) => bridge.command(cmd, args, s.info?.generation),
  (key, params) => t(key, params),
);
export const run = (o: RunOptions) => tracker.run(o);
bridge.setErrorSink(e => tracker.notify('error', t('msg.plugin', { error: message(e) })));

export const printerName = computed(() => s.info?.printer || 'U1');
export const targetKnown = computed(() => s.phase === 'connected' || s.phase === 'unreachable');
export const statusAge = computed(() => (s.statusAt ? (s.now - s.statusAt) / 1000 : Infinity));
export const printing = computed(() => s.status?.state === 'printing' || s.status?.state === 'paused');
/** Why printer commands are off, or '' when they can be used. Emergency stop has its own rule (estopReason). */
export const controlsOff = computed(() => {
  if (s.phase === 'noTarget') return t('reason.noTarget');
  if (s.phase === 'unreachable' || s.offline) return t('reason.offline');
  if (s.phase === 'connecting' || !s.status) return t('reason.waiting');
  return '';
});
/** E-stop stays usable for a known printer even when its status is offline or late (urgent path, no queue). */
export const estopReason = computed(() => (targetKnown.value ? '' : s.phase === 'noTarget' ? t('reason.noTarget') : t('reason.waiting')));
export const busy = computed(() => !!s.status?.busy);

function reset(): void {
  s.epoch++;
  Object.assign(s, { info: null, error: '', offline: '', status: null, statusAt: 0, spools: [], bindings: {}, spoolsVia: '',
    spoolsError: '', spoolsLoaded: false, frame: '', camError: '', screen: '', screenError: '', usageError: '' });
  if (s.stock) s.stock = { ...s.stock, bindings: {}, same_spoolman: null, usage: 'unknown' };
  cancelDialog();
}

let helloInFlight = false;
export async function hello(): Promise<void> {
  reset();
  s.phase = 'connecting';
  const epoch = s.epoch;
  helloInFlight = true;
  try {
    const r: Info = await bridge.request({ type: 'hello' });
    if (epoch !== s.epoch) return;
    s.info = r;
    s.limits = { ...LIMITS, ...(r.limits ?? {}) };
    s.phase = 'connected';
    void loadSpools(true);
  } catch (e) {
    if (epoch !== s.epoch) return;
    s.phase = e instanceof bridge.ReplyError && e.noTarget ? 'noTarget' : 'unreachable';
    s.error = message(e);
  } finally {
    helloInFlight = false;
    if (epoch === s.epoch) { void loadStock(false); void loadUsage(); }
  }
}

export async function loadSpools(quiet: boolean): Promise<void> {
  if (!targetKnown.value) return;
  const epoch = s.epoch;
  const r = await run({ key: 'spools', label: t('act.spools'), cmd: 'spools', quiet: true });
  if (epoch !== s.epoch) return;
  if (r.ok) {
    s.spools = r.result.spools ?? [];
    s.bindings = r.result.bindings ?? {};
    s.spoolsVia = r.result.via ?? '';
    s.spoolsError = '';
    s.spoolsLoaded = true;
  } else if (r.reason !== 'busy') {
    s.spoolsError = r.error ?? t('common.unknown');
    if (!quiet) tracker.notify('error', t('msg.failed', { action: t('act.spools'), error: s.spoolsError }));
  }
}

let stockSeq = 0;
export async function loadStock(refresh: boolean): Promise<void> {
  const mine = ++stockSeq, epoch = s.epoch;
  s.stockLoading = true;
  try {
    const r: StockView = await bridge.command('stock', { refresh }, s.info?.generation);
    if (mine === stockSeq && epoch === s.epoch) { s.stock = r; s.stockError = ''; }
  } catch (e) {
    if (mine === stockSeq && epoch === s.epoch) s.stockError = message(e);
  } finally {
    if (mine === stockSeq) s.stockLoading = false;
  }
}

export async function loadUsage(): Promise<void> {
  const epoch = s.epoch;
  try {
    const r: UsageView = await bridge.command('usage', {}, s.info?.generation);
    if (epoch === s.epoch) { s.usage = r; s.usageError = ''; }
  } catch (e) {
    if (epoch === s.epoch) s.usageError = message(e);
  }
}

export const stockVisible = computed(() => {
  const st = s.stock;
  if (s.stockError) return true;
  return !!st && st.spooler.state !== 'absent';
});

function onMessage(m: any): void {
  switch (m.type) {
    case 'status':
      s.status = m.data; s.statusAt = Date.now(); s.offline = '';
      if (m.data?.bindings) s.bindings = m.data.bindings;
      if (s.phase === 'unreachable' && !helloInFlight) void hello();   // it answers again: fetch its generation
      break;
    case 'offline': s.offline = String(m.error ?? ''); break;
    case 'frame': s.frame = m.image; s.camError = ''; break;
    case 'camera_error': if (s.camOn) { s.camError = String(m.error ?? ''); s.frame = ''; } break;
    case 'screen': s.screen = m.image; s.screenError = ''; break;
    case 'screen_error': if (s.scrOn) { s.screen = ''; s.screenError = String(m.error ?? ''); } break;
    case 'notice': tracker.notify('info', String(m.text ?? '')); break;
    case 'config': configHandlers.forEach(h => h(m)); break;
    case 'rfid': rfidHandlers.forEach(h => h(m)); break;
    case 'selection_changed': void hello(); break;
    case 'reply': if (m.error) tracker.notify('error', t('msg.plugin', { error: String(m.error) })); break;
  }
}
const configHandlers = new Set<(m: Config) => void>();
const rfidHandlers = new Set<(m: any) => void>();
export const onConfig = (h: (m: Config) => void) => { configHandlers.add(h); return () => configHandlers.delete(h); };
export const onRfid = (h: (m: any) => void) => { rfidHandlers.add(h); return () => rfidHandlers.delete(h); };

export function lease(): void {
  const vis = !s.hidden && s.tab === 'dash';
  bridge.post({ type: 'lease', camera: s.camOn && vis, screen: s.scrOn && vis, stock: vis && stockVisible.value });
}

export function start(): () => void {
  bridge.attach();
  const off = bridge.onMessage(onMessage);
  const onVis = () => { s.hidden = document.hidden; lease(); };
  document.addEventListener('visibilitychange', onVis);
  const timers = [
    window.setInterval(lease, 2000),
    window.setInterval(() => { s.now = Date.now(); }, 1000),
    window.setInterval(() => { if (s.tab === 'dash' && !s.hidden) void loadStock(false); }, 5000),
    window.setInterval(() => { if (s.tab === 'dash' && !s.hidden) void loadUsage(); }, 10000),
  ];
  void hello();
  return () => { off(); document.removeEventListener('visibilitychange', onVis); timers.forEach(clearInterval); };
}
