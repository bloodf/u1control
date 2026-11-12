import { icons } from './boot';
/** Sanitized SVG markup from the plugin's own icon files (scripts and handlers rejected at build time). */
export const iconSvg = (name: string): string => icons[name] ?? '';
