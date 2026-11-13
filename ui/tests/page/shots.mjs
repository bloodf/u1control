// MOCK evidence: the built page in owned headless Chrome (CSP, scripted bridge), screenshots in light/dark,
// en/pt-BR, 1280/720 px and 200 % zoom, with overflow and DOM measurements. Not a substitute for OrcaSlicer.
//   OUT=<dir> PAGE=<page with icons> node tests/page/shots.mjs
import { writeFile, mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { launch, MOCK_HOST, HELPERS, preparePage } from './cdp.mjs';

const OUT = process.env.OUT; const page = await readFile(process.env.PAGE, 'utf8');
const SETUP = { job: { name: 'Desk organiser — plate 1', time: '2h 04m', weight: 86, plate: 'Plate 1', address: '192.168.1.40' }, purifier: 'auto', auto_purifier: 'weak',
  filaments: [{ index: 0, type: 'PLA', colour: '#e5484d', weight: 50 }, { index: 1, type: 'PETG', colour: '#3e63dd', weight: 36 }],
  heads: [0, 1, 2, 3].map(i => ({ index: i, loaded: i !== 2, type: i === 2 ? '' : 'PLA', vendor: 'Generic', sub_type: 'Basic', colour: ['#e5484d', '#f4cf78', '#888', '#78cfd5'][i] })),
  map: { 0: 0, 1: 1 }, prefs: { bed_level: true, flow_calibrate: true, time_lapse_camera: false }, labels: {} };
const STATE = `
await until(() => __t.sent.find(m => m.type === 'hello'));
const hello = __t.sent.find(m => m.type === 'hello');
const VIEW = {state: 'printing', message: '', filename: 'desk_organiser_plate_1.gcode', progress: 0.37, layer: 142, total_layers: 380, print_duration: 4100, total_duration: 4500,
  extruders: [0,1,2,3].map(i => ({temp: i === 0 ? 219.6 : 25, target: i === 0 ? 220 : 0, active: i === 0})), bed: {temp: 59.8, target: 60},
  heads: ['PLA','PETG','','PLA'].map((t, i) => ({loaded: !!t, type: t, vendor: t ? 'Generic' : '', sub_type: t ? 'Basic' : '', colour: ['#e5484d','#3e63dd','','#78cfd5'][i], official: i === 0})),
  rfid: [{vendor: 'Snapmaker', type: 'PLA', uid: '04A1', official: true}, null, null, null], options: {bed_level: true, flow_calibrate: true, time_lapse_camera: false, unload_when_done: false},
  purifier: {fitted: true}, feed: [{state: 'loaded'},{state: 'loaded'},{state: 'empty'},{state: 'loaded'}], busy: true, machine_state: 'PRINTING', bindings: {'0': 7}, light: true, speed_factor: 1};
if (SCN !== 'notarget') {
  __t.handler({type: 'reply', id: hello.id, result: {firmware: {kind: 'stock', version: '2.0.0.205'}, address: '192.168.1.40', printer: 'Bench U1', generation: 1, limits: {hotend: 320, bed: 110}}});
  __t.handler({type: 'status', data: VIEW});
} else __t.handler({type: 'reply', id: hello.id, error: 'Select a Snapmaker U1 printer, or set "host" in U1 Control’s plugin config.', no_target: true});
await settle();
const ans = (cmd, r) => { const m = [...__t.sent].reverse().find(x => x.type === 'cmd' && x.cmd === cmd); if (m) __t.handler({type: 'reply', id: m.id, result: r}); };
await sleep(50);
ans('spools', {spools: [{id: 7, name: 'Matte Black', vendor: 'Generic', material: 'PLA', colour: '#111111', remaining: 640}, {id: 11, name: 'Cobalt Blue', vendor: 'Acme', material: 'PETG', colour: '#2850a8', remaining: 40}], bindings: {'0': 7}, via: 'direct'});
ans('stock', {spooler: {state: 'active', text: '', version: '0.20.1'}, stock: {state: 'stale', code: 'stale', text: '', key: 's:1', ts: Date.now() / 1000 - 300,
  rows: [{id: 7, name: 'Matte Black', vendor: 'Generic', material: 'PLA', colour: '#111111', colours: [], remaining: 640, low: false, use_first: true, location: 'Shelf A'},
         {id: 11, name: 'Cobalt Blue', vendor: 'Acme', material: 'PETG', colour: '#2850a8', colours: [], remaining: 40, low: true, use_first: false, location: 'Dry box'}]},
  same_spoolman: true, usage: 'u1control', bindings: {'0': 7}});
ans('usage', {pending: [], unconfirmed: [{id: 'a', at: null, spool: 7, grams: 12.5, head: 0, file: 'gcodes/benchy.gcode', error: 'Spoolman timed out', printer: '192.168.1.40', printer_name: 'Bench U1'}],
  acknowledged: [], acknowledged_total: 0, save_error: '', restore_notice: ''});
__t.handler({type: 'config', mode: 'expert', stored: {}, version: '0.4.2', spooler: {installed: true}, settings: {mode: 'expert', host: '', api_key: '••••', printer_name: 'Bench U1', spoolman_url: 'http://192.168.1.10:7912', rfid_auto_sync: true, purifier: 'auto'},
  automations: [{key: 'rfid_auto_sync', label: 'Apply RFID tags', help: 'When a toolhead reads a new tag.', automagic: true, choices: null}, {key: 'purifier', label: 'Top cover', help: 'auto follows the rule.', automagic: 'auto', choices: ['auto','strong','off']}]});
await settle();
if (SCN === 'settings' || SCN === 'files' || SCN === 'console') { document.querySelector('[data-tab="' + SCN + '"]').click(); await sleep(300); }
if (SCN === 'files') { ans('files', {path: 'gcodes', dirs: [{name: 'archive'}], files: [{name: 'desk_organiser_plate_1.gcode', size: 4200000, modified: Date.now()/1000 - 3600, time: 7440}, {name: 'benchy.gcode', size: 900000, modified: Date.now()/1000 - 86400, time: 2700}], disk: {free: 5.2e9}}); }
if (SCN === 'console') { const i = document.querySelector('#console-cmd'); i.value = 'M105'; i.dispatchEvent(new Event('input')); }
if (SCN === 'dialog') { document.querySelector('[data-test="cancel"]').focus(); document.querySelector('[data-test="cancel"]').click(); await until(() => document.querySelector('.p-dialog')); }
await sleep(400);
`;
const SCENES = [
  ['dash', 'light', 'en', 1280, 1], ['dash', 'dark', 'pt_BR', 1280, 1], ['dash', 'light', 'pt_BR', 720, 1], ['dash', 'dark', 'en', 640, 2],
  ['notarget', 'light', 'pt_BR', 1280, 1], ['notarget', 'dark', 'en', 720, 1], ['dialog', 'dark', 'pt_BR', 720, 1], ['dialog', 'light', 'en', 640, 2],
  ['settings', 'light', 'en', 1280, 1], ['settings', 'dark', 'pt_BR', 720, 1], ['files', 'light', 'pt_BR', 1280, 1], ['files', 'dark', 'en', 640, 2],
  ['console', 'dark', 'en', 1280, 1], ['setup', 'light', 'pt_BR', 720, 1], ['setup', 'dark', 'en', 1280, 1], ['setup', 'light', 'en', 360, 2],
];
const dir = await mkdtemp(join(tmpdir(), 'u1-shots-'));
const browser = await launch();
const metrics = [];
try {
  for (const [scn, theme, lang, width, scale] of SCENES) {
    const boot = scn === 'setup' ? { mode: 'setup', version: '0.4.2', lang, data: SETUP } : { mode: 'app', version: '0.4.2', lang };
    const file = join(dir, `${scn}.html`);
    await writeFile(file, preparePage(page, boot));
    const p = await browser.newPage();
    await p.size(width, 900, scale);
    await p.init(MOCK_HOST);
    await p.goto(pathToFileURL(file).href + '?theme=' + theme);
    const m = await p.evaluate(`(async () => { ${HELPERS} const SCN = ${JSON.stringify(scn)};
      await until(() => document.querySelector('#app > *'));
      ${scn === 'setup' ? 'await sleep(300);' : STATE}
      const over = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > innerWidth + 1 && getComputedStyle(e).position !== 'fixed'; })
        .slice(0, 5).map(e => e.tagName + '.' + String(e.className).slice(0, 40));
      const b = document.querySelector('.p-button'); const cs = b ? getComputedStyle(b) : null;
      return { overflowX: document.documentElement.scrollWidth > innerWidth, scrollWidth: document.documentElement.scrollWidth, innerWidth, overflowing: over,
        dom: document.getElementsByTagName('*').length, lang: document.documentElement.lang, dark: document.documentElement.classList.contains('orca-dark'),
        bodyFont: getComputedStyle(document.body).fontSize, buttonRadius: cs && cs.borderRadius, buttonFont: cs && cs.fontSize,
        violations: __t.violations, errors: __t.errors, rejections: __t.rejections }; })()`);
    const name = `MOCK-u1-${scn}-${theme}-${lang}-${width}${scale > 1 ? '-zoom200' : ''}.png`;
    await writeFile(join(OUT, name), await p.screenshot());
    metrics.push({ name, ...m });
    console.log(name, JSON.stringify({ overflowX: m.overflowX, dom: m.dom, lang: m.lang, dark: m.dark }));
    await p.close();
  }
} finally { await browser.close(); await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); }
await writeFile(join(OUT, 'metrics-u1control.json'), JSON.stringify(metrics, null, 2));
if (metrics.some(m => m.overflowX || m.violations.length || m.errors.length || m.rejections.length)) { console.log('PROBLEMS'); process.exit(1); }
console.log('OK');
