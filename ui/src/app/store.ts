import { computed, reactive, watch } from 'vue';
import * as bridge from '../core/bridge';
import { Tracker, message, type RunOptions } from '../core/tracker';
import { t } from '../core/i18n';
import { ask, cancelDialog } from '../core/dialog';
import { autoRefresh, cleanEvery, userBusy, REFRESH_DEFAULT_S } from '../core/autorefresh';
import type { Config, Heater, Info, Requirement, Spool, Status, StockView, UsageView } from './types';

export type Phase = 'connecting' | 'connected' | 'noTarget' | 'unreachable';
export const LIMITS = { hotend: 320, bed: 110 };
export const STALE_STATUS_S = 10;
/** Heater readings kept for the small charts: one every 5 s, ten minutes of them. Shown only, never acted on. */
export const HISTORY_EVERY_MS = 5000;
export const HISTORY_MAX = 120;

/** Open Settings at one page (conn-h, print-h, ...): a "Settings" link elsewhere on the page. */
export function openSettings(page: string): void { s.settingsPage = page; s.tab = 'settings'; }

export const s = reactive({
  phase: 'connecting' as Phase,
  epoch: 0,
  info: null as Info | null,
  error: '',
  offline: '',
  status: null as Status | null,
  statusAt: 0,
  history: {} as Record<string, (number | null)[]>,
  historyAt: 0,
  now: Date.now(),
  limits: { ...LIMITS },
  spools: [] as Spool[],
  bindings: {} as Record<string, number>,
  spoolsVia: '',
  spoolsError: '',
  spoolsLoaded: false,
  /** Seconds between Spoolman re-reads (settings spoolman_refresh_s; 0 = off), and whether the last ones failed. */
  refreshS: REFRESH_DEFAULT_S,
  spoolsRetrying: false,
  config: null as Config | null,
  tab: 'dash',
  settingsPage: '',                 // the settings page a link asked for, opened once Settings shows
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
  requirements: [] as Requirement[],
  reqChecking: false,
});

export const tracker = new Tracker(
  (cmd, args) => bridge.command(cmd, args, s.info?.generation),
  (key, params) => t(key, params),
);
export const run = (o: RunOptions) => tracker.run(o);
bridge.setErrorSink(e => tracker.notify('error', t('msg.plugin', { error: message(e) })));

export const printerName = computed(() => s.info?.printer || 'U1');
/** The firmware in words ("Official firmware 2.0.0"), for the Dashboard's page header. */
export const fwText = computed(() => {
  if (s.phase === 'connecting') return t('fw.connecting');
  if (!s.info) return t('fw.none');
  const v = s.info.firmware.version ?? '';
  return s.info.firmware.kind === 'extended' ? t('fw.extended', { version: v })
    : s.info.firmware.kind === 'stock' ? t('fw.stock', { version: v }) : t('fw.unknown');
});
export const targetKnown = computed(() => s.phase === 'connected' || s.phase === 'unreachable');
export const statusAge = computed(() => (s.statusAt ? (s.now - s.statusAt) / 1000 : Infinity));
/** Last known values of a printer the page no longer hears from: drawn grey, never as live. */
export const stale = computed(() => !!s.status && (s.phase === 'unreachable' || !!s.offline || statusAge.value > STALE_STATUS_S));
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
/** Same question and urgent path from the app bar on every tab: one press away, never queued behind another command. */
export async function estop(): Promise<void> {
  if (!await ask({ title: t('confirm.estop.title'), text: t('confirm.estop.text', { printer: printerName.value }),
    yes: t('confirm.estop.yes'), no: t('common.goBack'), danger: true })) return;
  await run({ key: 'estop', label: t('act.estop'), cmd: 'emergency_stop', okText: t('ok.estop'), timeoutMs: 10000, allowRepeat: true });
}
/** A requirement's status as last told by the plugin; 'unknown' until it answered. */
export const reqStatus = (id: Requirement['id']) => s.requirements.find(r => r.id === id)?.status ?? 'unknown';
/** Ask the plugin which requirements are there (no printer I/O); recheck = "Check again" (asks OrcaSlicer anew). */
export function loadRequirements(recheck = false): void { bridge.post({ type: 'requirements', recheck }); }
/** "Check again": the plugin looks again (OrcaSlicer's agent, Spooler), plus what only the printer can tell (its
 *  Spoolman link) when one is known. Rows show "Checking…" until the plugin answers; without an answer within
 *  REQ_TIMEOUT_MS they stop and say so. */
export const REQ_TIMEOUT_MS = 10000;
let reqTimer: ReturnType<typeof setTimeout> | undefined;
export async function checkRequirements(): Promise<void> {
  if (s.reqChecking) return;
  s.reqChecking = true;
  clearTimeout(reqTimer);
  reqTimer = setTimeout(() => {
    if (!s.reqChecking) return;
    s.reqChecking = false;
    tracker.notify('error', t('req.noAnswer', { seconds: REQ_TIMEOUT_MS / 1000 }));
  }, REQ_TIMEOUT_MS);
  loadRequirements(true);
  if (targetKnown.value) await loadSpools(true);
}
/** Why the guided toolhead commands (Edit, Load, Unload) are off, or ''. */
export const guidedWhy = computed(() => controlsOff.value || (busy.value ? t('reason.busy') : ''));

