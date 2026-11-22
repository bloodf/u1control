import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { fileURLToPath, pathToFileURL } from 'node:url';

// The page sits close to the size OrcaSlicer's WebView2 on Windows still shows (scripts/build.py PAGE_LIMIT), and every
// translation repeats the 800-odd message keys of English. So the build keeps the keys once: each other language ships as
// its texts in English's key order (null where it has none) plus any keys of its own (plural forms), and is rebuilt into
// the same object when the page loads. The sources stay plain objects; this changes only the built page.
const MESSAGES = /[\\/]src[\\/]core[\\/]messages(-\w+)?\.ts$/;
const isTexts = (v: unknown) => !!v && typeof v === 'object' && Object.values(v as object).every(x => typeof x === 'string');
function compactMessages(): Plugin {
  const english = fileURLToPath(new URL('./src/core/messages.ts', import.meta.url));
  return {
    name: 'compact-messages', enforce: 'pre',
    async transform(_code, id) {
      if (!MESSAGES.test(id)) return null;
      const { en } = await import(pathToFileURL(english).href) as { en: Record<string, string> };
      const own = id === english;
      const mod = own ? await import(pathToFileURL(english).href) : await import(pathToFileURL(id).href);
      const keys = Object.keys(en);
      let out = (own ? `export const en = ${JSON.stringify(en)};\n` : `import { en } from './messages';\n`)
        + 'const texts = (values, extra) => { const o = {}; Object.keys(en).forEach((k, i) => { if (values[i] !== null) o[k] = values[i]; }); return Object.assign(o, extra); };\n';
      for (const [name, dict] of Object.entries(mod as Record<string, unknown>)) {
        if (name === 'en') continue;
        if (!isTexts(dict)) throw new Error(`${id}: export ${name} is not a dictionary of texts`);
        const d = dict as Record<string, string>;
        const extra = Object.fromEntries(Object.entries(d).filter(([k]) => !(k in en)));
        out += `export const ${name} = texts(${JSON.stringify(keys.map(k => (k in d ? d[k] : null)))}, ${JSON.stringify(extra)});\n`;
      }
      return { code: out, map: null };
    },
  };
}

// One self-contained page (no CDN, no remote font, no eval). The plugin serves it for the tab and for the
// print setup window; the boot JSON the plugin fills in picks the mode.
export default defineConfig({
  plugins: [compactMessages(), vue(), viteSingleFile({ removeViteModuleLoader: true })],
  // PrimeVue components use Vue's Options API, even when application SFCs use <script setup>.
  define: { __VUE_OPTIONS_API__: true, __VUE_PROD_DEVTOOLS__: false, __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false },
  build: { target: 'safari14', outDir: 'dist', emptyOutDir: true, reportCompressedSize: false },
});
