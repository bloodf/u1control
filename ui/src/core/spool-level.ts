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
