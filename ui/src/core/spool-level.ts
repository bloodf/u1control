/** Filament left as 0..1 (null when either weight is unknown). */
export function spoolFraction(remaining: number | null | undefined, initial: number | null | undefined): number | null {
  return typeof remaining === 'number' && typeof initial === 'number' && initial > 0 ? Math.max(0, Math.min(1, remaining / initial)) : null;
}

/** How full a toolhead's spool is drawn: from its linked Spoolman spool, else null (unknown: the full reel with the unknown badge), never a guess.
 *  The U1 reports no amount left: an RFID tag carries the spool's nominal weight, not what is still on it. */
export function headFraction(loaded: boolean | undefined, spool: { remaining?: number | null; initial?: number | null } | null | undefined): number | null {
  return loaded && spool ? spoolFraction(spool.remaining, spool.initial) : null;
}

/** A level bar's colour: red when almost empty (under 5 % of the spool), amber when Spoolman marks it low, else green. */
export const CRITICAL_FRACTION = 0.05;
export function levelTone(fraction: number | null, low?: boolean): 'normal' | 'low' | 'critical' {
  return fraction != null && fraction < CRITICAL_FRACTION ? 'critical' : low ? 'low' : 'normal';
}

/** Filament in the toolhead, named or not: a spool nobody has named reports NONE, but it is not an empty head. */
export function present<T extends { loaded?: boolean; unnamed?: boolean }>(head: T | null | undefined): head is T {
  return !!(head?.loaded || head?.unnamed);
}

/** Feeder states with the filament only at the inlet (e.g. after Unload): nothing in the head to unload. */
export const AT_INLET = ['preload_finish', 'wait_insert', 'unload_finish'];

/** A toolhead with filament in the head itself, that Unload can take out. */
export function unloadable(head: { loaded?: boolean; unnamed?: boolean } | null | undefined, feedState?: string | null): boolean {
  return present(head) && !AT_INLET.includes(feedState || '');
}

/** Every colour of what a toolhead prints with, or null for one colour: its linked Spoolman spool's (when it has a colour),
 *  else the printer's own record of a multi-colour spool (filament_color_multi). */
export function headColours(spool: { colour?: string | null; colours?: string[] } | null | undefined,
  head: { colours?: string[] } | null | undefined): string[] | null {
  const list = spool && (spool.colour || spool.colours?.length) ? spool.colours : head?.colours;
  return list && list.length > 1 ? list : null;
}
