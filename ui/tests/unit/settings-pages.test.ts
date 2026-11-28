// Settings as pages: every link that opens a settings page names a page (or a group inside one, an older page id) that exists, every page has an id and a label
// in each language, and the narrow layout's Back and the list's "needs fixing" label are translated.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('../../src/', import.meta.url));
const files = (dir: string): string[] => readdirSync(dir).flatMap(n => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]));
const view = readFileSync(join(SRC, 'components/SettingsView.vue'), 'utf8');
const pages = [...view.matchAll(/\{ id: '([a-z-]+)', label: t\('([^']+)'\)/g)].map(m => ({ id: m[1], label: m[2] }));
const sectionIds = new Set([...files(SRC).filter(f => f.endsWith('.vue')).flatMap(f => [...readFileSync(f, 'utf8').matchAll(/<(?:Oui(?:FormSection|Panel)|div)[^>]*\sid="([a-z-]+)"/g)].map(m => m[1]))]);
// HOME: a group's id -> the page holding it
const home = Object.fromEntries([...(view.match(/const HOME[^{]*\{([^}]*)\}/)?.[1] ?? '').matchAll(/'?([a-z-]+)'?: '([a-z-]+)'/g)].map(m => [m[1], m[2]]));
const locales = files(SRC).filter(f => /core[\/\\]messages(-[a-z]+)?\.ts$/.test(f));

test('each settings page is listed once and drawn by one section', () => {
  assert.ok(pages.length >= 5, 'pages found: ' + pages.length);
  assert.equal(new Set(pages.map(p => p.id)).size, pages.length, 'unique ids');
  for (const p of pages) assert.ok(sectionIds.has(p.id), 'a section for ' + p.id);
});

test('every older page id is a group that still exists, inside a page that exists', () => {
  for (const id of ['mode', 'print-setup', 'options', 'calibration', 'connection', 'firmware', 'requirements', 'language', 'about']) {
    const page = home[id] ?? id;
    assert.ok(pages.some(p => p.id === page), id + ' maps to ' + page + ', which is not a page');
    assert.ok(sectionIds.has(id), 'a group with id ' + id);
  }
});

test('every link into Settings opens a page that exists', () => {
  const links = files(SRC).flatMap(f => [...readFileSync(f, 'utf8').matchAll(/openSettings\('([a-z-]+)'\)/g)].map(m => ({ f, id: m[1] })));
  assert.ok(links.length >= 2, 'links found: ' + links.length);
  for (const l of links) assert.ok(pages.some(p => p.id === (home[l.id] ?? l.id)), l.f + ' opens ' + l.id + ', which is not a page');
});

test('page names, Back and the error label are translated in every language', () => {
  assert.ok(locales.length >= 5, 'locale files: ' + locales.length);
  const keys = [...new Set([...pages.map(p => p.label), 'settings.back', 'settings.hasError'])];
  for (const f of locales) {
    const text = readFileSync(f, 'utf8');
    for (const k of keys) {
      const n = text.split("'" + k + "':").length - 1;
      assert.ok(n >= (/[\/\\]messages\.ts$/.test(f) ? 2 : 1), f + ' lacks ' + k);
    }
  }
});
