/**
 * The spool picture: eight renders of the same spool, from full (1) to an empty reel (8), tinted with the
 * filament colour on the page. These are how much each render shows wound on the reel. Same rule as Spooler.
 */
export const SPOOL_LEVEL_FILL = [1, 0.85, 0.7, 0.55, 0.4, 0.25, 0.08, 0] as const;
export type SpoolLevel = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

/** The render closest to `fraction` (0..1); any filament left is never the bare reel (8). */
export function spoolLevel(fraction: number | null | undefined): SpoolLevel {
  if (fraction == null || !Number.isFinite(fraction) || fraction <= 0) return 8;
  const f = Math.min(1, fraction);
  let best = 0;
  for (let n = 1; n < 7; n++) if (Math.abs(SPOOL_LEVEL_FILL[n] - f) < Math.abs(SPOOL_LEVEL_FILL[best] - f)) best = n;
  return (best + 1) as SpoolLevel;
}

/** Filament left as 0..1 (null when either weight is unknown). */
export function spoolFraction(remaining: number | null | undefined, initial: number | null | undefined): number | null {
  return typeof remaining === 'number' && typeof initial === 'number' && initial > 0 ? Math.max(0, Math.min(1, remaining / initial)) : null;
}

/** CSS paint for a spool: its colour, or its colours side by side. */
export function spoolPaint(colour: string | null | undefined, colours?: string[] | null): string {
  return colours && colours.length > 1
    ? 'linear-gradient(90deg, ' + colours.map((c, i) => `${c} ${(i * 100) / colours.length}% ${((i + 1) * 100) / colours.length}%`).join(', ') + ')'
    : colour || '';
}
