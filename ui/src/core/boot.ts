// The plugin fills one JSON block before serving the page: the boot payload (mode, version, host language,
// setup data). During `vite dev` it is absent and the defaults apply.
export interface Boot {
  mode: 'app' | 'setup';
  version: string;
  lang: string | null;
  pref?: 'auto' | 'en' | 'pt-BR' | 'es' | 'de' | 'zh-CN' | 'pl' | 'cs';
  theme?: 'auto' | 'light' | 'dark';
  clock?: 'auto' | '24' | '12';
  data?: unknown;
}

function readJson<T>(id: string, fallback: T): T {
  const text = document.getElementById(id)?.textContent?.trim() ?? '';
  if (!text || text.startsWith('__')) return fallback;
  try { return JSON.parse(text) as T; } catch { return fallback; }
}

export const boot: Boot = { mode: 'app', version: 'dev', lang: null, ...readJson<Partial<Boot>>('u1-boot', {}) };
