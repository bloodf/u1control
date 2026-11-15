/** Filament left as 0..1 (null when either weight is unknown). */
export function spoolFraction(remaining: number | null | undefined, initial: number | null | undefined): number | null {
  return typeof remaining === 'number' && typeof initial === 'number' && initial > 0 ? Math.max(0, Math.min(1, remaining / initial)) : null;
}
