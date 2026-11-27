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

export type HeaterPhase = 'heating' | 'target' | 'cooling' | 'off';

/** What a heater is doing, in words for its reading. Unknown reading or target is null, never a guess; within 2 °C is at target. */
export function heaterPhase(temp: number | null | undefined, target: number | null | undefined): HeaterPhase | null {
  if (typeof target !== 'number' || !Number.isFinite(target)) return null;
  if (target <= 0) return 'off';
  if (typeof temp !== 'number' || !Number.isFinite(temp)) return null;
  const d = temp - target;
  return Math.abs(d) <= 2 ? 'target' : d < 0 ? 'heating' : 'cooling';
}

export function parseSpeed(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') return null;
  const v = Number(raw);
  return Number.isFinite(v) && v >= 10 && v <= 300 ? Math.round(v) : null;
}

export const family = (t: unknown): string => ((String(t ?? '').match(/[A-Za-z]+/) || [''])[0]).toUpperCase();

export interface SetupFilament { index: number; type: string; colour?: string; weight?: number; nozzle?: string }
export interface SetupHead { index: number; loaded: boolean; unnamed?: boolean; type: string; vendor?: string; sub_type?: string; colour?: string;
  colours?: string[]; official?: boolean; nozzle?: string }
export type SetupWarning =
  | { id: string; kind: 'empty' | 'unnamed'; f: number; h: number }
  | { id: string; kind: 'material' | 'nozzle'; f: number; h: number; a: string; b: string };

/** Same rules and ids as u1.warning_ids in the plugin, which refuses a send whose warnings weren't acknowledged. */
export function setupWarnings(filaments: SetupFilament[], heads: SetupHead[], map: Record<string, number>): SetupWarning[] {
  const out: SetupWarning[] = [];
  for (const f of [...filaments].sort((a, b) => a.index - b.index)) {
    const h = heads[map[String(f.index)]];
    if (!h) continue;
    if (!h.loaded) { const kind = h.unnamed ? 'unnamed' : 'empty'; out.push({ id: `${kind}:${f.index}:${h.index}`, kind, f: f.index, h: h.index }); }
    else if (family(h.type) !== family(f.type)) out.push({ id: `material:${f.index}:${h.index}`, kind: 'material', f: f.index, h: h.index, a: f.type, b: h.type });
    // u1.nozzle_differs: the slice's nozzle type against the head's (firmware 1.6.0+); unknown on either side never warns
    if (f.nozzle && h.nozzle && f.nozzle !== h.nozzle) out.push({ id: `nozzle:${f.index}:${h.index}`, kind: 'nozzle', f: f.index, h: h.index, a: f.nozzle, b: h.nozzle });
  }
  return out;
}

/** Same 'redmean' distance as u1.colour_distance; unknown colours never count as different (nothing to compare). */
export function colourFar(a: unknown, b: unknown, limit = 150): boolean {
  const rgb = (c: unknown) => { const m = /^#?([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(String(c ?? '').trim()); return m ? [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16)) : null; };
  const x = rgb(a), y = rgb(b);
  if (!x || !y) return false;
  const rm = (x[0] + y[0]) / 2;
  return Math.sqrt((2 + rm / 256) * (x[0] - y[0]) ** 2 + 4 * (x[1] - y[1]) ** 2 + (2 + (255 - rm) / 256) * (x[2] - y[2]) ** 2) > limit;
}

export const warningKey = (w: SetupWarning[]): string => w.map(x => x.id).join(',');

/** Folder choices for "Move": every folder but the current one, the item itself and its subfolders. */
export function moveTargets(folders: string[], path: string, name: string): string[] {
  const src = `${path}/${name}`;
  return folders.filter(f => f !== path && f !== src && !f.startsWith(src + '/'));
}

/** The file root a printer path is under ("gcodes/sub/a.gcode" -> "gcodes"). */
export const rootOf = (path: string): string => path.split('/')[0];

export interface TreeFolder { id: string; name: string; parent: string | null; readonly: boolean }
/** The printer's folders (full paths, a root has no "/") as the file browser's tree, roots in the order given. Every
 *  folder of a read-only root is read only: its files can be looked at, and nothing is moved into it. */
export function folderTree(paths: string[], rootName: (root: string) => string, readOnly: string[] = []): TreeFolder[] {
  const all = new Set<string>();
  // every folder with its parents, so a path listed alone still hangs under its root
  for (const p of paths) for (let at = p.length; at > 0; at = p.lastIndexOf('/', at - 1)) all.add(p.slice(0, at));
  const roots = [...new Set(paths.map(rootOf))];
  return [...all].sort((a, b) => roots.indexOf(rootOf(a)) - roots.indexOf(rootOf(b)) || a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })).map(id => {
    const at = id.lastIndexOf('/');
    return { id, name: at < 0 ? rootName(id) : id.slice(at + 1), parent: at < 0 ? null : id.slice(0, at), readonly: readOnly.includes(rootOf(id)) };
  });
}

/** A file's kind for its chip: "G-code" for a print file, else its extension in capitals ("3MF", "MP4"), or none. */
export function fileKind(name: string): string | undefined {
  const ext = /\.([A-Za-z0-9]{1,5})$/.exec(name)?.[1].toUpperCase();
  return ext && ['GCODE', 'GCO', 'G'].includes(ext) ? 'G-code' : ext;
}

/** Map each bound spool id to its toolhead label ("T2"), preferring the live bindings. */
export function boundHeads(live: Record<string, number>, fromStock: Record<string, number>): Record<number, string> {
  const src = Object.keys(live).length ? live : fromStock;
  return Object.fromEntries(Object.entries(src).map(([h, sid]) => [sid, `T${Number(h) + 1}`]));
}

/** A page language's PrimeVue labels over English. `aria` is merged too, so a label the language lacks stays English. */
export function overEnglish<T extends { aria?: object }>(english: T, own: Partial<T> | undefined): T {
  return { ...english, ...own, aria: { ...english.aria, ...own?.aria } };
}

/** The links as they will be once `spool` is on `head` (null: unlinked); a spool is on one head only. Shown at once, before
 *  the printer and Spoolman have answered. */
export function withLink(bindings: Record<string, number>, head: number, spool: number | null): Record<string, number> {
  const next = Object.fromEntries(Object.entries(bindings).filter(([h, id]) => h !== String(head) && id !== spool));
  return spool ? { ...next, [String(head)]: spool } : next;
}
