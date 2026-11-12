// The plugin fills two JSON blocks before serving the page: the boot payload (mode, version, host language,
// setup data) and the sanitized icon map. During `vite dev` they are absent and the defaults apply.
export interface Boot {
  mode: 'app' | 'setup';
  version: string;
  lang: string | null;
  pref?: 'auto' | 'en' | 'pt-BR';
  data?: unknown;
}

function readJson<T>(id: string, fallback: T): T {
  const text = document.getElementById(id)?.textContent?.trim() ?? '';
  if (!text || text.startsWith('__')) return fallback;
  try { return JSON.parse(text) as T; } catch { return fallback; }
}

export const boot: Boot = { mode: 'app', version: 'dev', lang: null, ...readJson<Partial<Boot>>('u1-boot', {}) };
export const icons: Record<string, string> = readJson('u1-icons', {});
