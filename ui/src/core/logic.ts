// Pure rules shared by the pages and their unit tests (no DOM, no Vue).
export type TargetInput = { kind: 'empty' } | { kind: 'invalid' } | { kind: 'off' } | { kind: 'heat'; value: number };

/** A blank field is never 0 (U02); 0 typed explicitly means off; anything outside 0..max is refused (B-09). */
export function parseTarget(raw: unknown, max: number): TargetInput {
  if (raw === null || raw === undefined || (typeof raw === 'string' && raw.trim() === '')) return { kind: 'empty' };
  const v = typeof raw === 'number' ? raw : Number(String(raw).replace(',', '.'));
  if (!Number.isFinite(v) || v < 0 || v > max) return { kind: 'invalid' };
  const value = Math.round(v);
  return value === 0 ? { kind: 'off' } : { kind: 'heat', value };
}

export function parseSpeed(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') return null;
  const v = Number(raw);
  return Number.isFinite(v) && v >= 10 && v <= 300 ? Math.round(v) : null;
}

export const family = (t: unknown): string => ((String(t ?? '').match(/[A-Za-z]+/) || [''])[0]).toUpperCase();

export interface SetupFilament { index: number; type: string; colour?: string; weight?: number }
export interface SetupHead { index: number; loaded: boolean; type: string; vendor?: string; sub_type?: string; colour?: string }
export type SetupWarning =
  | { id: string; kind: 'empty'; f: number; h: number }
  | { id: string; kind: 'material'; f: number; h: number; a: string; b: string };

/** Same rules and ids as u1.warning_ids in the plugin, which refuses a send whose warnings weren't acknowledged. */
export function setupWarnings(filaments: SetupFilament[], heads: SetupHead[], map: Record<string, number>): SetupWarning[] {
  const out: SetupWarning[] = [];
  for (const f of [...filaments].sort((a, b) => a.index - b.index)) {
    const h = heads[map[String(f.index)]];
    if (!h) continue;
    if (!h.loaded) out.push({ id: `empty:${f.index}:${h.index}`, kind: 'empty', f: f.index, h: h.index });
    else if (family(h.type) !== family(f.type)) out.push({ id: `material:${f.index}:${h.index}`, kind: 'material', f: f.index, h: h.index, a: f.type, b: h.type });
  }
  return out;
}

export const warningKey = (w: SetupWarning[]): string => w.map(x => x.id).join(',');

/** Folder choices for "Move": every folder but the current one, the item itself and its subfolders. */
export function moveTargets(folders: string[], path: string, name: string): string[] {
  const src = `${path}/${name}`;
  return folders.filter(f => f !== path && f !== src && !f.startsWith(src + '/'));
}

/** Map each bound spool id to its toolhead label ("T2"), preferring the live bindings. */
export function boundHeads(live: Record<string, number>, fromStock: Record<string, number>): Record<number, string> {
  const src = Object.keys(live).length ? live : fromStock;
  return Object.fromEntries(Object.entries(src).map(([h, sid]) => [sid, `T${Number(h) + 1}`]));
}
