// What the printer photo shows on each spool holder (no DOM, no Vue): the Spoolman spool linked to the toolhead,
// else the filament the printer reports, else an empty reel. Shared by PrinterFigure and its unit tests.
import { spoolFraction } from './spool-level.ts';
import type { Head, Spool } from '../app/types.ts';

export type ColourName = 'black' | 'white' | 'grey' | 'red' | 'orange' | 'brown' | 'yellow' | 'green' | 'cyan' | 'blue' | 'purple' | 'pink' | 'multi';
export interface FigureSpool {
  /** Toolhead number, 1..4. */ n: number;
  /** Nothing to draw on the reel. */ empty: boolean;
  colour: string | null; /** Multi-colour filament, painted side by side. */ colours: string[] | null;
  /** Filament left, 0..1; null when the weight is unknown. */ fraction: number | null;
  material: string; name: ColourName | null; source: 'spoolman' | 'printer' | 'none';
}

/** '#rgb', '#rrggbb' or '#rrggbbaa' (with or without '#') as [r, g, b] 0..255; null when it isn't a colour. */
export function parseHex(value: string | null | undefined): [number, number, number] | null {
  let h = (value ?? '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(h)) h = [...h].map(c => c + c).join('');
  if (!/^[0-9a-f]{6}([0-9a-f]{2})?$/i.test(h)) return null;
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

/** A plain colour word for a filament colour, for the figure's spoken label. */
export function colourName(value: string | null | undefined): ColourName | null {
  const rgb = parseHex(value);
  if (!rgb) return null;
  const [r, g, b] = rgb.map(v => v / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  if (l < 0.12) return 'black';
  const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (sat < 0.15 || d < 0.08) return l > 0.85 ? 'white' : l < 0.2 ? 'black' : 'grey';
  if (l > 0.94) return 'white';
  const hue = (max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60;
  if (hue < 15 || hue >= 345) return l > 0.7 ? 'pink' : 'red';
  if (hue < 45) return l < 0.4 ? 'brown' : 'orange';
  if (hue < 68) return l < 0.3 ? 'brown' : 'yellow';
  if (hue < 165) return 'green';
  if (hue < 195) return 'cyan';
  if (hue < 260) return 'blue';
  if (hue < 295) return 'purple';
  return 'pink';
}

/** The four spools, T1..T4, from the printer's heads, the Spoolman links (head index -> spool id) and the spool list. */
export function figureSpools(heads: Head[] | undefined, bindings: Record<string, number>, spools: Spool[]): FigureSpool[] {
  return [0, 1, 2, 3].map(i => {
    const head = heads?.[i];
    const id = bindings[String(i)];
    const linked = id != null ? spools.find(x => x.id === id) ?? null : null;
    if (linked && (linked.colour || linked.colours?.length)) {
      const colours = linked.colours && linked.colours.length > 1 ? linked.colours : null;
      const fraction = spoolFraction(linked.remaining, linked.initial);
      return { n: i + 1, empty: fraction === 0, colour: linked.colour || colours?.[0] || null, colours, fraction,
        material: linked.material || head?.type || '', name: colours ? 'multi' : colourName(linked.colour), source: 'spoolman' };
    }
    if (head?.loaded) {
      return { n: i + 1, empty: false, colour: parseHex(head.colour) ? head.colour : null, colours: null, fraction: null,
        material: head.type || '', name: colourName(head.colour), source: 'printer' };
    }
    return { n: i + 1, empty: true, colour: null, colours: null, fraction: null, material: '', name: null, source: 'none' };
  });
}