function reset(): void {
  s.epoch++;
  Object.assign(s, { info: null, error: '', offline: '', status: null, statusAt: 0, history: {}, historyAt: 0, spools: [], bindings: {}, spoolsVia: '',
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
    if (epoch === s.epoch) { void loadStock(false); void loadUsage(); loadRequirements(); }
  }
}

/** Spools and toolhead links from Spoolman; false when the read failed. */
export async function loadSpools(quiet: boolean): Promise<boolean> {
  if (!targetKnown.value) return true;
  const epoch = s.epoch;
  const r = await run({ key: 'spools', label: t('act.spools'), cmd: 'spools', quiet: true });
  if (epoch !== s.epoch) return true;
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
  loadRequirements();   // the load is what tells whether Spoolman is there (directly or through the printer)
  return r.ok || r.reason === 'busy';
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

/** Spools in Spooler's stock list, for the Stock tab's count; null while there is no list to count. */
export const stockCount = computed(() => {
  const st = s.stock;
  return !s.stockError && st?.spooler.state === 'active' && Array.isArray(st.stock?.rows) && !['unavailable', 'missing', 'error', 'mismatch'].includes(st.stock.state) ? st.stock.rows.length : null;
});
export const stockVisible = computed(() => {
  const st = s.stock;
  if (s.stockError) return true;
  return !!st && st.spooler.state !== 'absent';
});

function remember(d: Status): void {
  const now = Date.now();
  if (now - s.historyAt < HISTORY_EVERY_MS) return;
  const add = (key: string, h: Heater | undefined) => [key, [...(s.history[key] ?? []), h?.temp ?? null].slice(-HISTORY_MAX)] as const;
  s.history = Object.fromEntries([...(d.extruders ?? []).map((e, i) => add(String(i), e)), add('bed', d.bed)]);
  s.historyAt = now;
}

function onMessage(m: any): void {
  switch (m.type) {
    case 'status':
      s.status = m.data; s.statusAt = Date.now(); s.offline = '';
      if (m.data) remember(m.data);
      if (m.data?.bindings) s.bindings = m.data.bindings;
      // The plugin checks the firmware again when its first answer was unclear (or after the printer was away).
      if (s.info && m.data?.firmware?.kind && (m.data.firmware.kind !== s.info.firmware.kind
        || (m.data.firmware.version ?? '') !== (s.info.firmware.version ?? ''))) { s.info = { ...s.info, firmware: m.data.firmware }; loadRequirements(); }
      if (s.phase === 'unreachable' && !helloInFlight) void hello();   // it answers again: fetch its generation
      break;
    case 'offline': s.offline = String(m.error ?? ''); break;
    case 'frame': s.frame = m.image; s.camError = ''; break;
    case 'camera_error': if (s.camOn) { s.camError = String(m.error ?? ''); s.frame = ''; } break;
    case 'screen': s.screen = m.image; s.screenError = ''; break;
    case 'screen_error': if (s.scrOn) { s.screen = ''; s.screenError = String(m.error ?? ''); } break;
    case 'requirements': if (Array.isArray(m.items)) { s.requirements = m.items; s.reqChecking = false; clearTimeout(reqTimer); } break;
    case 'notice': tracker.notify('info', String(m.text ?? '')); break;
    case 'config': configHandlers.forEach(h => h(m)); break;
    case 'rfid': rfidHandlers.forEach(h => h(m)); break;
    case 'selection_changed': void hello(); break;
    case 'show_tab': if (m.tab === 'settings') openSettings('print-setup'); break;   // the print setup's "Plugin settings"
    case 'reply': if (m.error) tracker.notify('error', t('msg.plugin', { error: String(m.error) })); break;
  }
}
const configHandlers = new Set<(m: Config) => void>();
const rfidHandlers = new Set<(m: any) => void>();
export const onConfig = (h: (m: Config) => void) => { configHandlers.add(h); return () => configHandlers.delete(h); };
export const onRfid = (h: (m: any) => void) => { rfidHandlers.add(h); return () => rfidHandlers.delete(h); };

/** The tabs that show Spooler's stock or what depends on it: the Dashboard (spool links follow Spooler's) and Stock. */
const stockShown = () => !s.hidden && (s.tab === 'dash' || s.tab === 'stock');
export function lease(): void {
  const vis = !s.hidden && s.tab === 'dash';
  bridge.post({ type: 'lease', camera: s.camOn && vis, screen: s.scrOn && vis, stock: stockShown() && stockVisible.value });
}

export function start(): () => void {
  bridge.attach();
  const off = bridge.onMessage(onMessage);
  const onVis = () => { s.hidden = document.hidden; lease(); };
  document.addEventListener('visibilitychange', onVis);
  const timers = [
    window.setInterval(lease, 2000),
    window.setInterval(() => { s.now = Date.now(); }, 1000),
    window.setInterval(() => { if (stockShown()) void loadStock(false); }, 5000),
    window.setInterval(() => { if (s.tab === 'dash' && !s.hidden) void loadUsage(); }, 10000),
  ];
  // Spoolman can change from elsewhere (Spooler, Spoolman's own page): re-read the links while the page shows.
  const auto = autoRefresh({ load: () => loadSpools(true), every: () => s.refreshS, held: userBusy, onFailing: f => { s.spoolsRetrying = f; } });
  const offCfg = onConfig(m => { const v = cleanEvery(m.settings?.spoolman_refresh_s); if (v !== s.refreshS) { s.refreshS = v; auto.restart(); } });
  // Spooler says right away when it linked or unlinked a spool (its presence's "links"): re-read without waiting.
  const offLinks = watch(() => s.stock?.spooler?.links, (now, was) => { if (was !== undefined && now !== was) void loadSpools(true); });
  void hello();
  return () => { off(); offCfg(); offLinks(); auto.stop(); document.removeEventListener('visibilitychange', onVis); timers.forEach(clearInterval); };
}
