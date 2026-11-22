// Behaviour tests of the built U1 Control page (src/u1control/ui/app.html), in owned headless Chrome under a
// host-like CSP, with a scripted OrcaSlicer bridge. Ported from the former fake-DOM harness (tests/ui_harness.js)
// and extended for the review findings (U01-U12, B-01..B-12, X02/X04).
//   node tests/page/run.mjs [name-filter]          PAGE=<built page> EXT_GROUPS=<json> are set by test_ui_page.py
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { launch, MOCK_HOST, HELPERS, preparePage } from './cdp.mjs';
import { SETUP_FULL } from './setup-data.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../../..');

async function builtPage() {
  if (process.env.PAGE) return readFile(process.env.PAGE, 'utf8');
  return execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, "scripts"); import build; sys.stdout.write(build.page_html("app.html"))'],
    { cwd: repo, encoding: 'utf8', maxBuffer: 64 << 20 });
}
// The Extended Firmware settings the scenarios marked needsGroups use. test_ui_page.py passes them; run directly
// (npm run test:page) they come from the same fake, or those scenarios had no settings to find.
const GROUPS = JSON.parse(process.env.EXT_GROUPS ?? execFileSync('python3', ['-c', 'import sys, json; sys.path[:0] = ["src/u1control", "tests"]; '
  + 'import fakes, extended; print(json.dumps(extended.normalize_settings(fakes.ext_settings())))'], { cwd: repo, encoding: 'utf8' }));

const PRELUDE = `
const head = (type, extra) => ({loaded: !!type, type: type || '', vendor: 'Generic', sub_type: 'Basic', colour: '#112233', official: false, ...extra});
const VIEW = extra => ({state: 'standby', message: '', filename: '', progress: 0, extruders: [0, 1, 2, 3].map(i => ({temp: 20, target: 0, active: i === 0})),
  bed: {temp: 20, target: 0}, heads: [0, 1, 2, 3].map(i => head('PLA', {index: i})), rfid: [null, null, null, null], options: {},
  purifier: {fitted: true}, feed: [], busy: false, machine_state: 'IDLE', bindings: {}, light: false, ...extra});
async function connect(kind, gen) {
  await until(() => last('hello'), 'hello sent');
  await reply(last('hello'), {firmware: {kind: kind || 'stock', version: '1'}, address: 'u1:80', printer: 'Bench U1', generation: gen || 1, limits: {hotend: 320, bed: 110}});
}
async function tab(name) { await click(q('[data-tab="' + name + '"]')); }
async function pick(root, label) {
  assert(root, 'select to open'); await reveal(root); root.click(); await until(() => q('.p-select-overlay') && !q('.p-select-overlay[class*="enter-active"]'), 'select overlay open');
  const opt = qa('.p-select-overlay [role=option]').find(o => text(o) === label);
  assert(opt, 'option ' + label + ' in ' + qa('.p-select-overlay [role=option]').map(text).join('|'));
  await mouse(opt); await until(() => !q('.p-select-overlay'), 'overlay closed'); await settle();
}
// Command results are toasts (bottom-left, shared OuiToastHost); the print setup pop-up's warnings are banners.
// A toast that was closed stays in the page for its leave transition: it no longer counts.
const toastText = t => [q('strong', t), q('.oui-toast-body', t)].filter(Boolean).map(text).join(' ');
const toasts = () => qa('.oui-toast:not(.oui-toast-leave-active)').map(toastText).join(' | ');
const alerts = () => [...qa('[role=alert] .oui-banner').map(text), toasts()].filter(Boolean).join(' | ');
const ROWS = [{id: 7, filament_id: 70, name: 'Matte Black', vendor: 'Generic', material: 'PLA', colour: '#111111', colours: [], remaining: 500, low: false, use_first: false, location: 'Shelf A'},
  {id: 11, filament_id: 110, name: 'White', vendor: 'Acme', material: 'PETG', colour: '#FAFAFA', colours: [], remaining: 40, low: true, use_first: true, location: ''}];
const SP = state => ({state, text: state === 'active' ? 'Spooler is running' : 'Spooler was unloaded or disabled.', detail: '', version: '0.21.0', origin: 'http://box:7912'});
const STOCK = extra => ({spooler: SP('active'), stock: {state: 'ok', code: 'ok', text: '', rows: ROWS, key: 's1:3', ts: Date.now() / 1000, origin: 'http://box:7912'},
  same_spoolman: true, usage: 'u1control', bindings: {}, ...extra});
const stockRows = () => qa('[data-stock]');
const REQS = (agents, ext, sm, spooler = 'ok') => [{id: 'printer_agents', status: agents, details: {}},
  {id: 'extended_firmware', status: ext, details: ext === 'unknown' ? {} : {version: '1.0'}},
  {id: 'spoolman', status: sm, details: sm === 'ok' ? {url: 'http://box:7912', via: 'direct'} : {}},
  {id: 'spooler', status: spooler, details: {url: 'https://example.invalid/spooler'}}];
// The Files tab reads both folder trees, then the open folder: answer the trees not yet answered.
const treesAnswered = new Set();
async function trees(gcodes = ['gcodes', 'gcodes/sub'], camera = ['camera']) {
  const waiting = () => cmds('folders').filter(m => !treesAnswered.has(m.id));
  await until(() => waiting().length >= 2, 'both folder trees asked for');
  for (const m of waiting()) { treesAnswered.add(m.id); await reply(m, m.args.root === 'gcodes' ? gcodes : camera); }
}
const reqRow = name => byTest('req-' + name);
const reqStatus = name => text(q('.oui-status', reqRow(name)));
const reqSteps = name => { const el = q('.oui-req-install > span', reqRow(name)); return el ? el.textContent.split('\\n').map(x => x.trim()).filter(Boolean) : []; };
`;

const SETUP_DATA = {
  job: { name: 'part', address: 'u1:80' }, purifier: 'auto', auto_purifier: 'weak',
  filaments: [{ index: 0, type: 'PLA', colour: '#fff' }, { index: 1, type: 'PETG', colour: '#000' }],
  heads: [0, 1, 2, 3].map(i => ({ index: i, loaded: i !== 2, type: i !== 2 ? 'PLA' : '', vendor: 'G', sub_type: 'B', colour: '#123456' })),
  map: { 0: 0, 1: 1 }, prefs: { bed_level: true }, labels: { bed_level: 'Auto bed leveling' },
};

const scenarios = [];
const test = (name, body, opts = {}) => scenarios.push({ name, body, ...opts });

// ------------------------------------------------------------------ ported from test_ui_behaviour.py
test('selection change cancels an open confirmation', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await type(q('#temp-0'), '220');
  await click(q('[data-set="0"]'));
  assert(dialogOpen(), 'heat asks first');
  assert(dialogText().includes('T1') && dialogText().includes('220') && dialogText().includes('Bench U1'), 'names head, °C and printer: ' + dialogText());
  await post({type: 'selection_changed'});
  await until(() => !dialogOpen(), 'dialog closed on printer change');
  eq(cmds('temperature'), [], 'nothing heated');
  eq(qa('.hc').length, 0, 'old toolheads cleared');
`);

test('requests carry the printer generation; heat needs confirmation; blank Set never sends 0', `
  await connect('stock', 7);
  await post({type: 'status', data: VIEW()});
  assert(q('[data-set="bed"]').disabled, 'Set disabled while the field is blank (U02)');
  await type(q('#temp-bed'), '60');
  await click(q('[data-set="bed"]'));
  await no();
  eq(cmds('temperature'), [], 'cancel sends nothing');
  await click(q('[data-set="bed"]'));
  assert(text(q('[data-dlg="yes"]')).includes('60'), 'the confirm button names the value');
  await yes();
  eq(cmds('temperature').map(m => [m.args, m.gen]), [[{heater: 'bed', target: 60}, 7]], 'confirmed heat for generation 7');
  await reply(last('cmd', 'temperature'), true);
  await click(q('[data-off="0"]'));
  assert(!dialogOpen() && cmds('temperature').length === 2, 'Off while idle needs no confirmation');
  await type(q('#temp-1'), '999');
  assert(q('[data-set="1"]').disabled, '999 °C refused before sending (B-09)');
  assert(text(q('#temp-why-1')).includes('320'), 'says the real limit: ' + text(q('#temp-why-1')));
  await type(q('#temp-1'), '');
  assert(q('[data-set="1"]').disabled, 'emptied again: still no Set');
  eq(cmds('temperature').length, 2, 'no command from blank/invalid fields');
`);

test('dialog keeps focus inside and returns it', `
  await connect();
  q('[data-test="estop"]').focus();
  await press('Enter');
  await until(dialogOpen, 'E-stop asks');
  await until(() => dialogEl().contains(document.activeElement), 'focus moves into the dialog');
  for (let i = 0; i < 4; i++) { await press('Tab'); assert(dialogEl().contains(document.activeElement), 'Tab stays inside the dialog'); }
  await press('Tab', true);
  assert(dialogEl().contains(document.activeElement), 'Shift+Tab stays inside');
  eq(dialogEl().getAttribute('role'), 'dialog', 'role'); eq(dialogEl().getAttribute('aria-modal'), 'true', 'modal');
  await press('Escape');
  await until(() => !dialogOpen(), 'Escape cancels');
  await until(() => document.activeElement === q('[data-test="estop"]'), 'focus returns to the E-stop button');
  eq(cmds('emergency_stop'), [], 'cancel sends nothing');
`);

test('editing a tagged head asks before FORCE', `
  await connect();
  await post({type: 'status', data: VIEW({rfid: [null, {vendor: 'Polymaker', type: 'PLA', uid: 'AA'}, null, null]})});
  await click(q('[data-edit="1"]'));
  assert(q('#e1-v') && q('label[for="e1-v"]'), 'labelled fields');
  await click(btn('Save', q('.hc-form')));
  assert(dialogOpen() && dialogText().includes('RFID'), 'asks about the tag');
  await no();
  eq(cmds('set_filament'), [], 'cancel writes nothing');
  await click(btn('Save', q('.hc-form')));
  await yes();
  eq(cmds('set_filament')[0].args.force, true, 'FORCE only after confirming');
  await click(q('[data-edit="2"]'));
  await click(btn('Save', qa('.hc-form').find(f => text(f).includes('T3'))));
  assert(!dialogOpen(), 'untagged head: no question');
  eq(cmds('set_filament')[1].args.force, false, 'untagged head: no FORCE');
`);

test('feeder: a spool unloaded from the head but still in the feeder says so', `
  await connect();
  await post({type: 'status', data: VIEW({feed: [{state: 'preload_finish', detected: true}, {state: 'load_finish', detected: true}, {state: 'wait_insert'}, {}]})});
  await until(() => q('[data-not-in-head="0"]'), 'T1 says it is not in the head');
  eq(qa('[data-not-in-head]').map(e => e.dataset.notInHead), ['0', '2'], 'T1 and T3, not T2');
  const meta = qa('.hc').map(c => qa('.oui-meta', c).map(text).find(x => x.startsWith('Feeder')));
  eq(meta[0], 'Feeder: at the inlet, not in the head', 'feeder line in words, no repeated inlet note');
  eq(meta[1], 'Feeder: in the head', 'no raw state and no inlet note once the filament is in the head');
  eq(meta[2], 'Feeder: waiting for filament', 'T3 waits for filament');
`);

test('park: only the head on the carriage offers Park, and it asks first', `
  await connect();
  await post({type: 'status', data: VIEW()});
  eq(qa('[data-park]').length, 0, 'no Park while every head is in its dock');
  await post({type: 'status', data: VIEW({extruders: [0, 1, 2, 3].map(i => ({temp: 20, target: 0, active: i === 1, picked: i === 1}))})});
  await until(() => q('[data-park="1"]'), 'Park on the picked-up head');
  eq(qa('[data-park]').length, 1, 'only that head');
  await click(q('[data-park="1"]'));
  assert(dialogOpen(), 'asks before moving the head');
  await no();
  eq(cmds('park'), [], 'cancel sends nothing');
  await click(q('[data-park="1"]'));
  await yes();
  eq(cmds('park')[0].args.head, 1, 'parks T2');
  await post({type: 'status', data: VIEW({busy: true, state: 'printing', extruders: [0, 1, 2, 3].map(i => ({temp: 20, target: 0, active: i === 1, picked: i === 1}))})});
  await until(() => !q('[data-park]'), 'no Park while printing');
`);

test('temperatures & fans: chamber, drivers and fan readings; part and aux fan set only when idle', `
  await connect();
  const drivers = [['X', 45, 'ok'], ['Y', null, null], ['Z', null, 'otpw'], ['T1', null, 'ok'], ['T2', null, 'ot'], ['T3', null, null], ['T4', null, null]]
    .map(([name, temp, state]) => ({name, temp, state}));
  await post({type: 'status', data: VIEW({chamber: 38.4, fan: 0.5, aux_fan: 0.25, drivers, purifier: {fitted: true, exhaust: 0.6, inner: 0}})});
  const card = byTest('temps-fans');
  assert(card && text(card).includes('Temperatures & fans'), 'the panel is on the Dashboard');
  const kv = label => { const dt = qa('dt', card).find(d => text(d) === label); return dt ? text(dt.nextElementSibling) : null; };
  eq([kv('Chamber'), kv('X driver'), kv('Y driver'), kv('Z driver'), kv('T1 driver'), kv('T2 driver')],
     ['38 °C', '45 °C', '—', 'Hot (warning)', 'OK', 'Overheated'], 'temperatures and driver states');
  eq([kv('Top cover exhaust fan'), kv('Top cover recirculation fan')], ['60 %', '0 %'], 'top-cover fan readings');
  assert(text(card).includes('50 %') && text(card).includes('25 %'), 'part and aux fan readings');
  const set = id => q('[data-focus-key="tf-' + id + '"]');
  assert(set('part').disabled, 'Set waits for a value');
  await type(q('#tf-part'), '40');
  await click(set('part'));
  eq(cmds('fan').map(m => m.args), [{fan: 'part', percent: 40}], 'part fan sent');
  await reply(last('cmd', 'fan'), true);
  await post({type: 'status', data: VIEW({busy: true, state: 'printing', drivers})});
  await until(() => q('#tf-aux').disabled, 'fan fields off while printing');
  assert(set('aux').disabled && set('aux').getAttribute('aria-describedby') === 'heads-why', 'Set off, pointing at the reason');
  eq(cmds('fan').length, 1, 'nothing more sent');
`);

test('busy machine disables guided commands; unload-when-done is read-only; E-stop stays', `
  await connect();
  await post({type: 'status', data: VIEW({busy: true, machine_state: 'BED_LEVELING', options: {bed_level: true, unload_when_done: true}})});
  for (const sel of ['[data-load="0"]', '[data-unload="0"]', '[data-edit="0"]']) assert(q(sel).disabled, sel + ' disabled while calibrating');
  assert(text(byTest('heads-why')).includes('busy'), 'the reason is visible, not only a tooltip');
  eq(qa('#heads-why').length, 1, 'said once for the four toolheads, not under each card');
  assert(!qa('.hc').some(c => text(c).includes('busy')), 'no copy of the reason inside a card');
  for (const sel of ['[data-load="0"]', '[data-unload="3"]', '[data-edit="2"]']) eq(q(sel).getAttribute('aria-describedby'), 'heads-why', sel + ' points at the reason');
  assert(!q('[data-rfid="0"]').disabled && !q('[data-rfid="0"]').hasAttribute('aria-describedby'), 'busy alone leaves Read RFID on, with no reason attached');
  assert(!q('[data-test="estop"]').disabled, 'E-stop stays available');
  await tab('settings');
  assert(q('[data-cal="bed_mesh"]').disabled && document.body.textContent.includes('Calibration runs when it is idle'), 'calibration blocked, says why');
  assert(q('#pref-unload_when_done').disabled, 'unload_when_done is not sent from this page');
  assert(text(q('#pref-unload_when_done').closest('.oui-formrow')).includes('print setup pop-up'), 'says where to set it');
  await tab('dash');
  if (!q('.hc-pick')) { await until(() => last('cmd', 'spools'), 'spools asked'); await reply(last('cmd', 'spools'), {spools: [{id: 7, name: 'Black', vendor: 'G', material: 'PLA', colour: '#111', remaining: 500, initial: 1000}], bindings: {}, via: 'direct'}); }
  await post({type: 'offline', error: 'timed out'});
  assert(text(byTest('heads-why')).includes('doesn'), 'offline: the shared reason says so: ' + text(byTest('heads-why')));
  for (const sel of ['[data-rfid="1"]', '.hc:nth-child(3) .hc-pick [role=combobox]']) {
    assert(q(sel) && (q(sel).disabled || q(sel).getAttribute('aria-disabled') === 'true'), sel + ' off while offline');
    eq(q(sel).getAttribute('aria-describedby'), 'heads-why', sel + ' points at the reason');
  }
`);

test('the printer photo: spools in the Spoolman colour, else the printer colour, else empty; the active spool lit', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', filename: 'cube.gcode', progress: 0.5, extruders: [0, 1, 2, 3].map(i => ({temp: 20, target: 0, active: i === 1})),
    heads: [head('PLA', {colour: '#00ff00'}), head('PETG', {colour: '#3e63dd'}), head(''), head('PLA', {colour: '#ffffff'})]})});
  await until(() => last('cmd', 'spools'), 'spools asked');
  await reply(last('cmd', 'spools'), {spools: [{id: 7, name: 'Orange', vendor: 'G', material: 'PETG', colour: '#ff7a00', remaining: 250, initial: 1000},
    {id: 12, name: 'Tri', vendor: 'G', material: 'PLA', colour: '#e5484d', colours: ['#e5484d', '#f5d90a', '#3e63dd'], remaining: 900, initial: 1000}], bindings: {'0': 7, '3': 12}, via: 'direct'});
  await settle();
  const fig = q('[data-test="job-card"] [data-test="printer-figure"]');
  assert(fig, 'the printer is shown in the status card');
  assert(!q('[data-test="job-card"] .art-printer'), 'the old icon is gone');
  const reel = n => fig.querySelector('.pf-reel[data-head="' + n + '"]');
  const paint = n => reel(n).style.getPropertyValue('--pf-paint');
  eq([reel(1).dataset.colour, paint(1)], ['#ff7a00', '#ff7a00'], 'T1: the linked Spoolman spool colour');
  eq([reel(2).dataset.colour, paint(2)], ['#3e63dd', '#3e63dd'], 'T2: the printer colour');
  assert(reel(3).hasAttribute('data-empty') && !reel(3).dataset.colour, 'T3: empty reel');
  for (const c of ['#e5484d', '#f5d90a', '#3e63dd']) assert(paint(4).includes(c), 'T4: every colour of a multi-colour spool: ' + paint(4));
  assert(reel(2).hasAttribute('data-active') && !reel(1).hasAttribute('data-active') && fig.querySelector('.pf-halo'), 'the active toolhead spool is lit');
  assert(qa('img', fig).every(i => i.complete && i.naturalWidth > 0), 'photo and light maps load');
  // The toolhead cards' spools: the linked spool's real fill; loaded with no Spoolman spool (amount unknown) the full
  // reel in its colour with the "?" badge, not the empty reel; nothing loaded the bare reel.
  const cardSpool = n => qa('.hc').find(c => text(c.querySelector('.oui-slot-badge')) === 'T' + n).querySelector('.oui-spool');
  const drawn = n => [cardSpool(n).dataset.level, cardSpool(n).hasAttribute('data-unknown'), cardSpool(n).querySelector('.oui-spool-unknown')?.textContent ?? null];
  eq(drawn(1), ['6', false, null], 'T1: 250 of 1000 g left');
  eq(drawn(2), ['1', true, '?'], 'T2: loaded, amount unknown: full reel with the unknown badge');
  eq(drawn(3), ['8', false, null], 'T3: nothing loaded: the bare reel');
  eq(drawn(4), ['2', false, null], 'T4: 900 of 1000 g left');
  eq(fig.getAttribute('role'), 'img');
  eq(fig.getAttribute('aria-label'), 'Printer and spools: T1 orange PETG, T2 blue PETG (in use), T3 empty, T4 multicolour PLA', 'says what each toolhead holds');
  await post({type: 'offline', error: 'timed out'});
  await until(() => q('[data-test="printer-figure"][data-stale]'), 'last known values');
  const old = q('[data-test="printer-figure"]');
  assert(!old.querySelector('.pf-halo') && !old.getAttribute('aria-label').includes('(in use)'), 'stale: no spool lit, nothing said in use');
  await post({type: 'status', data: VIEW()});
  await settle();
  const idle = q('[data-test="job-card"] [data-test="printer-figure"]');
  assert(idle && !idle.querySelector('.pf-halo'), 'idle: still shown, no spool lit');
  assert(!idle.getAttribute('aria-label').includes('(in use)'), 'idle: no toolhead in use');
`);

test('thumbnails only for visible rows, two at a time, dropped on folder change', `
  await connect();
  await tab('files');
  await trees();
  await until(() => last('cmd', 'files'), 'files listed');
  const files = Array.from({length: 500}, (_, i) => ({name: 'f' + i + '.gcode', size: 1, modified: 500 - i, time: 60, thumb: '.thumbs/f' + i + '-300x300.png'}));
  await reply(last('cmd', 'files'), {path: 'gcodes', dirs: [{name: 'sub'}], files, disk: {free: 2e9}});
  await sleep(200);
  const asked = cmds('thumbnail');
  eq(asked.length, 2, 'two at a time');
  eq(asked[0].args, {path: 'gcodes/f0.gcode', thumb: '.thumbs/f0-300x300.png'}, 'listing thumb reused');
  await reply(asked[0], 'data:image/png;base64,AA');
  await until(() => cmds('thumbnail').length === 3, 'next one after a reply');
  const old = cmds('thumbnail')[1];
  await click(q('[data-folder="gcodes/sub"]'));
  eq(last('cmd', 'files').args.path, 'gcodes/sub', 'opened the folder');
  await reply(old, 'data:image/png;base64,BB');
  await reply(cmds('thumbnail')[2], 'data:image/png;base64,CC');
  await sleep(100);
  eq(cmds('thumbnail').length, 3, "the old folder's queue was dropped");
  assert(cmds('thumbnail').length < 50, 'never asks for every row');
`);

test('extended settings render the release format and an unfinished log is not Applied', `
  await connect('extended');
  await until(() => last('cmd', 'spools'));
  await reply(last('cmd', 'spools'), {spools: [], bindings: {}, via: 'direct'});
  await tab('settings');
  await until(() => last('cmd', 'ext_settings'), 'firmware settings asked');
  await reply(last('cmd', 'ext_settings'), {status: {Version: 'x'}, settings: GROUPS});
  const body = text(q('#fw-h').closest('section'));
  assert(body.includes('SSH Access') && body.includes('Remote Access') && body.includes('Remote Screen'), 'items and group labels shown: ' + body);
  assert(!body.includes('Debug only'), 'hidden setting left out');
  const sel = q('#ext-l-spoolman').closest('.fw-item').querySelector('.p-select');
  sel.click(); await until(() => q('.p-select-overlay') && !q('.p-select-overlay[class*="enter-active"]'));
  eq(qa('.p-select-overlay [role=option]').map(text), ['Enabled', 'Disabled'], 'hidden option left out');
  await mouse(qa('.p-select-overlay [role=option]')[0]); await until(() => !q('.p-select-overlay')); await settle();
  await click(btn('Apply Spoolman Integration'));
  await until(dialogOpen);
  assert(dialogText().includes('Spoolman URL'), 'asks the input the firmware declares');
  await until(() => document.activeElement === q('#dlg-input'), 'the field has focus');
  await type(q('#dlg-input'), 'http://10.0.0.2:7912');
  assert(q('#dlg-input').value === 'http://10.0.0.2:7912' && !q('[data-dlg="yes"]').disabled, 'typed: ' + q('#dlg-input').value);
  await yes();
  await until(dialogOpen);
  assert(dialogText().includes('Enable Spoolman integration?'), "shows the firmware's own confirmation");
  await yes();
  const set = last('cmd', 'ext_set');
  eq(set.args, {setting_id: 'spoolman', value: 'enabled', inputs: {SPOOLMAN_URL: 'http://10.0.0.2:7912'}}, 'inputs sent');
  await reply(set, {ok: null, log: 'Applying changes...\\n', error: "the printer didn't report how this ended"});
  assert(alerts().includes('Result unknown'), 'an unfinished log is not Applied: ' + alerts());
`, { needsGroups: true });

test('settings: Open Filament Database is off by default; on and saved, its list line and Read again', `
  await connect();
  const config = {type: 'config', mode: 'automagic', stored: {}, version: 't', spooler: {installed: true}, automations: [],
    settings: {mode: 'automagic', host: '', api_key: '', printer_name: 'Bench U1', spoolman_url: '', ofd_enabled: false}};
  await post(config);
  await tab('settings');
  await until(() => q('.oui-settings-link[data-section="connection"]'), 'settings shown');
  await click(q('.oui-settings-link[data-section="connection"]'));
  await until(() => q('#ofd-on'), 'the OFD row');
  assert(!q('#ofd-on').checked && !byTest('ofd-state'), 'off by default, nothing more shown');
  await click(q('#ofd-on'));
  await until(() => byTest('ofd-state'), 'turned on');
  assert(text(byTest('ofd-state')).includes('Save to turn it on') && text(byTest('ofd-state')).includes('MIT'), 'saved first; the licence is named: ' + text(byTest('ofd-state')));
  assert(!last('ofd'), 'nothing asked before the save');
  await click(byTest('save'));
  eq(last('save_settings').settings.ofd_enabled, true, 'saved on');
  await reply(last('save_settings'), {saved: true});
  await post({...config, settings: {...config.settings, ofd_enabled: true}});
  await until(() => last('ofd'), 'once saved on, the line asks for the kept list');
  await reply(last('ofd'), {on: true, fetched: 1795371399, version: '2026.11.22', count: 2133, stale: false, error: ''});
  await until(() => text(byTest('ofd-state')).includes('2133'), 'the list line: ' + text(byTest('ofd-state')));
  await click(byTest('ofd-refresh'));
  eq(last('ofd').refresh, true, 'Read again asks OFD now');
`);
test('toolhead cards: an Open Filament Database proposal is marked untuned; picking it installs it by its id', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await until(() => last('preset_matches'), 'asked');
  await reply(last('preset_matches'), {matches: [{head: 0, name: 'Generic PLA @U1', source: 'auto', score: 35, reasons: [['material', 'PLA']], confident: true, remembered_key: '',
    candidates: [{name: 'Generic PLA @U1', score: 35, reasons: [['material', 'PLA']]}],
    ofd: [{id: 'f667', name: 'Polymaker Panchroma Matte PLA (OFD)', score: 58, reasons: [['material', 'PLA'], ['vendor', 'Polymaker']]}]}]});
  await until(() => q('[data-match="0"]'), 'T1 line');
  await click(q('.oui-match-change', q('[data-match="0"]')));
  await until(() => qa('.oui-match-option', q('[data-match="0"]')).length === 2, 'the candidate and the proposal');
  const ofdRow = qa('.oui-match-option', q('[data-match="0"]'))[1];
  assert(text(ofdRow).includes('OFD, untuned') && !ofdRow.disabled, 'marked and pickable: ' + text(ofdRow));
  await click(ofdRow);
  eq([last('preset_pick').head, last('preset_pick').ofd], [0, 'f667'], 'installed by its OFD id');
  await reply(last('preset_pick'), {matches: [], note: 'Spooler puts it into its preset of spool #7 on its next sync'});
  await until(() => toasts().includes('spool #7'), 'the note is shown: ' + toasts());
`);

test('settings draft survives mode switch; Saved needs the plugin answer', `
  await connect();
  const config = {type: 'config', mode: 'automagic', stored: {}, version: 't', spooler: {installed: true},
    settings: {mode: 'automagic', host: '', api_key: '', printer_name: 'Bench U1', spoolman_url: '', rfid_auto_sync: false, purifier: 'auto'},
    automations: [{key: 'rfid_auto_sync', label: 'RFID sync', help: 'h', automagic: true, choices: null},
                  {key: 'purifier', label: 'Top cover', help: 'h', automagic: 'auto', choices: ['auto', 'off']}]};
  await post(config);
  await tab('settings');
  await click(q('[data-mode="expert"]'));
  await click(q('#auto-rfid_auto_sync'));
  assert(document.body.textContent.includes('Unsaved changes'), 'unsaved change shown');
  await click(q('[data-mode="automagic"]'));
  await click(q('[data-mode="expert"]'));
  assert(q('#auto-rfid_auto_sync').checked, 'draft kept across Automagic/Expert');
  await click(byTest('save'));
  const save = last('save_settings');
  eq([save.settings.mode, save.settings.rfid_auto_sync], ['expert', true], 'draft sent');
  assert(!document.body.textContent.includes('Settings saved'), 'no Saved before the answer');
  await fail(save, 'disk full');
  assert(alerts().includes('Not saved') && alerts().includes('disk full'), 'failure shown and kept');
  assert(q('#auto-rfid_auto_sync').checked, 'typed value kept after a failure');
  await click(byTest('save'));
  const again = last('save_settings');
  await post({...config, mode: 'expert', settings: {...config.settings, mode: 'expert', rfid_auto_sync: true}, stored: {rfid_auto_sync: true}});
  await reply(again, {saved: true});
  assert(document.body.textContent.includes('Settings saved'), 'Saved after the answer');
  assert(!document.body.textContent.includes('Unsaved changes'), 'nothing pending after saving');
  eq(q('#c-key').type, 'password', 'API key masked');
`);

test('console routes M112 to the urgent path and shows replies', `
  await connect();
  await type(q('#console-cmd'), 'm112');
  await press('Enter');
  await until(dialogOpen, 'M112 asks like the E-stop button');
  assert(btn('Stop now (E-stop)', dialogEl()), 'explicit confirm label');
  await yes();
  eq(cmds('emergency_stop').length, 1, 'urgent path');
  eq(cmds('gcode'), [], 'not queued as G-code');
  await type(q('#console-cmd'), 'M105');
  await press('Enter');
  await until(() => last('cmd', 'gcode'));
  await reply(last('cmd', 'gcode'), {ok: true, output: ['ok T0:21.0 /0.0'], note: 'replies since'});
  const log = text(q('[role=log]'));
  assert(log.includes('accepted') && log.includes('T0:21.0'), log);
`);

const SETUP_BUSY = { ...SETUP_FULL, printer: { ...SETUP_FULL.printer, busy: true } };
test('setup: the print, the printer, a card per filament with its head, spool and the preview', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  eq(text(byTest('job-meta')), '2h 12m 34s · 26.4 g', 'time and weight');
  eq(text(byTest('job-meta2')), '175 layers · 522 tool changes', 'layers and tool changes');
  const line = text(byTest('printer'));
  assert(line.includes('Snapmaker U1') && line.includes('192.168.1.40') && line.includes('Ready'), 'printer: ' + line);
  eq(qa('.su-card').length, 4, 'one card per filament');
  const c0 = q('.su-card[data-f="0"]');
  assert(text(c0).includes('[1]') && text(c0).includes('PETG') && text(c0).includes('Head 1') && text(c0).includes('Generic Leaf Green'), 'card 1: ' + text(c0));
  eq(getComputedStyle(c0.querySelector('.hp-strand')).stroke, 'rgb(108, 191, 90)', 'strand in the Spoolman colour');
  eq(getComputedStyle(q('.su-card[data-f="3"] .hp-strand')).stroke, 'rgb(245, 158, 11)', 'no spool: the printer colour');
  assert(byTest('preview') && byTest('preview').getAttribute('aria-label').includes('Top view'), 'preview drawn');
  assert(byTest('prefs') && byTest('flow-more') && byTest('cover-more'), 'extra controls offered');
  assert(!alerts() && !byTest('send').disabled && text(byTest('send')) === 'Apply & continue', 'nothing to confirm');
  await click(byTest('send'));
  const s0 = __t.submits[0];
  eq(s0.map, {0: 0, 1: 2, 2: 1, 3: 3}, 'map');
  eq([s0.prefs.tangle_level, s0.prefs.exhaust_fan, s0.remember], ['medium', 60, true], 'prefs as offered');
`, { mode: 'setup', data: SETUP_FULL });

test('setup: a control the printer lacks is not shown', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  assert(!byTest('prefs') && !byTest('flow-more') && !q('#su-p-flow_calibrate') && !q('#su-p-time_lapse_camera') && !byTest('preview'), 'only what was offered');
  assert(q('#su-p-bed_level'), 'bed leveling offered');
  await click(byTest('cover-more'));
  await until(() => byTest('cover-pop'), 'cover popover');
  assert(!byTest('exhaust-mode') && !byTest('inner-mode'), 'no fan control without the command');
`, { mode: 'setup' });

test('setup: choose a head on the card; another material needs a confirmation tied to the mapping', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  const card = () => q('.su-card[data-f="1"]');
  card().focus();
  await press('Enter');
  await until(() => q('.su-pick'), 'head picker open');
  await until(() => document.activeElement && document.activeElement.matches('.su-pick-head'), 'focus in the picker');
  await click(q('.su-pick-head[data-pick="2"]'));            // PETG -> empty T3
  await until(() => !q('.su-pick'), 'picker closed');
  eq(card().dataset.t, '2', 'mapped to T3');
  assert(document.activeElement === card(), 'focus back on the card');
  assert(alerts().includes('T3'), 'warning announced: ' + alerts());
  assert(byTest('card-warn'), 'warning sign on the card');
  assert(byTest('send').disabled, 'send waits for the confirmation');
  await click(q('#su-ack'));
  assert(!byTest('send').disabled && text(byTest('send')).includes('warning'), 'says it sends with a warning');
  await click(card()); await until(() => q('.su-pick'), 'open again');
  await click(q('.su-pick-head[data-pick="3"]'));            // PETG -> PLA T4: another warning set
  assert(!q('#su-ack').checked && byTest('send').disabled, 'a new warning needs a new confirmation');
  assert(document.body.textContent.includes('previous check'), 'says why the box was cleared');
  await click(q('#su-ack'));
  await click(byTest('send'));
  eq(__t.submits.map(m => m.acknowledged), [['material:1:3']], 'sends the ids it confirmed');
  await click(byTest('send'));
  eq(__t.submits.length, 1, 'a second click does not send twice');
`, { mode: 'setup' });

test('setup: the Print dialog\'s slots survive a toolhead refresh; Auto map still re-picks', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  const before = qa('.su-card').map(c => c.dataset.t);
  await post({heads: ${JSON.stringify(SETUP_FULL.heads)}, busy: false, map: {0: 3, 1: 3, 2: 3, 3: 3}});
  eq(qa('.su-card').map(c => c.dataset.t), before, 'a refresh keeps the slots picked in OrcaSlicer');
  await click(byTest('automap'));
  await post({heads: ${JSON.stringify(SETUP_FULL.heads)}, busy: false, map: {0: 3, 1: 3, 2: 3, 3: 3}});
  eq(q('.su-card[data-f="0"]').dataset.t, '3', 'Auto map replaces them');
`, { mode: 'setup', data: {...SETUP_FULL, keep_map: true} });

test('setup: a busy printer locks the settings and Apply', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  assert(text(byTest('busy')).includes('can’t change during a print'), 'busy notice: ' + text(byTest('busy')));
  assert(byTest('send').disabled && q('.su-card').disabled && byTest('prefs').disabled && q('#su-p-bed_level').disabled, 'locked');
  assert(text(q('#su-why')).includes('busy'), 'why');
  await post({heads: ${JSON.stringify(SETUP_FULL.heads)}, busy: false, map: {}});
  assert(!byTest('busy') && !byTest('send').disabled && !q('.su-card').disabled, 'unlocked when ready');
`, { mode: 'setup', data: SETUP_BUSY });

test('setup: auto mapping, plugin settings, print preferences and the top-cover fans', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  await click(q('.su-card[data-f="0"]')); await until(() => q('.su-pick'));
  await click(q('.su-pick-head[data-pick="3"]'));
  await click(byTest('automap'));
  assert(sent().some(m => m.refresh), 'asks the plugin to match again');
  await post({heads: ${JSON.stringify(SETUP_FULL.heads)}, busy: false, map: {0: 0, 1: 2, 2: 1, 3: 3}});
  eq(q('.su-card[data-f="0"]').dataset.t, '0', 'auto mapping replaces a hand choice');
  await click(byTest('plugin-settings'));
  assert(sent().some(m => m.open_settings), 'asks the tab to open Settings');
  await click(byTest('prefs'));
  await until(() => byTest('prefs-dialog'), 'preferences dialog');
  assert(text(byTest('prefs-dialog')).includes('Air printing'), 'tangle detection named as air printing');
  eq(qa('[data-level="spaghetti_level"] [role=radio], [data-level="spaghetti_level"] button').length, 2, 'spaghetti: low/high only');
  await click([...qa('[data-level="tangle_level"] button')].find(b => text(b) === 'High'));
  await click(btn('Close', q('.p-dialog')));
  await until(() => !q('.p-dialog'), 'dialog closed');
  await click(byTest('cover-more')); await until(() => byTest('exhaust-mode'), 'exhaust control in a cooling mode');
  assert(!byTest('inner-mode'), 'no recirculation fan outside keep warm');
  await click([...qa('[data-test="exhaust-mode"] button')].find(b => text(b) === 'Off'));
  await click(byTest('send'));
  const s0 = __t.submits[0];
  eq([s0.prefs.tangle_level, s0.prefs.exhaust_fan], ['high', 0], 'chosen preferences sent');
`, { mode: 'setup', data: SETUP_FULL });

test('setup: Heads settings ask before overwriting a tagged spool; a set fan speed of 60 % stays set', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  await click(byTest('heads'));
  await until(() => last('cmd', 'spools'), 'spools asked');
  await reply(last('cmd', 'spools'), {spools: [{id: 7, vendor: 'Generic', name: 'Matte Black', material: 'PLA', colour: '#111111'}], bindings: {}});
  await click(q('[data-head="1"] button[type="submit"]'));     // T2 holds an official spool
  await until(dialogOpen, 'asks first');
  eq(cmds('set_filament'), [], 'nothing sent before the answer');
  await no();
  eq(cmds('set_filament'), [], 'nothing sent on Go back');
  await click(q('[data-head="1"] button[type="submit"]'));
  await until(dialogOpen, 'asks again');
  await yes();
  await until(() => cmds('set_filament').length, 'sent after yes');
  eq(cmds('set_filament')[0].args.force, true, 'force only after the confirmation');
  await click(q('[data-head="0"] button[type="submit"]'));     // not tagged: no question, no force
  await until(() => cmds('set_filament').length === 2, 'second save');
  eq(cmds('set_filament')[1].args.force, false, 'no force');
  await click(q('[data-head="2"] button[type="submit"]'));     // an RFID tag the head read: asks too
  await until(dialogOpen, 'asks for a read tag');
  await yes();
  await until(() => cmds('set_filament').length === 3, 'third save');
  eq(cmds('set_filament')[2].args.force, true, 'force after yes');
  await click(byTest('cover-more')); await until(() => byTest('exhaust-mode'));
  await click([...qa('[data-test="exhaust-mode"] button')].find(b => text(b) === 'Set'));
  assert(q('.su-slider'), 'slider shown');
  const range = q('.su-slider input[type=range]');
  assert(range, 'the slider is a native range input (keyboard and screen readers)');
  range.value = '60'; range.dispatchEvent(new Event('input', {bubbles: true}));
  await settle();
  assert(q('.su-slider') && text(q('.su-slider')).includes('60'), 'still Set at 60 %: ' + text(q('.su-slider') || document.body));
`, { mode: 'setup', data: { ...SETUP_FULL, tags: [false, false, true, false] } });

test('setup: keep warm hides the exhaust fan and never sends it', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  await click(byTest('cover-more')); await until(() => byTest('cover-pop'));
  assert(text(byTest('exhaust-blocked')).includes('stays off'), 'says why: ' + text(byTest('exhaust-blocked')));
  assert(byTest('inner-mode'), 'recirculation fan in keep warm');
  await click(byTest('send'));
  assert(!('exhaust_fan' in __t.submits[0].prefs) && __t.submits[0].prefs.inner_fan === 60, 'exhaust left out');
`, { mode: 'setup', data: { ...SETUP_FULL, purifier: 'keep-warm' } });

test('setup: remembers on request and in Portuguese at 380 px', `
  await until(() => sent().some(m => m.ready), 'ready posted');
  eq(text(byTest('send')), 'Aplicar e continuar', 'pt-BR');
  assert(document.documentElement.scrollWidth <= innerWidth, 'no horizontal scroll: ' + document.documentElement.scrollWidth);
  await click(q('#su-remember'));
  await click(byTest('send'));
  eq(__t.submits.map(m => m.remember), [false], 'sends the remember choice');
`, { mode: 'setup', data: SETUP_FULL, lang: 'pt_BR', size: [380, 900] });

test('stock: without Spooler the tab stays, says why in one row and asks for no stock lease', `
  await connect();
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), {spooler: {...SP('absent'), text: "Spooler isn't running"}, stock: {state: 'unavailable', rows: [], key: ''}, same_spoolman: null, usage: 'u1control', bindings: {}});
  assert(q('[data-tab="stock"]') && !q('[data-tab="stock"] .oui-appbar-count'), 'the Stock tab stays, with no count');
  await tab('stock');
  assert(!stockRows().length && !q('.sc-table') && text(byTest('stock-card')).includes('Spooler isn’t running'), 'solo U1 Control: one row saying why, no list: ' + text(byTest('stock-card')));
  await sleep(2100);
  eq(last('lease').stock, false, 'no stock lease without Spooler');
`);

test('stock: without Spooler\'s list the tab lists U1 Control\'s own Spoolman and links from it', `
  await connect('stock', 4);
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), {spooler: SP('absent'), stock: {state: 'ok', code: 'own', text: '', rows: ROWS, key: 'spoolman:http://box:7912', origin: 'http://box:7912', source: 'spoolman'}, same_spoolman: null, usage: 'u1control', bindings: {}});
  eq(text(q('[data-tab="stock"] .oui-appbar-count')), '2', 'the Stock tab counts the spools');
  await tab('stock');
  eq(stockRows().length, 2, 'the spools are listed, not a wait for Spooler');
  assert(text(byTest('stock-own')).includes('straight from Spoolman'), 'says where the list comes from');
  assert(!text(byTest('stock-about')).includes('through the printer'), 'not read through the printer');
  await click(q('[data-stock="7"]'));
  await yes();
  eq(cmds('stock_assign').map(m => m.args.key), ['spoolman:http://box:7912'], 'links with the own list key');
`);

test('stock: with no Spoolman anywhere the tab says what to set, with the way to Settings', `
  await connect();
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), {spooler: SP('absent'), stock: {state: 'error', code: 'no_spoolman', text: 'x', rows: [], key: '', source: 'spoolman'}, same_spoolman: null, usage: 'u1control', bindings: {}});
  await tab('stock');
  assert(text(byTest('stock-card')).includes('has no Spoolman address'), 'says no address is set: ' + text(byTest('stock-card')));
  assert(!text(byTest('stock-card')).includes('Waiting'), 'no wait');
  await click(byTest('stock-settings'));
  await until(() => q('[aria-labelledby="oui-tab-settings"]')?.checkVisibility());
`);

test('stock lists, filters and links with the list key and printer generation', `
  await connect('stock', 4);
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
  assert(!byTest('stock-card').checkVisibility() && !q('[aria-labelledby="oui-tab-dash"] [data-stock]'), 'the stock is not on the Dashboard');
  eq(text(q('[data-tab="stock"] .oui-appbar-count')), '2', 'the Stock tab counts the spools');
  await sleep(2100);
  eq(last('lease').stock, true, 'the Dashboard keeps the stock lease: its spool links follow Spooler');
  await tab('stock');
  const page = q('[aria-labelledby="oui-tab-stock"]');
  assert(byTest('stock-card').checkVisibility(), 'list shown while Spooler runs');
  assert(text(q('.oui-pagehead-title', page)).includes('Stock (Spooler)'), 'named as stock of Spooler (X02)');
  eq(stockRows().length, 2, 'both spools listed');
  assert(text(byTest('stock-about')).includes('recorded in Spoolman by U1 Control'), 'says who records filament use, behind the (i)');
  assert(!qa('p', page).some(e => text(e).includes('recorded in Spoolman')), 'no helper paragraph under the list');
  await type(q('input[type=search]', page), 'white');
  eq(stockRows().length, 1, 'search filters');
  await type(q('input[type=search]', page), '');
  await pick(q('[aria-label="Material"]').closest('.p-select') || q('[aria-label="Material"]'), 'PLA');
  eq(stockRows().map(b => b.dataset.stock), ['7'], 'material filter');
  eq(byTest('stock-head').getAttribute('role'), 'radiogroup', 'the link target is a list of the four toolheads');
  eq(qa('[data-stock-target]').map(b => [text(b.querySelector('.oui-slot-badge')), b.getAttribute('aria-checked')]), [['T1', 'true'], ['T2', 'false'], ['T3', 'false'], ['T4', 'false']], 'T1 chosen at first');
  q('[data-stock-target="0"]').focus();
  await press('ArrowDown');
  eq(qa('[data-stock-target]').map(b => b.getAttribute('aria-checked')), ['false', 'true', 'false', 'false'], 'arrow keys move the choice');
  eq(document.activeElement.dataset.stockTarget, '1', 'and the keyboard with it');
  assert(text(q('label[for="stock-fit"]')).includes('T2'), 'the same-material filter names the chosen toolhead');
  const b7 = q('[data-stock="7"]');
  eq(text(b7), 'Link to T2', 'the button names the full target (U07)');
  assert(b7.getAttribute('aria-label').includes('T2'), 'accessible name names the toolhead');
  await click(b7);
  assert(dialogText().includes('T2') && dialogText().includes('Bench U1'), 'asks first, naming head and printer');
  await no();
  eq(cmds('stock_assign'), [], 'cancel sends nothing');
  await click(q('[data-stock="7"]'));
  await yes();
  eq(cmds('stock_assign').map(m => [m.args, m.gen]), [[{head: 1, spool_id: 7, key: 's1:3', force: false}, 4]], 'one link, keyed');
  await reply(last('cmd', 'stock_assign'), {bindings: {'1': 7}});
  await until(() => q('[data-linked="7"]'), 'the spool now in T2 says so instead of offering the same link');
  eq([text(q('[data-linked="7"]')), !!q('[data-stock="7"]')], ['Linked', false], 'Linked, no button');
  eq(text(q('.sc-table .oui-slot-badge')), 'T2', 'and its row carries the toolhead badge');
  await click(q('[data-stock-target="0"]'));
  eq(text(q('[data-stock="7"]')), 'Link to T1', 'another target: the link is offered again');
`);

test('stock: a tagged head needs FORCE confirmation', `
  await connect();
  await post({type: 'status', data: VIEW({rfid: [{uid: 'AA'}, null, null, null]})});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
  await tab('stock');
  await click(q('[data-stock="11"]'));
  assert(dialogText().includes('RFID'), 'warns about the tag');
  await yes();
  eq(cmds('stock_assign')[0].args.force, true, 'FORCE only after that confirmation');
`);

test('stock: a late answer for the previous printer is dropped, older answers never replace newer', `
  await connect('stock', 1);
  await until(() => last('cmd', 'stock'));
  const before = last('cmd', 'stock');
  await post({type: 'selection_changed'});
  await reply(before, STOCK({bindings: {'0': 7}}));
  await tab('stock');
  assert(!stockRows().length && !q('.sc-table'), 'an answer asked before the printer changed is not shown');
  await connect('stock', 2);
  await until(() => cmds('stock').length >= 2);
  await reply(last('cmd', 'stock'), STOCK());
  assert(stockRows().length === 2 && !q('.sc-table .oui-slot-badge') && !q('[data-linked]'), 'only the new answer counts');
  await click(btn('Refresh stock'));
  const a = last('cmd', 'stock');
  await click(btn('Refresh stock'));
  await reply(last('cmd', 'stock'), STOCK());
  await reply(a, STOCK({stock: {...STOCK().stock, rows: ROWS.slice(0, 1)}}));
  eq(stockRows().length, 2, 'an older answer arriving late never replaces a newer one');
`);

test('stock: other Spoolman, stale and stopped states, each with its own severity', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK({same_spoolman: false}));
  await tab('stock');
  assert(stockRows().every(b => b.disabled), 'no link from another Spoolman');
  assert(q('.sc-notes .oui-banner[data-tone="danger"]') && text(q('.sc-notes .oui-banner[data-tone="danger"]')).includes('different Spoolman'), 'blocking reason as an error');
  assert(text(byTest('stock-why')).includes('Linking unavailable'), 'visible reason (U06)');
  await click(btn('Refresh stock'));
  eq(last('cmd', 'stock').args, {refresh: true}, 'Refresh asks Spooler for a new list');
  await reply(last('cmd', 'stock'), STOCK({stock: {...STOCK().stock, state: 'stale', ts: Date.now() / 1000 - 600}}));
  const stale = byTest('stock-stale');
  assert(stale && stale.dataset.state === 'stale' && stale.closest('.oui-pagehead') && text(stale).includes('read') && stockRows().length === 2, 'stale list stays; the page header says its age as a stale state');
  assert(text(byTest('stock-about')).includes('out of date'), 'what stale means is behind the (i)');
  assert(!q('[data-test="stock-card"] [data-tone="danger"], [data-test="stock-card"] [data-state="error"]'), 'stale is not shown as an error (U09)');
  await click(btn('Refresh stock'));
  await reply(last('cmd', 'stock'), STOCK({spooler: SP('stopped'), stock: {state: 'unavailable', rows: [], key: '', text: 'x'}}));
  assert(byTest('stock-card') && !stockRows().length && text(byTest('stock-card')).includes('unloaded'), 'stopped Spooler explained');
  await click(btn('Refresh stock'));
  await fail(last('cmd', 'stock'), 'the selected printer changed; nothing was sent to it');
  assert(q('[data-test="stock-card"] .oui-empty[data-state="error"]') && text(byTest('stock-card')).includes('printer changed'), 'errors are shown, not swallowed');
`);

test('stock: busy printer disables links with a visible reason; refresh keeps focus', `
  await connect();
  await post({type: 'status', data: VIEW({busy: true, state: 'printing'})});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
  await tab('stock');
  assert(stockRows().every(b => b.disabled), 'busy printer: no link');
  assert(text(q('#heads-why')).includes('busy') && stockRows().every(b => b.getAttribute('aria-describedby') === 'heads-why'), 'reason visible once for the page, and the links point at it (U06/B-06)');
  await post({type: 'status', data: VIEW()});
  const b = q('[data-stock="11"]');
  assert(!b.disabled && !byTest('stock-why'), 'idle again: link allowed');
  b.focus();
  btn('Refresh stock').click();
  await reply(last('cmd', 'stock'), STOCK());
  eq(document.activeElement.dataset.stock, '11', 'keyboard focus survives a refresh');
`);

test('stock: many spools scroll inside the table; the reel never sets the row height; plain note is not a box', `
  await connect();
  await post({type: 'status', data: VIEW({busy: true, state: 'printing'})});
  await until(() => last('cmd', 'stock'));
  const many = Array.from({length: 55}, (_, k) => ({...ROWS[k % 2], id: 100 + k, remaining: 20 * k, initial: 1000}));
  await reply(last('cmd', 'stock'), STOCK({same_spoolman: null, usage: 'printer', stock: {...STOCK().stock, rows: many}}));
  await tab('stock');
  eq(stockRows().length, 55, 'all spools listed');
  // OrcaSlicer's WebKit did not resolve the reel images' height: 100% in a table cell and used their 160 px source
  // height, which grew the reel to 40 x 160 and each row to ~177 px. Force that height: the box must not follow.
  // The reel is the foundation's photo spool (OuiSpool): a fixed px box with its pictures contained in it.
  await settle();
  const figs = qa('.sc-wrap .oui-spool').map(e => e.getBoundingClientRect());
  assert(figs.every(r => Math.round(r.width) === 40 && Math.round(r.height) === 40), 'reel is a fixed 40 px square: ' + JSON.stringify(figs.slice(0, 2)));
  const tall = qa('.sc-wrap tbody tr').map(r => r.getBoundingClientRect().height).filter(h => h > 80);
  eq(tall.length, 0, 'no row taller than its text needs');
  assert(qa('.sc-wrap .oui-spool img').every(e => Math.round(e.getBoundingClientRect().height) <= 40), 'reel pictures contained in their 40 px box');
  const wrap = q('.sc-wrap');
  assert(wrap.scrollHeight > wrap.clientHeight + 100 && getComputedStyle(wrap).overflowY === 'auto', 'long list scrolls inside the table');
  const list = q('.sv-list').getBoundingClientRect();
  assert(list.bottom <= innerHeight + 0.5 && wrap.getBoundingClientRect().bottom <= list.bottom + 0.5, 'the list stays inside the window and its rows scroll inside it');
  const rail = q('[data-test="stock-head"]').getBoundingClientRect();
  assert(rail.right <= q('.sv-list').getBoundingClientRect().left && rail.top < innerHeight, 'the link target stays beside the list');
  const note = byTest('stock-via');
  assert(note && text(note).includes('through the printer') && note.closest('.oui-hint') && !note.closest('.oui-banner'), 'the via-printer note is behind the (i), not a box');
  assert(q('#heads-why').classList.contains('oui-banner'), 'the busy reason keeps its box');
`);

// ------------------------------------------------------------------ new: review findings
test('U01/U12: destructive dialogs name both answers; E-stop apart from Cancel', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true, progress: 0.4})});
  await click(byTest('cancel'));
  assert(btn('Cancel print', dialogEl()) && btn('Keep printing', dialogEl()), 'cancel dialog: Cancel print / Keep printing');
  assert(!qa('button', dialogEl()).some(b => text(b) === 'OK' || text(b) === 'Cancel'), 'no OK / ambiguous Cancel');
  await no();
  eq(cmds('cancel'), [], 'Keep printing sends nothing');
  await click(byTest('estop'));
  assert(btn('Stop now (E-stop)', dialogEl()) && btn('Go back', dialogEl()), 'E-stop dialog labels');
  assert(!dialogText().includes('Klipper will halt'), 'plain language (U10)');
  await no();
  assert(byTest('estop').closest('.oui-appbar') && !byTest('cancel').closest('.oui-appbar'), 'E-stop in its own group, in the app bar, away from Cancel');
`);

test('status block: Pause only while printing, Resume only while paused, Cancel a red outline; the picture is the small box', `
  await connect();
  await post({type: 'status', data: VIEW()});
  eq([byTest('pause'), byTest('resume'), byTest('cancel')], [null, null, null], 'idle: no print controls');
  const box = () => { const r = q('[data-test="job-card"] .oui-job-thumb').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
  eq(box(), [72, 72], 'idle: the printer picture is the 72 px box');
  await post({type: 'status', data: VIEW({state: 'printing', busy: true, filename: 'a.gcode', progress: 0.2})});
  assert(byTest('pause') && !byTest('resume') && byTest('cancel'), 'printing: Pause and Cancel');
  eq(box(), [72, 72], 'printing: still the 72 px box');
  const fig = q('[data-test="job-card"] [data-test="printer-figure"]').getBoundingClientRect();
  assert(fig.height <= 72 && fig.width <= 72 && fig.height > 40, 'the photo is sized by the box, not the other way round: ' + fig.width + 'x' + fig.height);
  assert(byTest('job-card').getBoundingClientRect().height < 260, 'the status block stays compact: ' + byTest('job-card').getBoundingClientRect().height);
  const cancel = byTest('cancel');
  assert(cancel.classList.contains('p-button-danger') && cancel.classList.contains('p-button-outlined'), 'Cancel is a red outline: ' + cancel.className);
  assert(!byTest('estop').classList.contains('p-button-outlined'), 'the only solid red is Emergency stop');
  await post({type: 'status', data: VIEW({state: 'paused', busy: true, filename: 'a.gcode', progress: 0.2})});
  assert(!byTest('pause') && byTest('resume') && byTest('cancel'), 'paused: Resume and Cancel');
  await post({type: 'offline', error: 'timed out'});
  assert(byTest('resume').disabled && byTest('cancel').disabled, 'offline with a print known: shown, off');
  eq(byTest('cancel').getAttribute('aria-describedby'), 'heads-why', 'and pointing at the reason');
`);

test('U02: Off while printing confirms; declining keeps heating', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  await click(q('[data-off="0"]'));
  assert(dialogOpen() && btn('Keep heating', dialogEl()) && dialogText().includes('fail'), 'confirms during a print');
  await no();
  eq(cmds('temperature'), [], 'declined: nothing sent');
  await type(q('#temp-0'), '0');
  await click(q('[data-set="0"]'));
  assert(dialogOpen() && dialogText().includes('fail'), 'typed 0 during a print is an Off and confirms too');
  await yes();
  eq(cmds('temperature').map(m => m.args), [{heater: '0', target: 0}], 'sent only after confirming');
`);

test('U03: no target disables every physical command with a visible reason', `
  await until(() => last('hello'));
  await fail(last('hello'), 'Select a Snapmaker U1 printer', {no_target: true});
  assert(text(byTest('target-banner')).includes('No U1 selected'), 'banner says no U1 is selected');
  // No printer: the Dashboard is the first-run state. There is nothing to pause, cancel or stop, so those controls are
  // not on the page at all (the connecting state below keeps them, disabled, with the reason).
  for (const t of ['pause', 'resume', 'cancel', 'estop']) eq(byTest(t), null, t + ' absent with no printer chosen');
  assert(q('#heads-why') === byTest('target-banner') && qa('#heads-why').length === 1, 'reason said once, where the controls would be');
  assert(btn('Open Settings'), 'next step offered');
  await tab('settings');
  eq(qa('#heads-why').length, 1, 'on another tab the reason is still said once (one #heads-why)');
  assert(document.body.textContent.includes('Connect to a U1 to see its firmware'), 'settings explains too');
`);

test('E-stop: in the app bar and usable on every tab; while connecting it is shown, off, with the reason', `
  await until(() => last('hello'));
  assert(byTest('estop') && byTest('estop').disabled, 'connecting: E-stop shown, off');
  eq([byTest('pause'), byTest('cancel')], [null, null], 'no print known: nothing to pause or cancel on the page');
  eq(byTest('estop').getAttribute('aria-describedby'), 'heads-why', 'connecting: E-stop points at the reason');
  assert(text(q('#heads-why')).includes('Connecting'), 'the reason says it is connecting: ' + text(q('#heads-why')));
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  for (const name of ['dash', 'stock', 'files', 'settings']) {
    await tab(name);
    const b = byTest('estop');
    assert(b && b.closest('.oui-appbar') && !b.disabled, name + ': E-stop present, enabled and in the app bar');
    const r = b.getBoundingClientRect();
    assert(r.width > 0 && r.height > 0 && document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('[data-test="estop"]') === b, name + ': E-stop visible and on top');
  }
  await click(byTest('estop'));
  assert(btn('Stop now (E-stop)', dialogEl()), 'asks first, from the Settings tab too');
  await yes();
  eq(cmds('emergency_stop').length, 1, 'sent from the Settings tab');
`);

test('a toolhead being edited keeps its heater reading and Off', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: false, extruders: [0, 1, 2, 3].map(i => ({temp: i === 0 ? 210 : 20, target: i === 0 ? 215 : 0, active: i === 0}))})});
  await click(q('[data-edit="0"]'));
  assert(q('#hc-form-0'), 'edit form open');
  assert(q('[data-heater-row="0"]') && text(q('[data-heater-row="0"]')).includes('210'), 'reading still shown while editing');
  assert(q('[data-off="0"]') && !q('[data-off="0"]').disabled, 'Off still there and usable while editing');
  await click(q('[data-off="0"]'));
  assert(dialogOpen() && dialogText().includes('fail'), 'Off during a print still asks');
  await yes();
  eq(cmds('temperature').map(m => m.args), [{heater: '0', target: 0}], 'Off sent from the card being edited');
  assert(q('#hc-form-0'), 'the edit form stays open');
`);

test('settings: Discard drops what was typed and shows the saved values', `
  await connect();
  await post({type: 'config', mode: 'automagic', stored: {}, version: 't', spooler: {}, automations: [],
    settings: {mode: 'automagic', host: 'u1.saved', api_key: '', printer_name: 'Bench U1', spoolman_url: ''}});
  await tab('settings');
  await type(q('#c-host'), 'typed.host');
  assert(document.body.textContent.includes('Unsaved changes') && !byTest('discard').disabled, 'unsaved change shown, Discard on');
  await click(byTest('discard'));
  eq(q('#c-host').value, 'u1.saved', 'saved value back');
  assert(!document.body.textContent.includes('Unsaved changes') && byTest('discard').disabled, 'nothing pending');
  eq(last('save_settings'), undefined, 'nothing saved');
`);

test('offline after a status: the reason is announced assertively; stock links off and point at it; connecting too', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
  await tab('stock');
  assert(stockRows().length === 2 && stockRows().every(b => !b.disabled), 'online and idle: links on');
  await post({type: 'offline', error: 'timed out'});
  assert(text(byTest('target-alert')).includes('doesn') && byTest('target-alert').getAttribute('aria-live') === 'assertive', 'offline: assertive reason: ' + text(byTest('target-alert')));
  eq(qa('#heads-why').length, 1, 'said once');
  for (const b of stockRows()) {
    assert(b.disabled, 'offline: link ' + b.dataset.stock + ' off');
    eq(b.getAttribute('aria-describedby'), 'heads-why', 'offline: link ' + b.dataset.stock + ' points at the reason');
  }
  await post({type: 'selection_changed'});
  await until(() => byTest('estop') && byTest('estop').disabled, 'connecting again');
  assert(text(q('#heads-why')).includes('Connecting'), 'connecting: the reason says so: ' + text(q('#heads-why')));
  if (!stockRows().length) { await until(() => last('cmd', 'stock')); await reply(last('cmd', 'stock'), STOCK()); }
  assert(stockRows().length, 'stock still listed while connecting');
  for (const b of stockRows()) {
    assert(b.disabled, 'connecting: link ' + b.dataset.stock + ' off');
    eq(b.getAttribute('aria-describedby'), 'heads-why', 'connecting: link ' + b.dataset.stock + ' points at the reason');
  }
`);

test('stale status: the banner is announced once; its ticking age is kept out of the live region', `
  await connect();
  await post({type: 'status', data: VIEW()});
  const real = Date.now;
  Date.now = () => real() + 20000;   // the page's clock moves on; no wall-clock wait
  try {
    await until(() => byTest('stale'), 'stale banner');
    const banner = byTest('stale');
    eq(banner.closest('[aria-live]').getAttribute('aria-live'), 'polite', 'stale is a polite notice');
    const age = q('.u1-stale-age', banner);
    eq(age && age.getAttribute('aria-hidden'), 'true', 'the age is hidden from assistive tech');
    assert(age && /ago|s\b|min/.test(text(age)), 'age shown, hidden from the announcement: ' + text(age));
    const spoken = () => { const c = banner.cloneNode(true); c.querySelectorAll('[aria-hidden="true"]').forEach(e => e.remove()); return text(c); };
    const first = spoken(), shownFirst = text(age);
    Date.now = () => real() + 47000;
    await until(() => text(age) !== shownFirst, 'age ticked');
    eq(spoken(), first, 'what is announced does not change when the age ticks');
    assert(first.includes('out of date'), 'says the values may be out of date: ' + first);
  } finally { Date.now = real; }
`);

test('U03: known target offline keeps E-stop on the urgent path; other commands off', `
  await until(() => last('hello'));
  await fail(last('hello'), 'the U1 did not answer in 5 s');
  assert(text(byTest('target-alert')).includes('U1 unreachable'), 'unreachable, not "no target"');
  eq(byTest('target-alert').getAttribute('aria-live'), 'assertive', 'unreachable is announced at once, as before 0.9.0');
  eq(q('#heads-why').closest('[aria-live]'), byTest('target-alert'), 'the reason is in the assertive region');
  eq(q('#heads-why').getAttribute('role'), 'none', 'the banner does not add a second live region');
  eq([byTest('pause'), byTest('cancel')], [null, null], 'no print known: nothing to pause or cancel');
  assert(byTest('sync').disabled && byTest('sync').getAttribute('aria-describedby') === 'heads-why', 'normal commands off, pointing at the reason');
  assert(!byTest('estop').disabled, 'E-stop available for the known target');
  await click(byTest('estop'));
  await yes();
  eq(cmds('emergency_stop').length, 1, 'E-stop sent without fresh telemetry');
  eq(cmds('emergency_stop')[0].gen, undefined, 'no stale generation attached');
`);

test('B-04/B-05: one command per action, visible waiting, unknown after timeout, no automatic retry; E-stop independent', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  byTest('pause').click(); byTest('pause').click(); await settle();
  eq(cmds('pause').length, 1, 'double click sends once');
  assert(byTest('pause').disabled, 'pause disabled while waiting');
  assert(text(q('.notices [role=status]')).includes('Pause: waiting for the printer'), 'waiting is visible');
  assert(!byTest('estop').disabled, 'E-stop never waits behind another command');
  await click(byTest('estop')); await yes();
  eq(cmds('emergency_stop').length, 1, 'E-stop sent while pause is pending');
  await fail(last('cmd', 'emergency_stop'), 'printer not reachable');
  assert(alerts().includes('Emergency stop failed') && alerts().includes('printer not reachable'), 'E-stop error shown: ' + alerts());
  await sleep(15500);
  assert(alerts().includes('no answer after 15 s'), 'unknown outcome reported: ' + alerts());
  assert(!alerts().includes('Pausing'), 'never shown as success');
  eq(cmds('pause').length, 1, 'no automatic retry');
  assert(!byTest('pause').disabled, 'user may decide again: ' + text(q('.st-controls')) + ' / ' + byTest('pause').outerHTML.slice(0, 200));
  assert(alerts().includes('Emergency stop failed'), 'error still shown after 15 s (B-05)');
  await reply(cmds('pause')[0], true);
  assert(!alerts().includes('no answer after'), 'late answer replaces the unknown notice');
  assert(document.body.textContent.includes('answered late'), 'late answer reported');
  const dismiss = qa('.oui-toast').find(m => text(m).includes('Emergency stop failed')).querySelector('.oui-toast-close');
  await click(dismiss);
  assert(!alerts().includes('Emergency stop failed'), 'dismissed by the user');
`, { slow: true });

test('B-01: focus and typed values survive 2 s status ticks; dialogs return focus after a tick', `
  await connect();
  await post({type: 'status', data: VIEW()});
  const load = q('[data-load="0"]');
  load.focus();
  for (let i = 0; i < 3; i++) await post({type: 'status', data: VIEW({extruders: [0, 1, 2, 3].map(k => ({temp: 20 + i, target: 0, active: k === 0}))})});
  assert(document.activeElement === load && load.isConnected, 'Load T1 keeps focus across ticks');
  await type(q('#temp-bed'), '55');
  await post({type: 'status', data: VIEW({bed: {temp: 30, target: 0}})});
  eq(q('#temp-bed').value, '55', 'typed target kept');
  assert(document.activeElement === q('#temp-bed'), 'field keeps focus');
  load.focus(); await press('Enter');
  await until(dialogOpen);
  await post({type: 'status', data: VIEW({bed: {temp: 31, target: 0}})});
  await press('Escape');
  await until(() => !dialogOpen());
  await until(() => document.activeElement && document.activeElement.dataset.load === '0', 'focus back on Load T1');
`);

test('U05: unconfirmed use listed with identity; marking checked is local and needs confirmation', `
  await connect();
  await until(() => last('cmd', 'usage'));
  const entry = {id: 'abc', at: null, spool: 7, grams: 12.5, head: 1, file: 'gcodes/benchy.gcode', error: 'Spoolman timeout', printer: 'u1:80', printer_name: 'Bench U1'};
  await reply(last('cmd', 'usage'), {pending: [], unconfirmed: [entry], acknowledged: [], acknowledged_total: 0, save_error: '', restore_notice: '2 unreadable unconfirmed entries were skipped'});
  const card = byTest('usage-card');
  assert(card, 'card shown');
  assert(text(card).includes('1 filament use') || text(card).includes('benchy.gcode'), 'the banner names the use before Review: ' + text(card));
  await click(byTest('usage-review'));   // the list and "I checked it in Spoolman" are behind Review
  const t = text(card);
  for (const s of ['1 unconfirmed use', 'benchy.gcode', 'T2', '12.5', '#7', 'time unknown', 'Spoolman timeout', 'never sends them again', 'unreadable'])
    assert(t.includes(s), 'shows ' + s + ': ' + t);
  const before = __t.sent.length;
  await click(btn('Mark the use on T2 of benchy.gcode as checked'));
  assert(dialogText().includes('nothing is sent to Spoolman'), 'says nothing is booked');
  await no();
  eq(cmds('usage_ack'), [], 'cancel changes nothing');
  await click(btn('Mark the use on T2 of benchy.gcode as checked'));
  await yes();
  eq(cmds('usage_ack').map(m => m.args), [{id: 'abc'}], 'only the local acknowledgement');
  assert(!__t.sent.slice(before).some(m => m.type === 'cmd' && !['usage_ack', 'usage', 'stock', 'spools'].includes(m.cmd)), 'no booking command');
  await reply(last('cmd', 'usage_ack'), {pending: [], unconfirmed: [], acknowledged: [{...entry, acknowledged_at: 1794300000}], acknowledged_total: 1, save_error: '', restore_notice: ''});
  assert(!byTest('usage-card').checkVisibility(), 'gone once checked');
`);

test('U05: a failed acknowledgement keeps the entry and says why', `
  await connect();
  await until(() => last('cmd', 'usage'));
  const entry = {id: 'abc', at: 1794300000, spool: null, grams: 3, head: 0, file: 'a.gcode', error: 'restart', printer: 'u1:80'};
  await reply(last('cmd', 'usage'), {pending: [], unconfirmed: [entry], acknowledged: [], acknowledged_total: 0, save_error: '', restore_notice: ''});
  await click(byTest('usage-review'));
  await click(btn('Mark the use on T1 of a.gcode as checked')); await yes();
  await fail(last('cmd', 'usage_ack'), "can't save the print ledger (disk full)");
  assert(alerts().includes('disk full') && byTest('usage-card') && text(byTest('usage-card')).includes('a.gcode'), 'entry kept, error shown');
  assert(text(byTest('usage-card')).includes('none linked'), 'unlinked spool said, not hidden');
`);

test('X02: official firmware is named, never "stock"', `
  await connect('stock');
  eq(text(byTest('firmware')), 'Official firmware 1', 'firmware pill');
  assert(byTest('firmware').closest('.oui-pagehead') && !text(q('.oui-pagehead')).toLowerCase().includes('stock'), 'the page header never calls the firmware "stock"');
  assert(!text(q('.oui-appbar-status')).includes('firmware') && !text(q('.oui-appbar-status')).includes('u1:80'), 'the app bar holds the state only');
`);

test('X04: host language pt_BR gives Portuguese, including safety dialogs', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'pt-BR', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('Painel') && text(q('[data-tab="settings"]')).includes('Ajustes'), 'nav in pt-BR');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('Imprimindo'), 'state translated');
  await click(byTest('cancel'));
  assert(btn('Cancelar impressão', dialogEl()) && btn('Continuar imprimindo', dialogEl()), 'cancel dialog in pt-BR');
  await no();
  await click(byTest('estop'));
  assert(btn('Parar agora (E-stop)', dialogEl()) && btn('Voltar', dialogEl()), 'E-stop dialog in pt-BR');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('Pausar falhou: timeout'), 'errors in pt-BR: ' + alerts());
`, { lang: 'pt_BR' });

test('X04: an explicit language choice wins over the host and is kept', `
  await connect();
  await tab('settings');
  await pick(byTest('lang'), 'English');
  assert(text(q('[data-tab="settings"]')).includes('Settings'), 'switched to English');
  eq(last('ui_language').value, 'en', 'kept in the plugin settings');
  await pick(byTest('lang'), 'Automático (Português (Brasil))'.replace('Automático', 'Automatic').replace('Português (Brasil)', 'Português (Brasil)'));
  eq(last('ui_language').value, 'auto', 'automatic again');
  assert(text(q('[data-tab="settings"]')).includes('Ajustes'), 'back to the host language');
`, { lang: 'pt_BR' });

test('i18n: host language de_DE gives de, including safety dialogs and errors', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'de', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('Übersicht') && text(q('[data-tab="settings"]')).includes('Einstellungen'), 'nav in de');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('Druckt'), 'state translated: ' + text(byTest('state')));
  await click(byTest('cancel'));
  assert(btn('Druck abbrechen', dialogEl()) && btn('Weiterdrucken', dialogEl()), 'cancel dialog in de');
  await no();
  await click(byTest('estop'));
  assert(btn('Jetzt stoppen (Not-Aus)', dialogEl()) && btn('Zurück', dialogEl()), 'E-stop dialog in de');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('Pause fehlgeschlagen') && alerts().includes('timeout'), 'errors in de, printer text as given: ' + alerts());
`, { lang: 'de_DE' });

test('i18n: host language es_ES gives es, including safety dialogs and errors', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'es', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('Panel') && text(q('[data-tab="settings"]')).includes('Ajustes'), 'nav in es');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('Imprimiendo'), 'state translated: ' + text(byTest('state')));
  await click(byTest('cancel'));
  assert(btn('Cancelar impresión', dialogEl()) && btn('Seguir imprimiendo', dialogEl()), 'cancel dialog in es');
  await no();
  await click(byTest('estop'));
  assert(btn('Detener ahora (parada de emergencia)', dialogEl()) && btn('Volver', dialogEl()), 'E-stop dialog in es');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('Pausar falló') && alerts().includes('timeout'), 'errors in es, printer text as given: ' + alerts());
`, { lang: 'es_ES' });

test('i18n: host language zh_CN gives zh-CN, including safety dialogs and errors', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'zh-CN', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('仪表盘') && text(q('[data-tab="settings"]')).includes('设置'), 'nav in zh-CN');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('打印中'), 'state translated: ' + text(byTest('state')));
  await click(byTest('cancel'));
  assert(btn('取消打印', dialogEl()) && btn('不取消', dialogEl()), 'cancel dialog in zh-CN');
  await no();
  await click(byTest('estop'));
  assert(btn('立即停止（紧急停止）', dialogEl()) && btn('返回', dialogEl()), 'E-stop dialog in zh-CN');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('暂停失败') && alerts().includes('timeout'), 'errors in zh-CN, printer text as given: ' + alerts());
`, { lang: 'zh_CN' });

test('i18n: host language pl_PL gives pl, including safety dialogs and errors', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'pl', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('Pulpit') && text(q('[data-tab="settings"]')).includes('Ustawienia'), 'nav in pl');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('Drukowanie'), 'state translated: ' + text(byTest('state')));
  await click(byTest('cancel'));
  assert(btn('Anuluj druk', dialogEl()) && btn('Drukuj dalej', dialogEl()), 'cancel dialog in pl');
  await no();
  await click(byTest('estop'));
  assert(btn('Zatrzymaj teraz (E-stop)', dialogEl()) && btn('Wróć', dialogEl()), 'E-stop dialog in pl');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('Wstrzymaj – błąd') && alerts().includes('timeout'), 'errors in pl, printer text as given: ' + alerts());
`, { lang: 'pl_PL' });

test('i18n: host language cs_CZ gives cs, including safety dialogs and errors', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'cs', 'lang attribute');
  assert(text(q('[data-tab="dash"]')).includes('Přehled') && text(q('[data-tab="settings"]')).includes('Nastavení'), 'nav in cs');
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(text(byTest('state')).startsWith('Tiskne'), 'state translated: ' + text(byTest('state')));
  await click(byTest('cancel'));
  assert(btn('Zrušit tisk', dialogEl()) && btn('Pokračovat v tisku', dialogEl()), 'cancel dialog in cs');
  await no();
  await click(byTest('estop'));
  assert(btn('Zastavit hned (E-stop)', dialogEl()) && btn('Zpět', dialogEl()), 'E-stop dialog in cs');
  await no();
  await fail(last('cmd', 'spools') || {id: -1}, 'x');
  await click(byTest('pause'));
  await fail(last('cmd', 'pause'), 'timeout');
  assert(alerts().includes('Pozastavit selhalo') && alerts().includes('timeout'), 'errors in cs, printer text as given: ' + alerts());
`, { lang: 'cs_CZ' });

test('i18n: Traditional Chinese OrcaSlicer reads Simplified Chinese', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'zh-CN', 'zh_TW -> zh-CN');
  assert(text(q('[data-tab="settings"]')).includes('设置'), 'nav in Chinese');
`, { lang: 'zh_TW' });

test('i18n: unknown host language falls back to English', `
  await until(() => last('hello'));
  eq(document.documentElement.lang, 'en', 'fr_FR -> en');
  assert(text(q('[data-tab="settings"]')).includes('Settings'), 'nav in English');
`, { lang: 'fr_FR' });

test('i18n: Deutsch, Español, 简体中文, Polski and Čeština can be chosen by hand and are kept', `
  await connect();
  await tab('settings');
  await pick(byTest('lang'), 'Deutsch');
  assert(text(q('[data-tab="settings"]')).includes('Einstellungen'), 'switched to German');
  eq(last('ui_language').value, 'de', 'kept in the plugin settings');
  await pick(byTest('lang'), 'Español');
  assert(text(q('[data-tab="settings"]')).includes('Ajustes'), 'switched to Spanish');
  eq(last('ui_language').value, 'es', 'Spanish kept');
  await pick(byTest('lang'), '简体中文');
  assert(text(q('[data-tab="settings"]')).includes('设置'), 'switched to Chinese');
  eq(last('ui_language').value, 'zh-CN', 'Chinese kept');
  await pick(byTest('lang'), 'Polski');
  assert(text(q('[data-tab="settings"]')).includes('Ustawienia'), 'switched to Polish');
  eq(last('ui_language').value, 'pl', 'Polish kept');
  await pick(byTest('lang'), 'Čeština');
  assert(text(q('[data-tab="settings"]')).includes('Nastavení'), 'switched to Czech');
  eq(last('ui_language').value, 'cs', 'Czech kept');
  await pick(byTest('lang'), 'Polski');
  await pick(byTest('lang'), 'Automatycznie (English)');
  eq(last('ui_language').value, 'auto', 'automatic from Polish');
  await pick(byTest('lang'), '简体中文');
  await pick(byTest('lang'), '自动（English）');
  eq(last('ui_language').value, 'auto', 'automatic again');
  assert(text(q('[data-tab="settings"]')).includes('Settings'), 'back to the host language');
`);

test('i18n: a saved German choice wins over a Chinese host at load', `
  await until(() => last('hello'));
  assert(text(q('[data-tab="settings"]')).includes('Einstellungen'), 'German kept although the host is zh_CN');
`, { lang: 'zh_CN', pref: 'de' });

test('X04: the saved explicit choice wins over the host language at load', `
  await until(() => last('hello'));
  assert(text(q('[data-tab="settings"]')).includes('Settings'), 'English kept although the host is pt_BR');
`, { lang: 'pt_BR', pref: 'en' });

test('B-11: theme follows the host colour while the page runs', `
  const root = document.documentElement;
  root.style.setProperty('--orca-bg', '#f4f4f4');
  await until(() => !root.classList.contains('orca-dark'), 'light', 4000);
  root.style.setProperty('--orca-bg', '#151515');
  await until(() => root.classList.contains('orca-dark'), 'dark after the host changed', 4000);
  eq(getComputedStyle(document.body).backgroundColor, 'rgb(36, 36, 40)', "dark palette background (OrcaSlicer's neutral, foundation 5.0)");
`);

// ------------------------------------------------------------------ 2026-11 audit: firmware, files, camera
test('a late Extended answer in the status turns the Firmware card on', `
  await connect('stock');
  await until(() => last('cmd', 'spools'));
  await reply(last('cmd', 'spools'), {spools: [], bindings: {}, via: 'direct'});
  await tab('settings');
  assert(text(q('#fw-h').closest('section')).includes('Official Snapmaker firmware'), 'stock first: ' + text(q('#fw-h').closest('section')));
  await post({type: 'status', data: VIEW({firmware: {kind: 'stock', version: '1'}})});
  eq(cmds('ext_settings').length, 0, 'stock: no firmware settings asked');
  await post({type: 'status', data: VIEW({firmware: {kind: 'extended', version: '1.2.0'}})});
  await until(() => last('cmd', 'ext_settings'), 'asked once the printer turned out Extended');
  assert(text(document.body).includes('Extended firmware 1.2.0'), 'header follows');
`);

test('firmware settings that restart Klipper wait for the print; the others stay', `
  await connect('extended');
  await until(() => last('cmd', 'spools'));
  await reply(last('cmd', 'spools'), {spools: [], bindings: {}, via: 'direct'});
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  await tab('settings');
  await until(() => last('cmd', 'ext_settings'));
  await reply(last('cmd', 'ext_settings'), {status: {}, settings: GROUPS});
  assert(btn('Apply Spoolman Integration').disabled, 'Spoolman restarts Klipper: waits');
  assert(!btn('Apply Remote Screen').disabled && !btn('Apply SSH Access').disabled, 'safe ones stay');
  assert(btn('Restart Klipper').disabled && btn('Reboot printer').disabled, 'print-ending actions wait');
  assert(!btn('Restart Moonraker').disabled, 'Moonraker restart stays');
  assert(text(byTest('ext-print-why')).includes('print'), 'says why: ' + text(byTest('ext-print-why')));
  await post({type: 'status', data: VIEW()});
  assert(!btn('Apply Spoolman Integration').disabled && !btn('Restart Klipper').disabled, 'idle again: all on');
  eq(byTest('ext-print-why'), null, 'no reason when idle');
`, { needsGroups: true });

const FILES = {path: 'gcodes', dirs: [{name: 'sub'}], disk: {free: 2e9},
  files: [{name: 'benchy.gcode', size: 10, modified: 5, time: 60, weight: 12.3}, {name: 'clip.gcode', size: 5, modified: 4, time: 30}]};
test('files: a newly selected printer starts at the top folder', `
  await connect();
  await tab('files');
  await trees();
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(q('[data-folder="gcodes/sub"]'));
  eq(last('cmd', 'files').args.path, 'gcodes/sub', 'in the folder');
  await reply(last('cmd', 'files'), {path: 'gcodes/sub', dirs: [], files: []});
  const before = cmds('files').length;
  await post({type: 'selection_changed'});
  await connect('stock', 2);
  await trees();
  await until(() => cmds('files').length > before, 'listed again');
  eq(last('cmd', 'files').args.path, 'gcodes', 'top folder of the new printer');
`);

test('files: rename in place, from the details or the context menu; an unchanged name sends nothing', `
  await connect();
  await tab('files');
  await trees();
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  assert(!btn('Rename benchy.gcode'), 'the actions of one file show once it is selected');
  await click(q('[data-file="gcodes/benchy.gcode"]'));
  await click(btn('Rename benchy.gcode'));
  const field = () => q('[data-files-newname]');
  await until(() => document.activeElement === field(), 'the name opens in its row');
  eq([field().value, field().value.slice(field().selectionStart, field().selectionEnd), !!field().closest('[data-file="gcodes/benchy.gcode"]')], ['benchy.gcode', 'benchy', true], 'the name without its extension is selected, in the row');
  await press('Enter');
  await until(() => !field(), 'closed');
  eq(cmds('rename'), [], 'same name: nothing sent');
  await click(btn('Rename benchy.gcode'));
  await until(() => document.activeElement === field());
  await type(field(), 'clip.gcode'); await press('Enter');
  eq(text(q('.oui-files-nameerror')), 'This folder already has one with that name.', 'a name the folder already has is refused here');
  await type(field(), 'boat.gcode');
  await mouse(q('.oui-files-detail'));
  await until(() => last('cmd', 'rename'), 'a click elsewhere commits');
  eq(last('cmd', 'rename').args, {path: 'gcodes/benchy.gcode', name: 'boat.gcode'}, 'path and new name');
  assert(field() && field().readOnly, 'the field waits for the printer');
  await fail(last('cmd', 'rename'), 'gcodes/boat.gcode exists');
  await until(() => text(q('.oui-files-nameerror')) === 'gcodes/boat.gcode exists', 'the printer refusal stays under the field: ' + text(q('.oui-files-nameerror')));
  assert(!toasts().includes('exists'), 'said once, there, not in a toast too');
  await press('Enter');
  await until(() => cmds('rename').length === 2, 'tried again');
  const listed = cmds('files').length;
  await reply(last('cmd', 'rename'), {path: 'gcodes/boat.gcode'});
  await trees();
  await until(() => cmds('files').length > listed, 'listed again after the rename');
  await reply(last('cmd', 'files'), {...${JSON.stringify(FILES)}, files: [{name: 'boat.gcode', size: 10, modified: 5}, {name: 'clip.gcode', size: 5, modified: 4}]});
  await until(() => !field(), 'the field closes once it is done');
  eq(qa('.oui-files-row[aria-selected="true"]').map(r => r.dataset.file), ['gcodes/boat.gcode'], 'the renamed file stays selected');
  assert(!byTest('folder-rename'), 'a file root is never renamed');
  // The context menu of a file, and F2.
  q('[data-file="gcodes/clip.gcode"]').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(q('[data-file="gcodes/clip.gcode"]'))[0], clientY: centre(q('[data-file="gcodes/clip.gcode"]'))[1]}));
  await until(() => q('.oui-menu'), 'a menu');
  eq(qa('.oui-menu [role=menuitem]').map(text), ['Print', 'Save', 'Rename', 'Move to…', 'Delete'], 'the page\\u2019s actions, then rename, move and delete');
  eq(qa('.oui-files-row[aria-selected="true"]').map(r => r.dataset.file), ['gcodes/clip.gcode'], 'a file outside the selection is selected alone');
  await click(qa('.oui-menu [role=menuitem]').find(b => text(b) === 'Rename'));
  await until(() => document.activeElement === field() && field().value === 'clip.gcode', 'renamed from the menu');
  await press('Escape');
  await until(() => !field(), 'Escape leaves');
  q('[data-file="gcodes/clip.gcode"]').focus(); await press('F2');
  await until(() => document.activeElement === field(), 'F2 renames the focused file');
  await press('Escape');
  eq(cmds('rename').length, 2, 'Escape sends nothing');
`);

test('files: filter by name and show each file\'s filament', `
  await connect();
  await tab('files');
  await trees();
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  const rows = () => qa('.oui-files-row').map(r => r.dataset.file);
  await click(q('[data-file="gcodes/benchy.gcode"]'));
  assert(text(q('.oui-files-detail')).includes('12 g'), 'filament weight in the details of the file: ' + text(q('.oui-files-detail')));
  await type(q('#files-filter'), 'BNCH');
  eq(rows(), ['gcodes/benchy.gcode'], 'fuzzy: case-insensitive, the letters in order');
  eq(qa('.oui-files-row .oui-files-hit').map(text).join(''), 'bnch', 'the matched letters are marked');
  await click(btn('Clear', q('.oui-files-bar')));
  assert(text(q('.oui-files-bar')).includes('Showing 1 of 2 files'), 'with nothing selected the bar says how many of the files are shown: ' + text(q('.oui-files-bar')));
  eq([q('#files-filter').placeholder, q('#files-filter').getAttribute('aria-label')], ['Search by name', 'Search files'], 'the search field, named as in the other printer plugin');
  eq(text(q('.oui-files-row .oui-chip')), 'G-code', 'a print file is tagged G-code');
  assert(q('[data-folder="gcodes/sub"]'), 'the folder tree is not filtered');
  await type(q('#files-filter'), 'zzz');
  assert(text(byTest('files')).includes('No file matches'), 'says nothing matches');
  await type(q('#files-filter'), '');
  eq(rows().length, 2, 'all back');
`);

// ------------------------------------------------------------------ 0.15.0: the file browser (foundation 5.0)
const ABC = {path: 'gcodes', dirs: [{name: 'sub'}], disk: {free: 2e9},
  files: ['a', 'b', 'c'].map((n, i) => ({name: n + '.gcode', size: 1000 * (i + 1), modified: 100 - i, time: 60}))};
const FILES_OPEN = `
  await connect();
  await tab('files');
  const TREE = ['gcodes', 'gcodes/sub', 'gcodes/sub/deep'];
  await trees(TREE);
  await until(() => last('cmd', 'files'), 'the open folder asked for');
  await reply(last('cmd', 'files'), ${JSON.stringify(ABC)});
  // After a change the browser reads the trees and the open folder again, side by side.
  let listed = last('cmd', 'files').id;
  const again = async (tree, answer) => { await trees(tree); await until(() => last('cmd', 'files').id !== listed, 'listed again'); listed = last('cmd', 'files').id; if (answer) await reply(last('cmd', 'files'), answer); };
  const row = n => q('[data-file="gcodes/' + n + '.gcode"]');
  const picked = () => qa('.oui-files-row[aria-selected="true"]').map(r => r.dataset.file.split('/').pop());
  const folderEl = id => q('[data-folder="' + id + '"]');
  const bar = () => q('.oui-files-bar');
`;
test('files: a tree of the printer\'s folders, several files selected, moved by the menu and by dragging onto a folder', `
  ${FILES_OPEN}
  eq(cmds('folders').map(m => [m.args.root, m.gen]).sort(), [['camera', 1], ['gcodes', 1]], 'one walk a root, for the selected printer');
  eq(qa('[data-folder]').map(f => [f.dataset.folder, text(f.querySelector('.oui-files-foldername')), f.getAttribute('aria-level')]),
    [['gcodes', 'Print files', '1'], ['gcodes/sub', 'sub', '2'], ['camera', 'Timelapses & camera', '1']], 'roots named and open, print files first; a folder inside a closed one is not shown');
  eq(folderEl('gcodes').getAttribute('aria-selected'), 'true', 'the open folder is marked');
  eq(text(q('[aria-labelledby="oui-tab-files"] .oui-pagehead-meta')), '2 GB free', 'free space in the page header');
  assert(text(bar()).includes('3 files'), 'the bar counts the files: ' + text(bar()));
  await click(row('a'));
  eq(picked(), ['a.gcode'], 'a click selects one');
  row('c').dispatchEvent(new MouseEvent('click', {bubbles: true, shiftKey: true})); await settle();
  eq(picked(), ['a.gcode', 'b.gcode', 'c.gcode'], 'Shift-click selects the range');
  assert(text(bar()).includes('3 selected') && !btn('Print a.gcode'), 'the bar says how many; the actions of one file are gone: ' + text(bar()));
  await pick(q('.oui-files-move'), 'Print files / sub');
  await until(() => cmds('move').length === 1, 'the first move sent');
  await settle();
  eq(cmds('move').map(m => [m.args, m.gen]), [[{path: 'gcodes/a.gcode', folder: 'gcodes/sub'}, 1]], 'one file at a time, with the folder it goes to');
  await reply(cmds('move')[0], {path: 'gcodes/sub/a.gcode'});
  await until(() => cmds('move').length === 2, 'then the second');
  await fail(cmds('move')[1], 'gcodes/sub already has something named b.gcode; nothing was moved');
  await until(() => cmds('move').length === 3, 'a failure does not stop the rest');
  await reply(cmds('move')[2], {path: 'gcodes/sub/c.gcode'});
  await until(() => toasts().includes('2 files moved.'), 'one message for the files that went: ' + toasts());
  assert(alerts().includes('Move failed') && alerts().includes('b.gcode'), 'the one that stayed says why: ' + alerts());
  await again(TREE, {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files.slice(1, 2))}});
  eq(qa('.oui-files-row').map(r => r.dataset.file), ['gcodes/b.gcode'], 'what is left');
  // Dragging onto a folder, with the real mouse: trusted pointer events. OrcaSlicer's macOS web view never delivers HTML5
  // drops (it replaces WKWebView's drop handling), so the browser drags with pointer events.
  await mdown(row('b'));
  assert(!q('.oui-files-ghost'), 'a press alone does not drag');
  await mmove(folderEl('camera'));
  const ghost = q('.oui-files-ghost');
  assert(ghost && text(ghost).includes('b.gcode') && !q('.oui-files-ghostcount'), 'the file follows the pointer, by name: ' + text(ghost));
  const at = (el, g = ghost.getBoundingClientRect()) => { const [x, y] = centre(el); return Math.abs(g.left - (x - 14)) < 2 && Math.abs(g.top - (y - 14)) < 2; };
  assert(at(folderEl('camera')), 'under the pointer: ' + JSON.stringify(ghost.getBoundingClientRect()) + ' / ' + centre(folderEl('camera')));
  eq(getComputedStyle(ghost).pointerEvents, 'none', 'never in the way of what is under the pointer');
  assert(row('b').hasAttribute('data-dragged'), 'the dragged row dims');
  assert(folderEl('camera').hasAttribute('data-refused') && folderEl('gcodes').hasAttribute('data-refused'), 'a read-only root and the folder the file is in are refused');
  assert(!folderEl('gcodes/sub').hasAttribute('data-refused') && !folderEl('gcodes/sub').hasAttribute('data-drop'), 'a folder that takes it looks as it did');
  eq([qa('[data-drop]').length, document.documentElement.dataset.ouiDrag], [0, 'refused'], 'a refused folder is never marked; the cursor says no');
  await mmove(folderEl('gcodes/sub'));
  assert(at(folderEl('gcodes/sub')), 'the file went with the pointer');
  eq(qa('[data-drop]').map(f => f.dataset.folder), ['gcodes/sub'], 'only the folder under the pointer is marked');
  eq(document.documentElement.dataset.ouiDrag, 'move', 'a grabbing cursor over a folder that takes it');
  await mmove(folderEl('gcodes'));
  eq(qa('[data-drop]').length, 0, 'leaving it clears the mark');
  await mup(folderEl('gcodes'));
  await until(() => !q('.oui-files-ghost'), 'dropped on the folder it is in: the file goes back to its row');
  eq(cmds('move').length, 3, 'and nothing is moved');
  assert(!document.documentElement.dataset.ouiDrag && !q('[data-refused]') && !q('[data-dragged]'), 'the folders and the row are as before');
  eq(picked(), ['b.gcode'], 'the release is not a click');
  await mdown(row('b')); await mmove(folderEl('camera')); await mup(folderEl('camera'));
  await until(() => !q('.oui-files-ghost'), 'dropped on a read-only folder: back to its row');
  await mdown(row('b')); await mmove(folderEl('gcodes/sub')); await press('Escape');
  await until(() => !q('.oui-files-ghost') && !q('[data-drop]'), 'Escape ends the drag');
  await mup(folderEl('gcodes/sub'));
  eq(cmds('move').length, 3, 'a refused drop and Escape move nothing');
  eq(picked(), ['b.gcode'], 'and keep the selection');
  await mdown(row('b')); await mmove(folderEl('gcodes/sub')); await mup(folderEl('gcodes/sub'));
  assert(!q('.oui-files-ghost'), 'the drop takes the file away at once');
  eq(cmds('move').length, 4, 'the drop moves it');
  eq(last('cmd', 'move').args, {path: 'gcodes/b.gcode', folder: 'gcodes/sub'}, 'into the folder it was dropped on');
  await reply(last('cmd', 'move'), {path: 'gcodes/sub/b.gcode'});
  await until(() => toasts().includes('File moved.'), 'said once: ' + toasts());
`);

test('files: dragging a selected file takes the whole selection; an unselected one goes alone', `
  ${FILES_OPEN}
  await click(row('a'));
  row('c').dispatchEvent(new MouseEvent('click', {bubbles: true, ctrlKey: true})); await settle();
  await mdown(row('c')); await mmove(folderEl('gcodes/sub'));
  eq([text(q('.oui-files-ghost .oui-truncate')), text(q('.oui-files-ghostcount'))], ['c.gcode', '2'], 'the file taken, and how many: ' + text(q('.oui-files-ghost')));
  eq(qa('[data-dragged]').map(r => r.dataset.file), ['gcodes/a.gcode', 'gcodes/c.gcode'], 'both rows dim');
  await mup(folderEl('gcodes/sub'));
  await until(() => cmds('move').length === 1, 'the first move sent');
  eq(cmds('move')[0].args, {path: 'gcodes/a.gcode', folder: 'gcodes/sub'}, 'each selected file');
  await reply(cmds('move')[0], {path: 'gcodes/sub/a.gcode'});
  await until(() => cmds('move').length === 2);
  eq(cmds('move')[1].args, {path: 'gcodes/c.gcode', folder: 'gcodes/sub'}, 'goes');
  await reply(cmds('move')[1], {path: 'gcodes/sub/c.gcode'});
  await until(() => toasts().includes('2 files moved.'), toasts());
  await again(TREE, {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files.slice(1, 2))}.concat([{name: 'd.gcode', size: 5, modified: 1}])});
  await click(row('b'));
  await mdown(row('d')); await mmove(folderEl('gcodes/sub'));
  eq([text(q('.oui-files-ghost .oui-truncate')), q('.oui-files-ghostcount')], ['d.gcode', null], 'an unselected file is dragged alone');
  eq(picked(), ['d.gcode'], 'and becomes the selection');
  await mup(folderEl('gcodes/sub'));
  await until(() => cmds('move').length === 3);
  eq(cmds('move')[2].args, {path: 'gcodes/d.gcode', folder: 'gcodes/sub'}, 'only it moves');
`);

test('files: the context menu of a file of the selection acts for the selection', `
  ${FILES_OPEN}
  await click(row('a'));
  row('c').dispatchEvent(new MouseEvent('click', {bubbles: true, ctrlKey: true})); await settle();
  row('c').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(row('c'))[0], clientY: centre(row('c'))[1]}));
  await until(() => q('.oui-menu'));
  eq(qa('.oui-menu [role=menuitem]').map(text), ['Move to…', 'Delete'], 'for two files: no rename, no print');
  eq(picked(), ['a.gcode', 'c.gcode'], 'the selection is kept');
  await mouse(q('.oui-files-detail'));
  await until(() => !q('.oui-menu'), 'a press outside closes it');
  row('c').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(row('c'))[0], clientY: centre(row('c'))[1]}));
  await until(() => q('.oui-menu') && document.activeElement === q('.oui-menu [role=menuitem]'), 'open again, its first item focused');
  await press('ArrowDown');
  eq(text(document.activeElement), 'Delete', 'arrow keys move through the menu');
  await press('Enter');
  await until(dialogOpen, 'asks first');
  assert(dialogText().includes('Delete 2 files?') && dialogText().includes('a.gcode') && dialogText().includes('c.gcode'), dialogText());
  await click(q('[data-dlg="confirm"]', dialogEl()));
  await until(() => cmds('delete').length === 1);
  eq(cmds('delete')[0].args, {path: 'gcodes/a.gcode'}, 'each file of the selection');
  await reply(cmds('delete')[0], true);
  await until(() => cmds('delete').length === 2);
  eq(cmds('delete')[1].args, {path: 'gcodes/c.gcode'}, 'goes');
  await reply(cmds('delete')[1], true);
  await again(TREE, {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files.slice(1, 2))}});
  // Move to… from the menu: the folders the file can go to.
  row('b').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(row('b'))[0], clientY: centre(row('b'))[1]}));
  await until(() => q('.oui-menu'));
  await click(qa('.oui-menu [role=menuitem]').find(b => text(b) === 'Move to…'));
  await until(() => q('[data-files-moveto]'));
  await pick(q('[data-files-moveto]'), 'Print files / sub');
  await click(q('[data-dlg="confirm"]'));
  eq(last('cmd', 'move').args, {path: 'gcodes/b.gcode', folder: 'gcodes/sub'}, 'moved where chosen');
`);

test('files: a grid of pictures, kept for next time; selecting, the menu, rename and dragging work there too', `
  ${FILES_OPEN}
  const withThumbs = {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files)}.map(f => ({...f, thumb: '.thumbs/' + f.name + '-300x300.png'}))};
  await click(q('[data-files-view="grid"]'));
  eq([q('[data-files-view="grid"]').getAttribute('aria-pressed'), qa('.oui-files-card[data-file]').length, !!q('.oui-files-table')], ['true', 3, false], 'cards instead of the table');
  eq(localStorage.getItem('oui-files-view:' + location.pathname + ':u1control'), 'grid', 'kept for the plugin');
  await click(byTest('files-refresh'));
  await again(TREE, withThumbs);
  await until(() => cmds('thumbnail').length, 'the pictures of the cards on screen are asked for');
  await reply(cmds('thumbnail')[0], 'data:image/png;base64,${'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='}');
  await until(() => q('.oui-files-card img'), 'and shown on the card');
  eq(q('.oui-files-card img').closest('[data-file]').dataset.file, cmds('thumbnail')[0].args.path, 'on its own card');
  assert(q('.oui-files-card[data-file="gcodes/b.gcode"] .oui-files-cardpic svg'), 'a file without its picture yet shows the file icon');
  await click(row('a'));
  row('c').dispatchEvent(new MouseEvent('click', {bubbles: true, shiftKey: true})); await settle();
  eq(picked(), ['a.gcode', 'b.gcode', 'c.gcode'], 'Shift-click selects the range');
  row('a').focus(); await press('Escape');
  eq(picked(), [], 'Escape clears');
  row('b').dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(row('b'))[0], clientY: centre(row('b'))[1]}));
  await until(() => q('.oui-menu'));
  await click(qa('.oui-menu [role=menuitem]').find(b => text(b) === 'Rename'));
  const field = () => q('[data-files-newname]');
  await until(() => document.activeElement === field() && field().closest('.oui-files-card'), 'renamed on its card');
  await type(field(), 'bee.gcode'); await press('Enter');
  eq(last('cmd', 'rename').args, {path: 'gcodes/b.gcode', name: 'bee.gcode'}, 'sent');
  await reply(last('cmd', 'rename'), {path: 'gcodes/bee.gcode'});
  await again(TREE, withThumbs);
  await mdown(row('c')); await mmove(folderEl('gcodes/sub'));
  eq(text(q('.oui-files-ghost .oui-truncate')), 'c.gcode', 'a card drags like a row');
  await mup(folderEl('gcodes/sub'));
  eq(last('cmd', 'move').args, {path: 'gcodes/c.gcode', folder: 'gcodes/sub'}, 'dropped on the folder');
`);

test('files: the search is fuzzy, best match first', `
  ${FILES_OPEN}
  const names = ['my_bench_2.gcode', 'xbenchx.gcode', 'benchy_PLA.gcode', 'Bench.gcode', 'clip.gcode', 'b-e-n-c-h.gcode'];
  await click(byTest('files-refresh'));
  await again(TREE, {...${JSON.stringify(ABC)}, files: names.map((name, i) => ({name, size: 1, modified: i}))});
  const shown = () => qa('.oui-files-row').map(r => r.dataset.file.split('/').pop());
  await type(q('#files-filter'), 'bench');
  eq(shown(), ['Bench.gcode', 'b-e-n-c-h.gcode', 'benchy_PLA.gcode', 'my_bench_2.gcode', 'xbenchx.gcode'], 'exact, then without separators, prefix, word start, inside a word');
  eq(text(q('.oui-files-row .oui-files-hit')), 'Bench', 'the match is marked');
  await type(q('#files-filter'), 'bnch pla');
  eq(shown(), ['benchy_PLA.gcode'], 'letters in order, separators skipped');
  await type(q('#files-filter'), 'BÊNCHY');
  eq(shown(), ['benchy_PLA.gcode'], 'case and accents do not matter');
  assert(text(q('.oui-files-bar')).includes('Showing 1 of 6 files'), text(q('.oui-files-bar')));
  await type(q('#files-filter'), '');
  eq(shown().length, 6, 'all back, in the column order');
`);

test('files: no files left after a move says 0 files, in every language', `
  ${FILES_OPEN}
  await click(row('a')); row('c').dispatchEvent(new MouseEvent('click', {bubbles: true, shiftKey: true})); await settle();
  await pick(q('.oui-files-move'), 'Arquivos de impressão / sub');
  for (const n of [0, 1, 2]) { await until(() => cmds('move').length === n + 1); await reply(cmds('move')[n], {path: 'x'}); }
  await again(TREE, {...${JSON.stringify(ABC)}, files: []});
  assert(text(byTest('files')).includes('Nenhum arquivo nesta pasta.'), 'the folder is empty');
  eq(text(q('.oui-files-bar [aria-live]')), '0 arquivos', 'and the count says so (Portuguese puts 0 in the plural rule "one", which read "1 arquivo")');
`, { lang: 'pt-BR' });

test('files: right-click anywhere: the empty list, the empty tree, a root, a time-lapse', `
  ${FILES_OPEN}
  const menuAt = (el, x, y) => { const [cx, cy] = centre(el); el.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: x ?? cx, clientY: y ?? cy})); };
  const items = () => qa('.oui-menu [role=menuitem]').map(text);
  const close = async () => { await press('Escape'); await until(() => !q('.oui-menu'), 'closed'); };
  // The empty part of the list (under the rows).
  const scroll = q('.oui-files-scroll'), sr = scroll.getBoundingClientRect();
  menuAt(scroll, sr.left + sr.width / 2, sr.bottom - 8);
  await until(() => q('.oui-menu'), 'a menu on the empty list');
  eq(items(), ['New folder', 'Select all files', 'Grid', 'Refresh'], 'what can be done in the open folder');
  await click(q('.oui-menu [data-menu="select-all"]'));
  eq(picked(), ['a.gcode', 'b.gcode', 'c.gcode'], 'Select all');
  menuAt(scroll, sr.left + sr.width / 2, sr.bottom - 8);
  await until(() => q('.oui-menu'));
  await click(q('.oui-menu [data-menu="view"]'));
  assert(q('.oui-files-cards') && q('[data-files-view="grid"]').getAttribute('aria-pressed') === 'true', 'the grid, from the menu');
  menuAt(q('.oui-files-scroll'), sr.left + sr.width / 2, sr.bottom - 8);
  await until(() => q('.oui-menu'));
  eq(items()[2], 'List', 'and back');
  await click(q('.oui-menu [data-menu="view"]'));
  assert(q('.oui-files-table'), 'the list again');
  menuAt(scroll, sr.left + sr.width / 2, sr.bottom - 8);
  await until(() => q('.oui-menu'));
  await click(q('.oui-menu [data-menu="new-folder"]'));
  await until(() => q('[data-files-newname]') && q('[data-files-newname]').closest('.oui-files-newrow'), 'New folder from the empty list: at the top of the list');
  await press('Escape');
  menuAt(scroll, sr.left + sr.width / 2, sr.bottom - 8);
  await until(() => q('.oui-menu'));
  await click(q('.oui-menu [data-menu="refresh"]'));
  await again(TREE, ${JSON.stringify(ABC)});
  // The empty part of the tree, and a root.
  const tree = q('.oui-files-tree'), tr = tree.getBoundingClientRect();
  menuAt(tree, tr.left + 20, tr.bottom - 6);
  await until(() => q('.oui-menu'), 'a menu on the empty tree');
  eq(items(), ['New folder', 'Refresh'], 'a new folder in the open one, or read again');
  await close();
  menuAt(folderEl('gcodes'));
  await until(() => q('.oui-menu'));
  eq(items(), ['New folder', 'Refresh'], 'a root: no rename, move or delete');
  await close();
  menuAt(folderEl('camera'));
  await until(() => q('.oui-menu'));
  eq([items(), q('.oui-menu [data-menu="new-folder"]').disabled], [['New folder', 'Refresh'], true], 'the read-only root: nothing can be made there');
  await close();
  // A row of the time-lapses card.
  await until(() => last('cmd', 'timelapses'), 'time-lapses asked for');
  await reply(last('cmd', 'timelapses'), {supported: true, videos: [{path: 'timelapse/v.mp4', file: 'v.mp4', name: 'v', size: 1000, modified: 1794842000, cover: null}]});
  const tl = () => q('[data-timelapse="timelapse/v.mp4"]');
  await until(tl, 'a time-lapse row');
  menuAt(tl());
  await until(() => q('.oui-menu'), 'its menu');
  eq(items(), ['Save', 'Delete'], 'what its buttons do');
  await click(q('.oui-menu [data-menu="save"]'));
  eq(last('cmd', 'download').args, {path: 'timelapse/v.mp4'}, 'Save from the menu');
  await reply(last('cmd', 'download'), '/tmp/v.mp4');
  menuAt(tl());
  await until(() => q('.oui-menu'));
  await click(q('.oui-menu [data-menu="delete"]'));
  await until(dialogOpen, 'Delete asks first');
  await no();
  eq(cmds('timelapse_delete'), [], 'Go back deletes nothing');
`);

test('files: a folder dragged in the tree goes into another folder; itself, inside itself and where it is are refused', `
  ${FILES_OPEN}
  await click(byTest('files-refresh'));
  await again(['gcodes', 'gcodes/Spares', 'gcodes/sub', 'gcodes/sub/deep'], ${JSON.stringify(ABC)});
  await click(q('[data-folder="gcodes/sub"] .oui-files-twisty'));
  assert(folderEl('gcodes/sub/deep'), 'the folder inside is shown');
  await mdown(folderEl('gcodes/sub')); await mmove(folderEl('gcodes/Spares'));
  eq(text(q('.oui-files-ghost .oui-truncate')), 'sub', 'the folder follows the pointer');
  assert(folderEl('gcodes/sub').hasAttribute('data-dragged'), 'and dims in the tree');
  eq(qa('[data-refused]').map(f => f.dataset.folder).sort(), ['camera', 'gcodes', 'gcodes/sub', 'gcodes/sub/deep'], 'itself, inside itself, where it is and another root are refused');
  eq(qa('[data-drop]').map(f => f.dataset.folder), ['gcodes/Spares'], 'the folder under the pointer is marked');
  await mmove(folderEl('gcodes/sub/deep')); await mup(folderEl('gcodes/sub/deep'));
  await until(() => !q('.oui-files-ghost'), 'dropped inside itself: back');
  eq(cmds('move'), [], 'nothing moved');
  eq(last('cmd', 'files').args.path, 'gcodes', 'and the release is not a click that opens the folder');
  await mdown(folderEl('gcodes/sub')); await mmove(folderEl('gcodes/Spares')); await press('Escape');
  await until(() => !q('.oui-files-ghost'), 'Escape ends it'); await mup(folderEl('gcodes/Spares'));
  eq(cmds('move'), [], 'still nothing');
  await mdown(folderEl('gcodes/sub')); await mmove(folderEl('gcodes/Spares')); await mup(folderEl('gcodes/Spares'));
  await until(() => last('cmd', 'move'), 'the drop moves it');
  eq(last('cmd', 'move').args, {path: 'gcodes/sub', folder: 'gcodes/Spares'}, 'the folder, whole, into the one it was dropped on');
  await reply(last('cmd', 'move'), {path: 'gcodes/Spares/sub'});
  await again(['gcodes', 'gcodes/Spares', 'gcodes/Spares/sub', 'gcodes/Spares/sub/deep'], ${JSON.stringify(ABC)});
  assert(!folderEl('gcodes/sub'), 'gone from where it was');
  await click(q('[data-folder="gcodes/Spares"] .oui-files-twisty'));
  assert(folderEl('gcodes/Spares/sub'), 'inside the folder it was dropped on');
  // Back to the root: a root takes a folder dropped on it.
  await mdown(folderEl('gcodes/Spares/sub')); await mmove(folderEl('gcodes'));
  eq(qa('[data-drop]').map(f => f.dataset.folder), ['gcodes'], 'the root takes it');
  await mup(folderEl('gcodes'));
  await until(() => cmds('move').length === 2);
  eq(last('cmd', 'move').args, {path: 'gcodes/Spares/sub', folder: 'gcodes'}, 'to the top');
  await reply(last('cmd', 'move'), {path: 'gcodes/sub'});
  await again(['gcodes', 'gcodes/Spares', 'gcodes/sub', 'gcodes/sub/deep'], ${JSON.stringify(ABC)});
  // Files still drop on folders of the tree.
  await mdown(row('a')); await mmove(folderEl('gcodes/Spares')); await mup(folderEl('gcodes/Spares'));
  await until(() => cmds('move').length === 3);
  eq(last('cmd', 'move').args, {path: 'gcodes/a.gcode', folder: 'gcodes/Spares'}, 'a file onto a folder');
`);

test('files: a card shows its name on two lines at most, broken between words, with the extension under it', `
  ${FILES_OPEN}
  const long = 'CHROMA_V8_50_slots_pull_tray_PLA_84.4g_2h52m_with_a_very_long_tail_name.gcode';
  await click(byTest('files-refresh'));
  await again(TREE, {...${JSON.stringify(ABC)}, files: [{name: 'cable_clip_x10.gcode', size: 2e6, modified: 2}, {name: long, size: 3e6, modified: 1}]});
  await click(q('[data-files-view="grid"]'));
  const card = n => q('.oui-files-card[data-file="gcodes/' + n + '"]');
  const name = n => q('.oui-files-cardname', card(n));
  eq([name('cable_clip_x10.gcode').textContent.replace(/\\u200b/g, ''), text(q('.oui-files-cardmeta', card('cable_clip_x10.gcode')))], ['cable_clip_x10', '.gcode · 2 MB'], 'the name, then the extension and the size');
  eq(card(long).getAttribute('title'), long, 'the whole name in the tooltip');
  const lines = el => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
  assert(lines(name(long)) <= 2 && name(long).scrollHeight > name(long).clientHeight, 'a long name is cut at two lines: ' + lines(name(long)));
  // Every line of a short name ends at a separator, never inside a word.
  const range = document.createRange(), node = name('cable_clip_x10.gcode').firstChild;
  const tops = []; for (let i = 0; i < node.length; i++) { range.setStart(node, i); range.setEnd(node, i + 1); tops.push(Math.round(range.getBoundingClientRect().top)); }
  const chars = [...node.textContent];
  for (let i = 1; i < tops.length; i++) if (tops[i] !== tops[i - 1]) assert(/[\\u200b_]/.test(chars[i - 1]), 'a line ends inside a word at ' + i + ': ' + node.textContent);
  await click(q('[data-files-view="list"]'));
`);

test('files: Delete asks once, with the names; the camera folder is read only and says why', `
  ${FILES_OPEN}
  await click(row('a'));
  row('b').dispatchEvent(new MouseEvent('click', {bubbles: true, ctrlKey: true})); await settle();
  eq(picked(), ['a.gcode', 'b.gcode'], 'Ctrl-click adds one');
  const del = btn('Delete', bar());
  assert(del.classList.contains('p-button-danger') && del.classList.contains('p-button-outlined'), 'Delete is a red outline in the page');
  await click(del);
  await until(dialogOpen, 'asks first');
  assert(dialogText().includes('Delete 2 files?') && dialogText().includes('a.gcode') && dialogText().includes('b.gcode') && dialogText().includes('can’t be undone'), 'the count and the names: ' + dialogText());
  const confirm = q('[data-dlg="confirm"]', dialogEl());
  assert(confirm.classList.contains('p-button-danger') && !confirm.classList.contains('p-button-outlined'), 'the solid red is the confirmation');
  await click(q('[data-dlg="cancel"]', dialogEl()));
  await until(() => !dialogOpen(), 'left');
  eq([cmds('delete').length, picked().length], [0, 2], 'Go back deletes nothing and keeps the selection');
  await click(btn('Delete', bar()));
  await until(dialogOpen);
  await click(q('[data-dlg="confirm"]', dialogEl()));
  await until(() => cmds('delete').length === 1, 'the first delete sent');
  await until(() => !dialogOpen(), 'the question closes');
  eq(cmds('delete')[0].args, {path: 'gcodes/a.gcode'}, 'a file, not a folder');
  await reply(cmds('delete')[0], true);
  assert(!dialogOpen(), 'no second question from the page');
  await until(() => cmds('delete').length === 2);
  eq(cmds('delete')[1].args, {path: 'gcodes/b.gcode'}, 'then the other');
  await reply(cmds('delete')[1], true);
  await until(() => toasts().includes('2 files deleted.'), 'one message: ' + toasts());
  assert(document.activeElement && document.activeElement.dataset.file === 'gcodes/b.gcode', 'the question closed before the printer answered: the keyboard is back on a row that is about to go');
  await again(TREE, {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files.slice(2))}});
  await until(() => document.activeElement && document.activeElement.dataset.file === 'gcodes/c.gcode', 'the keyboard stays in the list, on the row that is left');
  // Enter on a row is the page's main action for it: Print, which asks first.
  await click(row('c'));
  assert(btn('Print c.gcode') && !btn('Print c.gcode').classList.contains('p-button-secondary'), 'Print is the one primary action');
  row('c').focus();
  await press('Enter');
  await until(dialogOpen, 'Enter prints, and asks');
  assert(dialogText().includes('c.gcode') && dialogText().includes('Bench U1'), dialogText());
  await no();
  eq(cmds('print_file'), [], 'Go back prints nothing');
  await click(folderEl('camera'));
  eq(last('cmd', 'files').args.path, 'camera', 'the other root');
  await reply(last('cmd', 'files'), {path: 'camera', dirs: [], files: [{name: 'shot.jpg', size: 2000, modified: 9}]});
  await click(q('[data-file="camera/shot.jpg"]'));
  assert(q('#files-ro') && text(q('#files-ro')) === 'Read only', 'says it is read only, once');
  assert(btn('Delete', bar()).disabled && btn('Delete', bar()).getAttribute('aria-describedby') === 'files-ro', 'Delete off, pointing at the reason');
  assert(q('.oui-files-move').classList.contains('p-disabled') && !q('[data-files-mkdir]') && !byTest('folder-delete'), 'Move off; no folder is made, renamed or deleted here');
  await mdown(q('[data-file="camera/shot.jpg"]')); await mmove(folderEl('gcodes/sub'));
  assert(!q('.oui-files-ghost') && !q('[data-drop]'), 'nothing to drag'); await mup(folderEl('gcodes/sub'));
  eq(cmds('move'), [], 'and nothing moved');
  assert(btn('Save shot.jpg') && !btn('Print shot.jpg') && !btn('Rename shot.jpg'), 'a picture can be saved, not printed or renamed');
  await click(btn('Save shot.jpg'));
  eq(last('cmd', 'download').args, {path: 'camera/shot.jpg'}, 'saved from its own root');
`);

test('files: newest first; a read that fails says so, keeps the tree and reads again on Try again', `
  await connect();
  await tab('files');
  await trees();
  await until(() => last('cmd', 'files'));
  await fail(last('cmd', 'files'), 'the U1 did not answer in 5 s');
  assert(text(byTest('files')).includes('Couldn’t read the file list') && text(byTest('files')).includes('did not answer'), 'what failed and why: ' + text(byTest('files')));
  assert(q('[data-folder="gcodes/sub"]') && !q('.oui-files-row'), 'the folders stay; no rows are made up');
  await click(q('[data-files-retry]'));
  await trees();
  await until(() => cmds('files').length === 2, 'read again');
  await reply(last('cmd', 'files'), {path: 'gcodes', dirs: [], files: [{name: 'old.gcode', modified: 1}, {name: 'new.gcode', modified: 9}, {name: 'mid.gcode', modified: 5}]});
  const rows = () => qa('.oui-files-row').map(r => r.dataset.file.split('/').pop());
  eq(rows(), ['new.gcode', 'mid.gcode', 'old.gcode'], 'newest first, as the printer lists them');
  await click(q('.oui-files-sort'));
  eq(rows(), ['mid.gcode', 'new.gcode', 'old.gcode'], 'any column can still be sorted');
  // a camera root the firmware does not share is still listed: opening it says what is wrong
  await click(byTest('files-refresh'));
  const walks = cmds('folders').slice(-2);
  await reply(walks.find(m => m.args.root === 'gcodes'), ['gcodes']);
  await fail(walks.find(m => m.args.root === 'camera'), 'no such root');
  await until(() => cmds('files').length === 3);
  await reply(last('cmd', 'files'), {path: 'gcodes', dirs: [], files: []});
  assert(q('[data-folder="camera"]') && !alerts(), 'a root that cannot be walked stays in the tree, without an error');
`);

// A narrow tab: the folders go above the list and the open file's details under it. The list keeps its rows.
for (const size of [[420, 900], [600, 720]]) test(`files: at ${size.join('x')} the rows stay in sight with a file's details open`, `
  ${FILES_OPEN}
  await click(row('b'));
  await until(() => btn('Print b.gcode'), 'the details of the file are open');
  await settle();
  const box = sel => q(sel).getBoundingClientRect();
  const rows = box('.oui-files-scroll'), tools = box('.oui-files-toolbar'), bulk = box('.oui-files-bar'), detail = box('.oui-files-detail'), all = box('.oui-files-grid');
  assert(rows.height >= 110, 'room for the column heads and at least two rows: ' + rows.height);
  for (const n of ['a', 'b']) { const r = row(n).getBoundingClientRect(); assert(r.top >= rows.top - 1 && r.bottom <= rows.bottom + 1, n + '.gcode is in sight: ' + r.top + '..' + r.bottom + ' in ' + rows.top + '..' + rows.bottom); }
  assert(tools.bottom <= bulk.top + 1 && box('#files-filter').bottom <= tools.bottom + 1, 'the path, New folder and the filter keep their own lines: ' + tools.bottom + ' / ' + bulk.top);
  assert(bulk.bottom <= rows.top + 1 && box('.oui-files-bar .p-button-danger').bottom <= bulk.bottom + 1, 'Move to and Delete are whole, over the rows');
  assert(detail.top >= rows.bottom - 1 && detail.height <= all.height * 0.42, 'the details sit under the list and take no more than their share: ' + detail.height + ' of ' + all.height);
  const pane = q('.oui-files-detail');
  assert(pane.scrollHeight <= pane.clientHeight + 1 || getComputedStyle(pane).overflowY === 'auto', 'details that do not fit scroll inside their pane');
  assert(document.documentElement.scrollWidth <= innerWidth, 'no sideways scrolling');
`, { size });

test('files: a new folder, and the open folder renamed, moved and deleted', `
  ${FILES_OPEN}
  // New folder, as in Finder: a folder at the top of the list with its name selected; a click elsewhere commits.
  const field = () => q('[data-files-newname]');
  assert(!q('[data-files-mkdir]').classList.contains('p-button-text'), 'New folder reads as a button');
  await mouse(q('[data-files-mkdir]'));
  await until(() => document.activeElement === field(), 'the name field');
  eq([field().value, field().value.slice(field().selectionStart, field().selectionEnd), !!field().closest('.oui-files-table .oui-files-newrow')], ['New folder', 'New folder', true], 'at the top of the list, the name selected');
  await type(field(), 'SUB'); await press('Enter');
  assert(field() && text(q('.oui-files-nameerror')) === 'This folder already has one with that name.' && field().getAttribute('aria-invalid') === 'true', 'a name its sibling has is refused: ' + text(q('.oui-files-nameerror')));
  await type(field(), 'a/b'); await mouse(q('.oui-files-detail'));
  eq([!!field(), text(q('.oui-files-nameerror'))], [true, 'A name can’t contain / or be . or ..'], 'a click elsewhere with a bad name says why and keeps the field');
  await type(field(), ''); await press('Enter');
  eq(text(q('.oui-files-nameerror')), 'Type a name.', 'an empty name is refused');
  await press('Escape');
  await until(() => !field(), 'Escape leaves');
  eq(cmds('mkdir'), [], 'nothing sent for a refused name or Escape');
  await mouse(q('[data-files-mkdir]'));
  await until(() => document.activeElement === field());
  await type(field(), 'Spares');
  await mouse(q('.oui-files-detail'));
  await until(() => last('cmd', 'mkdir'), 'a click elsewhere commits');
  eq(last('cmd', 'mkdir').args, {path: 'gcodes/Spares'}, 'in the open folder');
  await reply(last('cmd', 'mkdir'), {item: {path: 'Spares', root: 'gcodes'}, action: 'create_dir'});
  await until(() => toasts().includes('Folder created'), 'said: ' + toasts());
  await again(['gcodes', 'gcodes/Spares', ...TREE.slice(1)], {path: 'gcodes/Spares', dirs: [], files: []});
  eq(last('cmd', 'files').args.path, 'gcodes/Spares', 'the new folder is opened');
  eq(folderEl('gcodes/Spares').getAttribute('aria-selected'), 'true', 'and marked in the tree');
  // A refusal from the printer is shown under the field, which stays open with the name.
  await mouse(q('[data-files-mkdir]'));
  await until(() => document.activeElement === field());
  await type(field(), 'bad#name'); await press('Enter');
  await until(() => cmds('mkdir').length === 2);
  await fail(last('cmd', 'mkdir'), "folder names use letters, digits, spaces, '-', '_' and '.'");
  await until(() => text(q('.oui-files-nameerror')).includes('folder names use'), 'the reason, under the field: ' + text(q('.oui-files-nameerror')));
  eq(field().value, 'bad#name', 'the name is kept to fix');
  await press('Escape');
  // The new folder takes files like any other: drag one there.
  await click(folderEl('gcodes'));
  listed = last('cmd', 'files').id;
  await reply(last('cmd', 'files'), ${JSON.stringify(ABC)});
  await mdown(row('a')); await mmove(folderEl('gcodes/Spares'));
  eq(qa('[data-drop]').map(f => f.dataset.folder), ['gcodes/Spares'], 'a place to drop');
  await mup(folderEl('gcodes/Spares'));
  eq(last('cmd', 'move').args, {path: 'gcodes/a.gcode', folder: 'gcodes/Spares'}, 'moved into the new folder');
  await reply(last('cmd', 'move'), {path: 'gcodes/Spares/a.gcode'});
  await again(['gcodes', 'gcodes/Spares', ...TREE.slice(1)], {...${JSON.stringify(ABC)}, files: ${JSON.stringify(ABC.files.slice(1))}});
  // A folder's context menu in the tree: New folder there, named in the tree.
  const menuAt = el => el.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: centre(el)[0], clientY: centre(el)[1]}));
  menuAt(folderEl('gcodes/sub'));
  await until(() => q('.oui-menu [role=menuitem]'), 'a menu');
  eq(qa('.oui-menu [role=menuitem]').map(text), ['New folder', 'Rename', 'Move to…', 'Delete', 'Refresh'], 'what can be done with a folder');
  eq(document.activeElement, q('.oui-menu [role=menuitem]'), 'the first item has focus');
  await press('Escape');
  await until(() => !q('.oui-menu'), 'Escape closes it');
  menuAt(folderEl('gcodes'));
  await until(() => q('.oui-menu'));
  eq(qa('.oui-menu [role=menuitem]').map(text), ['New folder', 'Refresh'], 'a root is never renamed, moved or deleted');
  await press('Escape');
  menuAt(folderEl('gcodes/sub'));
  await until(() => q('.oui-menu'));
  await mouse(q('.oui-menu [role=menuitem]'));
  await until(() => field() && document.activeElement === field(), 'the name field');
  eq(field().closest('[role=treeitem]').previousElementSibling.dataset.folder, 'gcodes/sub', 'in the tree, under that folder');
  await type(field(), 'inner'); await press('Enter');
  await until(() => cmds('mkdir').length === 3);
  eq(last('cmd', 'mkdir').args, {path: 'gcodes/sub/inner'}, 'in the folder of the menu');
  await reply(last('cmd', 'mkdir'), {item: {path: 'sub/inner', root: 'gcodes'}, action: 'create_dir'});
  await again(['gcodes', 'gcodes/Spares', 'gcodes/sub', 'gcodes/sub/inner', 'gcodes/sub/deep'], {path: 'gcodes/sub/inner', dirs: [], files: []});
  await click(folderEl('gcodes/sub'));
  listed = last('cmd', 'files').id;
  await reply(last('cmd', 'files'), {path: 'gcodes/sub', dirs: [{name: 'deep'}, {name: 'inner'}], files: []});
  assert(text(byTest('files')).includes('No files in this folder'), 'an empty folder says so');
  // The open folder's own buttons beside the path: move (a question with the folders it can go to), rename in place, delete.
  await click(byTest('folder-move'));
  await until(() => q('[data-files-moveto]'), 'asks where');
  await pick(q('[data-files-moveto]'), 'Print files / Spares');
  await click(q('[data-dlg="confirm"]'));
  eq(last('cmd', 'move').args, {path: 'gcodes/sub', folder: 'gcodes/Spares'}, 'the folder moves whole');
  await reply(last('cmd', 'move'), {path: 'gcodes/Spares/sub'});
  await again(['gcodes', 'gcodes/Spares', 'gcodes/Spares/sub', 'gcodes/Spares/sub/deep', 'gcodes/Spares/sub/inner'], {path: 'gcodes/Spares/sub', dirs: [{name: 'deep'}], files: []});
  eq(last('cmd', 'files').args.path, 'gcodes/Spares/sub', 'the page follows it');
  eq(folderEl('gcodes/Spares/sub').getAttribute('aria-selected'), 'true', 'open and marked where it is now');
  assert(!folderEl('gcodes/sub'), 'gone from where it was');
  await click(byTest('folder-rename'));
  await until(() => document.activeElement === field(), 'the name opens in the tree');
  assert(field().closest('[data-folder="gcodes/Spares/sub"]'), 'in its own row');
  await type(field(), 'old'); await mouse(q('.oui-files-detail'));
  await until(() => last('cmd', 'rename'), 'a click elsewhere commits');
  eq(last('cmd', 'rename').args, {path: 'gcodes/Spares/sub', name: 'old'}, 'renamed where it is');
  await reply(last('cmd', 'rename'), {path: 'gcodes/Spares/old'});
  await again(['gcodes', 'gcodes/Spares', 'gcodes/Spares/old'], {path: 'gcodes/Spares/old', dirs: [], files: []});
  eq(last('cmd', 'files').args.path, 'gcodes/Spares/old', 'the page follows the new name');
  const del = byTest('folder-delete');
  assert(del.classList.contains('p-button-danger') && del.classList.contains('p-button-text'), 'deleting a folder is red, an icon like its neighbours');
  await click(del);
  await until(dialogOpen);
  assert(dialogText().includes('old') && dialogText().includes('everything in it'), 'asks, naming the folder and what goes with it: ' + dialogText());
  await click(q('[data-dlg="cancel"]', dialogEl()));
  await until(() => !dialogOpen());
  eq(cmds('delete'), [], 'Keep deletes nothing');
  menuAt(folderEl('gcodes/Spares/old'));
  await until(() => q('.oui-menu'));
  await click(qa('.oui-menu [role=menuitem]').find(b => text(b) === 'Delete'));
  await until(dialogOpen, 'the menu asks too');
  await click(q('[data-dlg="confirm"]', dialogEl()));
  await until(() => last('cmd', 'delete'));
  eq(last('cmd', 'delete').args, {path: 'gcodes/Spares/old', is_dir: true}, 'the folder and what is in it');
  await reply(last('cmd', 'delete'), true);
  await again(['gcodes', 'gcodes/Spares'], {path: 'gcodes/Spares', dirs: [], files: []});
  eq(last('cmd', 'files').args.path, 'gcodes/Spares', 'back in the folder above');
  assert(!folderEl('gcodes/Spares/old'), 'and out of the tree');
`);

// ------------------------------------------------------------------ 0.11.0: time-lapses
const PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
const TL = {supported: true, videos: [
  {path: 'timelapse/benchy_20261116130921.mp4', file: 'benchy_20261116130921.mp4', name: 'benchy', size: 375588, modified: 1794842000, cover: 'timelapse/benchy_20261116130921_cover.jpg'},
  {path: 'timelapse/vase_20261115080000.mp4', file: 'vase_20261115080000.mp4', name: 'vase', size: 2400000, modified: 1794760000, cover: 'timelapse/vase_20261115080000.jpg'},
  {path: 'timelapse/no cover.mp4', file: 'no cover.mp4', name: 'no cover', size: 1000, modified: null, cover: null}]};
const TL_OPEN = `
  await connect();
  await tab('files');
  await until(() => last('cmd', 'timelapses'), 'time-lapses asked for');
  const panel = byTest('timelapses');
  const row = file => q('[data-timelapse="timelapse/' + file + '"]', panel);
`;

test('time-lapses: one row per video with its cover; saving says where the file went', `
  ${TL_OPEN}
  eq([last('cmd', 'timelapses').args, last('cmd', 'timelapses').gen], [{}, 1], 'asked for the selected printer');
  assert(text(panel).includes('Listing time-lapses'), 'loading is said');
  await reply(last('cmd', 'timelapses'), ${JSON.stringify(TL)});
  eq(qa('.tl-name', panel).map(text), ['benchy', 'vase', 'no cover'], 'print names, in the order the plugin gave');
  assert(text(row('benchy_20261116130921.mp4')).includes('benchy_20261116130921.mp4') && text(row('benchy_20261116130921.mp4')).includes('376 kB'), 'file name and size: ' + text(row('benchy_20261116130921.mp4')));
  assert(text(panel).includes('3 videos'), 'count in the header');
  eq(text(q('#timelapses-h')), 'Time-lapses', 'its own titled section');
  eq(panel.getAttribute('aria-labelledby'), 'timelapses-h', 'labelled by its title');
  await until(() => cmds('timelapse_cover').length === 2, 'covers asked for');
  eq(cmds('timelapse_cover').map(m => m.args), [{path: 'timelapse/benchy_20261116130921_cover.jpg'}, {path: 'timelapse/vase_20261115080000.jpg'}], 'only the videos that have a picture');
  await trees();
  await until(() => last('cmd', 'files'), 'print files asked for');
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(byTest('files-refresh'));
  await reply(cmds('timelapse_cover')[0], ${JSON.stringify(PIXEL)});
  await until(() => q('.tl-cover img', row('benchy_20261116130921.mp4')), 'cover shown, although the print files were listed again meanwhile');
  eq(q('.tl-cover img', row('benchy_20261116130921.mp4')).getAttribute('alt'), '', 'decorative: the name is next to it');
  assert(!q('img', row('no cover.mp4')) && q('.tl-cover svg', row('no cover.mp4')), 'an icon where there is no cover');
  await fail(cmds('timelapse_cover')[1], 'printer response too large');
  assert(!q('img', row('vase_20261115080000.mp4')) && !alerts(), 'a cover that fails is an icon, not an error');
  eq(cmds('thumbnail'), [], 'covers never use the print-file thumbnails');
  const save = btn('Save the time-lapse benchy_20261116130921.mp4');
  eq(text(save), 'Save', 'same word as the file list');
  save.click(); save.click(); await settle();
  eq(cmds('download').map(m => [m.args, m.gen]), [[{path: 'timelapse/benchy_20261116130921.mp4'}, 1]], 'one download, from the writable root');
  assert(btn('Delete the time-lapse benchy_20261116130921.mp4').disabled, 'no delete while that video is being saved');
  assert(!btn('Delete the time-lapse vase_20261115080000.mp4').disabled && !btn('Save the time-lapse vase_20261115080000.mp4').disabled, 'the other rows stay usable');
  await reply(last('cmd', 'download'), '/home/u/Downloads/u1control/benchy_20261116130921.mp4');
  await until(() => toasts().includes('Saved to /home/u/Downloads/u1control/benchy_20261116130921.mp4'), 'says where it was saved');
  assert(!btn('Delete the time-lapse benchy_20261116130921.mp4').disabled, 'delete is back');
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(!btn('Save the time-lapse vase_20261115080000.mp4').disabled && !btn('Delete the time-lapse vase_20261115080000.mp4').disabled, 'saving and deleting stay on while printing');
`);

test('time-lapses: delete asks first, names both answers, takes the video and keeps the keyboard in the list', `
  ${TL_OPEN}
  await reply(last('cmd', 'timelapses'), ${JSON.stringify(TL)});
  const del = btn('Delete the time-lapse benchy_20261116130921.mp4');
  del.focus();
  await click(del);
  assert(dialogOpen() && dialogText().includes('benchy_20261116130921.mp4') && dialogText().includes('cover pictures'), 'says what goes: ' + dialogText());
  assert(btn('Delete', dialogEl()) && btn('Go back', dialogEl()), 'both answers named');
  await until(() => document.activeElement === q('[data-dlg="no"]'), 'focus starts on the way back');
  await no();
  eq(cmds('timelapse_delete'), [], 'cancel deletes nothing');
  await until(() => document.activeElement === del, 'focus returns to Delete');
  await click(del);
  await yes();
  eq(cmds('timelapse_delete').map(m => [m.args, m.gen]), [[{path: 'timelapse/benchy_20261116130921.mp4'}, 1]], 'only the video is named; the plugin pairs the pictures');
  assert(btn('Save the time-lapse benchy_20261116130921.mp4').disabled, 'no save while that video is being deleted');
  const listed = cmds('timelapses').length;
  await reply(last('cmd', 'timelapse_delete'), {deleted: ['timelapse/benchy_20261116130921_cover.jpg', 'timelapse/benchy_20261116130921.mp4']});
  await until(() => cmds('timelapses').length > listed, 'listed again after the delete');
  await reply(last('cmd', 'timelapses'), ${JSON.stringify({ ...TL, videos: TL.videos.slice(1) })});
  eq(qa('[data-timelapse]', panel).map(r => r.dataset.timelapse), ['timelapse/vase_20261115080000.mp4', 'timelapse/no cover.mp4'], 'the row is gone');
  assert(text(panel).includes('2 videos'), 'count follows');
  await until(() => document.activeElement === byTest('tl-refresh'), 'focus goes to Refresh, not to the top of the page');
  assert(toasts().includes('Deleted'), 'success is said');
  btn('Delete the time-lapse no cover.mp4').focus();
  await click(btn('Delete the time-lapse no cover.mp4'));
  await yes();
  const again = cmds('timelapses').length;
  await fail(last('cmd', 'timelapse_delete'), 'printer said: delete failed');
  assert(alerts().includes('Delete time-lapse failed: printer said: delete failed'), 'the failure is shown: ' + alerts());
  await until(() => cmds('timelapses').length > again, 'listed again after a failure too');
  await reply(last('cmd', 'timelapses'), ${JSON.stringify({ ...TL, videos: TL.videos.slice(1) })});
  assert(row('no cover.mp4'), 'the video is still there to try again');
  await until(() => document.activeElement === btn('Delete the time-lapse no cover.mp4'), 'focus is back on its Delete');
`);

test('time-lapses: no printer, empty, error with a way out, firmware without the folder, another printer', `
  await until(() => last('hello'), 'hello sent');
  await tab('files');
  const panel = byTest('timelapses');
  assert(text(panel).includes('Connect to a U1 to see its time-lapses.'), 'no printer yet: ' + text(panel));
  assert(byTest('tl-refresh').disabled, 'nothing to refresh without a printer');
  eq(cmds('timelapses'), [], 'nothing asked without a printer');
  await connect();
  await until(() => last('cmd', 'timelapses'), 'asked once connected');
  await reply(last('cmd', 'timelapses'), {supported: true, videos: []});
  assert(text(panel).includes('No time-lapses yet.') && !q('table', panel), 'empty state: ' + text(panel));
  await click(byTest('tl-refresh'));
  eq(cmds('timelapses').length, 2, 'Refresh asks again');
  assert(q('[aria-busy="true"]', panel) || q('.p-button-loading', panel), 'busy while it waits');
  await fail(last('cmd', 'timelapses'), 'printer said: boom');
  eq(text(q('[role=alert]', panel)).includes('Couldn’t list the time-lapses: printer said: boom'), true, 'the error is announced in the section: ' + text(panel));
  await click(btn('Try again', panel));
  await reply(last('cmd', 'timelapses'), {supported: false, videos: []});
  assert(text(panel).includes('This printer shares no time-lapse folder.') && !q('[role=alert]', panel), 'a firmware without the folder is said, not shown as an error');
  await click(byTest('tl-refresh'));
  await reply(last('cmd', 'timelapses'), ${JSON.stringify(TL)});
  eq(qa('[data-timelapse]', panel).length, 3, 'listed');
  const before = cmds('timelapses').length;
  await post({type: 'selection_changed'});
  eq(qa('[data-timelapse]', panel).length, 0, "the other printer's videos are never shown");
  await connect('stock', 2);
  await until(() => cmds('timelapses').length > before, 'asked from the new printer');
  eq(last('cmd', 'timelapses').gen, 2, 'for its generation');
  const late = last('cmd', 'timelapses');
  await tab('dash');
  await post({type: 'selection_changed'});
  await connect('stock', 3);
  await reply(late, ${JSON.stringify(TL)});
  await tab('files');
  eq(qa('[data-timelapse]', panel).length, 0, 'an answer that was on its way for the previous printer is dropped');
  eq(last('cmd', 'timelapses').gen, 3, 'and the list is asked from the printer now selected');
`);

test('time-lapses: Portuguese, including the delete question', `
  ${TL_OPEN}
  await reply(last('cmd', 'timelapses'), ${JSON.stringify(TL)});
  eq(text(q('#timelapses-h')), 'Timelapses', 'title');
  assert(text(panel).includes('3 vídeos') && text(panel).includes('Gravado em'), 'header and columns: ' + text(panel));
  await click(btn('Excluir o timelapse vase_20261115080000.mp4'));
  assert(dialogText().includes('Excluir o timelapse vase_20261115080000.mp4 e as imagens de capa dele da impressora?'), dialogText());
  assert(btn('Excluir', dialogEl()) && btn('Voltar', dialogEl()), 'both answers in pt-BR');
  await no();
  eq(cmds('timelapse_delete'), [], 'nothing deleted');
`, { lang: 'pt_BR' });

test('camera: save the picture on screen', `
  await connect();
  await post({type: 'status', data: VIEW()});
  eq(byTest('cam-save'), null, 'no button while the camera is off');
  const box = () => { const r = q('.oui-camera').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
  const off = box();
  assert(text(q('.oui-camera')).includes('Camera off') && Math.abs(off[0] / off[1] - 16 / 9) < 0.02, 'off: one sentence in the 16:9 box: ' + off);
  await click(byTest('camera'));
  eq(byTest('cam-save'), null, 'no button before the first picture');
  eq([box(), text(q('.oui-camera'))], [off, 'Starting the camera…'], 'starting: the same box, saying so');
  assert(!sent().some(m => m.type === 'frame_ack'), 'nothing acknowledged before a picture is shown');
  await post({type: 'frame', image: ${JSON.stringify(PIXEL)}});
  await until(() => last('frame_ack'), 'the picture on screen is acknowledged, so the plugin sends the next one');
  eq(box(), off, 'turning the camera on does not move the page');
  assert(text(q('.oui-camera-overlay')).includes('Live'), 'live is said over the picture');
  await post({type: 'frame', image: 'data:image/jpeg;base64,/9j/'});
  await click(byTest('cam-save'));
  const cmd = last('cmd', 'snapshot');
  eq(cmd.args, {}, 'asks the plugin to save its last picture');
  await reply(cmd, '/home/u/Downloads/u1control/Bench U1 2026-11-14 10-00-00.jpg');
  await until(() => toasts().includes('Saved to'), 'says where it was saved');
`);

test('camera: frame rate choice starts at the stored rate, is sent to the plugin and says its limits', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await post({type: 'config', mode: 'automagic', stored: {}, version: '0.7.0', spooler: {}, automations: [], settings: {mode: 'automagic', camera_fps: 10}});
  eq(byTest('cam-fps'), null, 'no choice while the camera is off');
  await click(byTest('camera'));
  const sel = byTest('cam-fps');
  assert(sel && text(sel).includes('10 fps'), 'shows the stored rate: ' + text(sel));
  eq(q('[role=combobox]', sel).getAttribute('aria-describedby'), 'cam-fps-help', 'the combobox itself is described by its help');
  assert(text(q('#cam-fps-help')).includes('can be lower'), 'does not promise the rate: ' + text(q('#cam-fps-help')));
  await pick(sel, '30 fps');
  eq(last('camera_fps'), {type: 'camera_fps', value: 30}, 'choice sent to the plugin');
  assert(text(byTest('cam-fps')).includes('30 fps'), 'choice kept on screen');
`);

test('settings: says whether the process preset runs the toolhead choice and when its pop-up opens', `
  await connect();
  const cfg = (pipeline, dialog, auto = true) => post({type: 'config', mode: 'automagic', stored: {}, version: '0.7.0', spooler: {}, automations: [],
    settings: {mode: 'automagic', print_dialog: dialog, auto_add_pipeline: auto}, pipeline});
  await tab('settings');
  await cfg({preset: '0.20 Standard @U1', on: false}, 'auto');
  assert(byTest('ps-off') && text(byTest('ps-off')).includes('0.20 Standard @U1') && text(byTest('ps-off')).includes('without choosing toolheads'), 'missing step is a warning: ' + text(byTest('ps-off')));
  assert(byTest('ps-off').classList.contains('oui-banner') && byTest('ps-off').dataset.tone === 'warn', 'shown as a warning');
  assert(text(byTest('ps-off')).includes('once per OrcaSlicer session'), 'auto-add on: says when it is added');
  await cfg({preset: '0.20 Standard @U1', on: false}, 'auto', false);
  assert(text(byTest('ps-off')).includes('Adding it automatically is off') && !text(byTest('ps-off')).includes('U1 Control adds it'), 'auto-add off: no promise it is added: ' + text(byTest('ps-off')));
  assert(text(byTest('ps-rule')).includes('only when a choice is needed') && text(byTest('ps-rule')).includes('always'), 'auto rule and how to always ask');
  assert(text(byTest('print-setup')).includes('Use printer agents instead of print hosts'), 'names the OrcaSlicer option that skips it');
  assert(text(byTest('ps-agent')).includes('Printer Agent to u1control'), 'says how to pick U1 Control as the printer agent: ' + text(byTest('ps-agent')));
  assert(text(byTest('ps-agent')).includes('start ticked'), 'says the dialog boxes start ticked and the settings decide');
  assert(text(byTest('ps-agent')).includes('OrcaSlicer remembers the box'), 'says OrcaSlicer keeps an unticked box');
  await cfg({preset: '0.20 Standard @U1', on: true}, 'always');
  assert(!byTest('ps-off') && text(byTest('ps-on')).includes('runs for the process preset'), 'running: a plain line');
  assert(text(byTest('ps-rule')).includes('every print'), 'always rule');
  await cfg(null, 'never');
  assert(!byTest('ps-off') && !byTest('ps-on'), 'no U1 preset: nothing claimed about it');
`);

// PrimeVue's InputNumber reads only the locale's decimal sign; '.' typed or pasted must not turn 2.5 into 25.
for (const [lang, shown] of [['de_DE', '2,5'], ['es_ES', '2,5'], ['pt_BR', '2,5'], ['pl_PL', '2,5'], ['cs_CZ', '2,5'], ['en', '2.5']]) {
  test(`decimal input: "2.5" typed or pasted is 2.5 in ${lang}`, `
    await connect();
    await post({type: 'status', data: VIEW()});
    const field = q('#temp-0');
    await type(field, '2.5');
    eq(field.value, '${shown}', 'typed');
    await type(field, '');
    field.focus();
    const data = new DataTransfer();
    data.setData('text/plain', '2.5');
    field.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
    await settle();
    eq(field.value, '${shown}', 'pasted');
    if ('${shown}' === '2,5') { await type(field, '2,5'); eq(field.value, '2,5', 'the locale sign still works'); }
  `, { lang });
}

// ------------------------------------------------------------------ requirements (Settings > Requirements)

test('requirements: one section; each row says status, why and how; Check again asks anew', `
  await connect('stock');
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'spools'));
  await reply(last('cmd', 'spools'), {spools: [], bindings: {}, via: 'direct'});
  await tab('settings');
  await until(() => last('requirements'), 'the page asks which requirements are there');
  eq(last('requirements').recheck, false, 'a plain ask, not a recheck');
  await post({type: 'requirements', items: REQS('unknown', 'missing', 'missing', 'missing')});
  eq(qa('[data-test="requirements"]').length, 1, 'one Requirements section');
  eq(qa('[data-test="requirements"] .oui-req').map(r => r.dataset.test), ['req-agents', 'req-ext', 'req-spoolman', 'req-spooler'], 'four rows');
  eq(reqStatus('agents'), 'Not detected', 'agents: not detected');
  eq(q('.oui-status', reqRow('agents')).dataset.state, 'warn', 'a warning, not an error');
  assert(reqSteps('agents').some(x => x.includes('Developer tab > Experimental Features') && x.includes('Use printer agents instead of print hosts')), 'names the exact preference: ' + reqSteps('agents'));
  assert(reqSteps('agents').some(x => x.includes('Restart OrcaSlicer')), 'says to restart');
  eq(reqStatus('ext'), 'Official firmware', 'stock firmware');
  assert(reqSteps('ext').some(x => x.includes('firmware_config: true')), 'how to install the Extended Firmware');
  assert(q('a[href*="SnapmakerU1-Extended-Firmware"]', reqRow('ext')), 'links the project');
  eq(reqStatus('spoolman'), 'Not set', 'no Spoolman');
  assert(reqSteps('spoolman').some(x => x.startsWith('macOS')) && reqSteps('spoolman').some(x => x.startsWith('Linux')), 'one line per OS: ' + reqSteps('spoolman'));
  assert(q('a[href="https://github.com/Donkie/Spoolman"]', reqRow('spoolman')), 'official Spoolman link');
  eq(reqRow('spooler').dataset.status, 'missing', 'Spooler from the plugin check');
  eq(q('.oui-req-link', reqRow('spooler')).getAttribute('href'), 'https://example.invalid/spooler', 'Spooler install link');
  await post({type: 'requirements', items: REQS('ok', 'ok', 'ok')});
  eq(reqStatus('agents'), 'On', 'agents on');
  eq(reqStatus('spoolman'), 'Set', 'Spoolman set');
  assert(text(reqRow('spoolman')).includes('http://box:7912'), 'shows the address');
  eq(qa('[data-test="requirements"] .oui-req-install').length, 0, 'nothing to install: no steps');
  const before = cmds('spools').length;
  await click(q('.oui-req-check', reqRow('agents')));
  assert(sent().some(m => m.type === 'requirements' && m.recheck === true), 'Check again rechecks');
  assert(cmds('spools').length > before, 'and asks the printer for its Spoolman link again');
`);

test('requirements: printer screen stays on stock firmware, off, with its reason', `
  await connect('stock');
  await post({type: 'status', data: VIEW()});
  assert(byTest('screen-card'), 'the card is not hidden on stock firmware');
  assert(byTest('screen-show').disabled, 'Show screen is off');
  assert(text(byTest('screen-card')).includes('Needs the U1 Extended Firmware'), 'one-line reason: ' + text(byTest('screen-card')));
  await post({type: 'selection_changed'});
  await connect('extended');
  await post({type: 'status', data: VIEW()});
  assert(!byTest('screen-show').disabled, 'on the Extended Firmware it can be shown');
`);

test('requirements: no Spoolman turns stock links off with the reason', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK({same_spoolman: null}));
  await tab('stock');
  assert(stockRows().length && stockRows().every(b => !b.disabled), 'links on while Spoolman is not known missing');
  await post({type: 'requirements', items: REQS('unknown', 'missing', 'missing')});
  assert(stockRows().every(b => b.disabled && b.getAttribute('aria-describedby') === 'stock-why'), 'links off, pointing at the reason');
  assert(text(byTest('stock-why')).includes('no Spoolman'), 'visible reason: ' + text(byTest('stock-why')));
  await post({type: 'requirements', items: REQS('unknown', 'missing', 'ok')});
  assert(stockRows().every(b => !b.disabled) && !byTest('stock-why'), 'Spoolman set: links on again');
`);

test('Apply to project filaments: busy until the plugin answers, then says what it applied or why not', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await click(byTest('sync'));
  const m = last('sync_project');
  assert(typeof m.id === 'number', 'asked with an id, so the plugin answers this click');
  assert(byTest('sync').disabled, 'busy while OrcaSlicer applies');
  await click(byTest('sync'));
  eq(sent().filter(x => x.type === 'sync_project').length, 1, 'a second click sends nothing');
  await reply(m, {text: 'Project filaments 1: Generic PLA, 2: Generic PETG', done: 2, problems: 0});
  await until(() => toasts().includes('Generic PETG'), 'what was applied is shown: ' + toasts());
  assert(!byTest('sync').disabled, 'free again');
  await click(byTest('sync'));
  await reply(last('sync_project'), {text: 'Project filaments unchanged. Problems: filament 1: no preset', done: 0, problems: 1});
  await until(() => q('.oui-toast[role=alert]') && toasts().includes('no preset'), 'why not is shown, as an error: ' + toasts());
`);

test('toolhead cards: the OrcaSlicer preset Apply gives each head, its score and reasons; Change remembers another', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await until(() => last('preset_matches'), 'the cards ask for the presets once the heads are known');
  const ask = last('preset_matches');
  const choices = [{name: 'Generic PLA @U1', score: 35, reasons: [['material', 'PLA'], ['generic', ''], ['printer', '']]},
                   {name: 'Generic PLA Silk @U1', score: 29, reasons: [['material', 'PLA'], ['extra_word', 'silk']]}];
  const row = {head: 0, name: 'Generic PLA @U1', source: 'auto', score: 35, reasons: choices[0].reasons, confident: false, candidates: choices, remembered_key: ''};
  await reply(ask, {matches: [row]});
  await until(() => q('[data-match="0"]'), 'T1 shows its preset');
  const card = q('[data-match="0"]');
  assert(text(card).includes('Generic PLA @U1') && text(card).includes('material PLA') && text(card).includes('Score 35'), 'name, reasons, score: ' + text(card));
  assert(q('.oui-status[data-state="warn"]', card), 'a close call is marked');
  assert(!q('[data-match="1"]'), 'no line for a head the plugin gave no preset');
  await click(q('.oui-match-change', card));
  await until(() => qa('.oui-match-option', card).length === 2, 'the candidates, no Automatic while nothing was picked by hand');
  await click(qa('.oui-match-option', card)[1]);
  const pick = last('preset_pick');
  eq([pick.head, pick.name], [0, 'Generic PLA Silk @U1'], 'remembered for T1');
  await reply(pick, {matches: [{...row, name: 'Generic PLA Silk @U1', source: 'remembered', score: 29, reasons: choices[1].reasons, confident: true, remembered_key: 'mat:g|pla|'}]});
  await until(() => text(q('[data-match="0"]')).includes('Picked by hand'), 'the new pick, marked as picked by hand');
  await click(q('.oui-match-change', q('[data-match="0"]')));
  const auto = () => qa('.oui-match-option', q('[data-match="0"]')).find(b => text(b).includes('Automatic'));
  await until(auto, 'Automatic offered');
  await click(auto());
  eq(last('preset_pick').name, null, 'Automatic forgets the pick');
`);

// ------------------------------------------------------------------ foundation 4.2.0 on: toasts, dismissible notices, requirements
test('toasts: bottom-left, each with a Close button, gone once closed', `
  await connect();
  await post({type: 'notice', text: 'Project filaments updated'});
  await until(() => q('.oui-toast'), 'toast shown');
  const host = q('.oui-toasts');
  eq(qa('.oui-toasts').length, 1, 'one toast host on the page');
  const toast = q('.oui-toast'), r = toast.getBoundingClientRect();
  assert(r.left <= 20 && innerHeight - r.bottom <= 20 && r.bottom <= innerHeight, 'bottom-left: ' + JSON.stringify(r));
  eq(toast.getAttribute('role'), 'status', 'an info toast is polite');
  assert(toasts().includes('Project filaments updated'), 'text shown: ' + toasts());
  const close = q('.oui-toast-close', toast);
  eq(close && close.getAttribute('aria-label'), 'Close', 'Close button named');
  await click(close);
  await until(() => !toasts().includes('Project filaments updated'), 'toast closed');
  await post({type: 'reply', id: 99999, error: 'boom'});
  const err = qa('.oui-toast').find(t => text(t).includes('boom'));
  assert(err && err.getAttribute('role') === 'alert', 'an error toast is an alert');
  assert(err.parentElement.closest('.oui-toasts') === host, 'in the same host');
`);

test('notices: a closed banner stays closed while its condition holds and comes back when it starts again', `
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  const busyBanner = () => qa('.oui-banner').find(b => text(b).includes('busy'));
  assert(busyBanner(), 'busy banner shown');
  const close = q('.oui-banner-close', busyBanner());
  eq(close && close.getAttribute('aria-label'), 'Close', 'Close button named');
  await click(close);
  assert(!busyBanner(), 'closed');
  await post({type: 'status', data: VIEW({state: 'printing', busy: true, progress: 0.5})});
  await post({type: 'status', data: VIEW({state: 'printing', busy: true, progress: 0.6})});
  assert(!busyBanner(), 'stays closed across polls with the same condition');
  await post({type: 'status', data: VIEW()});
  await sleep(5);
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  assert(busyBanner(), 'back when the printer is busy again');
  // unconfirmed filament use: keyed on the entries
  const entry = id => ({id, at: null, spool: 7, grams: 1, head: 0, file: 'a.gcode', error: 'x', printer: 'u1:80', printer_name: 'Bench U1'});
  const usage = list => ({pending: [], unconfirmed: list, acknowledged: [], acknowledged_total: 0, save_error: '', restore_notice: ''});
  await until(() => last('cmd', 'usage'), 'usage asked');
  await reply(last('cmd', 'usage'), usage([entry('a')]));
  await until(() => byTest('usage-banner'), 'usage banner');
  await click(q('.oui-banner-close', byTest('usage-banner')));
  assert(!byTest('usage-banner'), 'usage banner closed');
  await post({type: 'status', data: VIEW({progress: 0.1})});
  assert(!byTest('usage-banner'), 'same entries: stays closed across a poll');
`);

test('settings: requirements say what was found; Check again asks again', `
  await connect();
  await tab('settings');
  await click(q('.oui-settings-link[data-section="requirements"]'));
  await post({type: 'requirements', items: REQS('unknown', 'unknown', 'unknown', 'missing')});
  const sp = byTest('req-spooler'), sm = byTest('req-spoolman');
  assert(sp && sm, 'Spoolman and Spooler rows');
  eq(sp.dataset.status, 'missing', 'Spooler not found');
  assert(text(sp).includes('Not found') && text(sp).includes('Install Spooler'), 'says so and how to get it: ' + text(sp));
  await click(q('.oui-req-check', sp));
  const ask = [...sent()].reverse().find(m => m.type === 'requirements' && m.recheck === true);
  assert(ask, 'Check again asks the plugin to look again');
  eq(byTest('req-spooler').dataset.status, 'checking', 'checking while it looks');
  await post({type: 'requirements', items: REQS('unknown', 'unknown', 'unknown', 'ok')});
  eq(byTest('req-spooler').dataset.status, 'found', 'found after installing');
  assert(text(byTest('req-spooler')).includes('Found') && !q('.oui-req-link', byTest('req-spooler')), 'no install link once found');
  await reply(last('cmd', 'spools'), {spools: ROWS, bindings: {}, via: 'direct'});
  await post({type: 'requirements', items: REQS('unknown', 'unknown', 'ok', 'ok')});
  eq(byTest('req-spoolman').dataset.status, 'found', 'Spoolman reached');
  assert(q('.oui-req-check', byTest('req-spoolman')).disabled, 'Spoolman Check again off while the printer has sent no status');
  await post({type: 'status', data: VIEW()});
  assert(!q('.oui-req-check', byTest('req-spoolman')).disabled, 'on once the printer answers');
  await post({type: 'offline', error: 'timed out'});
  assert(q('.oui-req-check', byTest('req-spoolman')).disabled, 'off again while the printer is offline');
  await post({type: 'status', data: VIEW()});
  const before = cmds('spools').length;
  await click(q('.oui-req-check', byTest('req-spoolman')));
  eq(cmds('spools').length, before + 1, 'Check again loads the spools again');
  await fail(last('cmd', 'spools'), 'connection refused');
  eq(byTest('req-spoolman').dataset.status, 'missing', 'Spoolman not reached');
  assert(text(byTest('req-spoolman')).includes('connection refused'), 'says why');
`);

test('settings: requirements Check again stops after 10 s without an answer and says so', `
  await connect();
  await tab('settings');
  await click(q('.oui-settings-link[data-section="requirements"]'));
  await post({type: 'requirements', items: REQS('unknown', 'unknown', 'unknown', 'missing')});
  await click(q('.oui-req-check', byTest('req-spooler')));
  eq(byTest('req-spooler').dataset.status, 'checking', 'checking while it looks');
  await sleep(10500);
  eq(byTest('req-spooler').dataset.status, 'missing', 'Checking ends after 10 s');
  assert(alerts().includes('did not answer within 10 s'), 'says the plugin did not answer: ' + alerts());
`);

test('settings: a toast sits above the sticky save bar', `
  await connect();
  await post({type: 'config', mode: 'automagic', stored: {}, version: 't', spooler: {installed: true},
    settings: {mode: 'automagic', host: '', api_key: '', printer_name: 'Bench U1', spoolman_url: ''}, automations: []});
  await tab('settings');
  await post({type: 'notice', text: 'Project filaments updated'});
  await until(() => q('.oui-toast'), 'toast shown');
  await sleep(400); await frame();
  const bar = q('.oui-settings-foot').getBoundingClientRect(), toast = q('.oui-toast').getBoundingClientRect();
  assert(bar.height > 0, 'save bar on screen');
  assert(toast.bottom <= bar.top, 'toast bottom ' + toast.bottom + ' <= save bar top ' + bar.top);
`);

test('power loss: the banner with Resume and Discard cannot be closed', `
  await connect();
  await post({type: 'status', data: VIEW({power_loss: true})});
  const b = byTest('power-loss');
  assert(b && qa('button', b).length === 2, 'banner with its two actions: ' + text(b));
  assert(!q('.oui-banner-close', b), 'no Close button');
`);

test('notices: dismissals are keyed on the condition, survive a remount and are forgotten when it clears', `
  await connect();
  await post({type: 'status', data: VIEW()});
  await post({type: 'offline', error: 'timed out'});
  await until(() => byTest('heads-why'), 'offline banner');
  await click(q('.oui-banner-close', byTest('heads-why')));
  assert(!byTest('heads-why'), 'closed');
  eq(sessionStorage.getItem('oui-banner:offline:u1:80'), '1', 'remembered under the printer, not a time (survives a reload)');
  await post({type: 'offline', error: 'timed out again'});
  assert(!byTest('heads-why'), 'stays closed while still offline');
  await post({type: 'status', data: VIEW()});
  eq(sessionStorage.getItem('oui-banner:offline:u1:80'), null, 'forgotten once the printer answers');
  await post({type: 'offline', error: 'timed out'});
  assert(byTest('heads-why') && text(byTest('heads-why')).includes('doesn'), 'shown again when it goes offline again');
  // the unconfirmed-use card is hidden (v-show) when empty, so its banner sees its condition clear
  const entry = id => ({id, at: null, spool: 7, grams: 1, head: 0, file: 'a.gcode', error: 'x', printer: 'u1:80', printer_name: 'Bench U1'});
  const usage = list => ({pending: [], unconfirmed: list, acknowledged: [], acknowledged_total: 0, save_error: '', restore_notice: ''});
  await until(() => last('cmd', 'usage'), 'usage asked');
  await reply(last('cmd', 'usage'), usage([entry('a')]));
  await click(q('.oui-banner-close', byTest('usage-banner')));
  assert(!byTest('usage-banner'), 'usage banner closed');
  eq(sessionStorage.getItem('oui-banner:unconfirmed:a'), '1', 'keyed on the entry ids');
`);

// ------------------------------------------------------------------ settings pages (one page per section)
const PAGES = ['mode', 'print-setup', 'options', 'calibration', 'connection', 'firmware', 'requirements', 'language', 'about'];
const PAGES_JS = `
const PAGES = ${JSON.stringify(PAGES)};
const link = id => q('.oui-settings-link[data-section="' + id + '"]');
const shown = () => PAGES.filter(id => q('#' + id) && !q('#' + id).hidden);
const onHeading = id => document.activeElement === q('#' + id + ' .oui-panel-title');
const listShown = () => getComputedStyle(q('.oui-settings-nav')).display !== 'none';
const pageShown = () => getComputedStyle(q('.oui-settings-body')).display !== 'none';
const CFG = () => post({type: 'config', mode: 'automagic', stored: {}, version: '0.7.0', spooler: {}, automations: [], settings: {mode: 'automagic'}});
`;
test('settings pages: list beside one page; a page opens with focus on its heading and is remembered', PAGES_JS + `
  await connect(); await CFG();
  await tab('settings');
  eq(qa('.oui-settings-link').map(e => e.dataset.section), PAGES, 'one page per section');
  eq(shown(), ['mode'], 'only the first page');
  assert(listShown() && pageShown() && !byTest('settings-back').getClientRects().length, 'wide: list and page side by side, no Back');
  await click(link('calibration'));
  eq(shown(), ['calibration'], 'only Calibration');
  assert(onHeading('calibration'), 'focus on the page heading');
  assert(Object.entries(localStorage).some(([k, v]) => k.startsWith('oui-settings:') && v === 'calibration'), 'last page stored');
  link('calibration').focus(); await press('ArrowDown'); await settle();
  eq([shown(), document.activeElement.dataset.section], [['connection'], 'connection'], 'arrow keys move along the list');
  assert(byTest('save'), 'one save bar');
`);
test('settings pages: narrow shows the list, then one page with Back', PAGES_JS + `
  await connect(); await CFG();
  await tab('settings');
  assert(listShown() && !pageShown(), 'narrow: the list first');
  await click(link('connection'));
  assert(!listShown() && pageShown(), 'then the page alone');
  eq(shown(), ['connection'], 'Connection only');
  assert(onHeading('connection'), 'focus on its heading');
  assert(byTest('settings-back').getClientRects().length, 'Back shown');
  await click(byTest('settings-back'));
  assert(listShown() && !pageShown(), 'Back returns to the list');
  eq(document.activeElement, link('connection'), 'focus back on the page it came from');
`, { size: [600, 900] });
test('settings pages: the last page opens again; Plugin settings opens Print setup, also before the config came', PAGES_JS + `
  await connect();
  await tab('settings');
  eq(shown(), ['language'], 'remembered page');
  await tab('dash');
  await post({type: 'show_tab', tab: 'settings'});
  eq(shown(), ['language'], 'Print setup is not there yet: the page stays');
  await CFG();
  await until(() => shown()[0] === 'print-setup', 'Print setup opened once it exists');
  assert(onHeading('print-setup'), 'heading focused');
`, { lastPage: 'language' });
test('settings pages: with no printer the address entered in Connection is saved and connects', PAGES_JS + `
  await until(() => last('hello'));
  const first = last('hello');
  // The plugin sends the config along with the no-target answer (plugin.py hello), so Settings can save.
  await CFG();
  await fail(first, 'Select a Snapmaker U1 printer', {no_target: true});
  await click(btn('Open Settings'));
  eq(shown(), ['connection'], 'Connection page');
  await type(q('#c-host'), '192.0.2.10');
  assert(!byTest('save').disabled, 'Save is on');
  await click(byTest('save'));
  const save = last('save_settings');
  eq(save.settings.host, '192.0.2.10', 'address sent');
  await reply(save, {saved: true});
  await until(() => last('hello') !== first, 'saved: the page says hello again, which connects');
`, { lastPage: 'about' });
test('settings pages: Open Settings with no printer opens Connection', PAGES_JS + `
  await until(() => last('hello'));
  await fail(last('hello'), 'Select a Snapmaker U1 printer', {no_target: true});
  await click(btn('Open Settings'));
  eq(shown(), ['connection'], 'Connection page');
  assert(onHeading('connection'), 'heading focused');
`, { lastPage: 'about' });
// U1: what the shared dashboard scenarios need to know about this page.
const DASH_PLUGIN = `
const STORE = dash => post({type: 'config', mode: 'automagic', stored: {}, version: 't', spooler: {}, automations: [], settings: {mode: 'automagic', dashboard: dash}});
async function READY(dash) { await connect(); if (dash !== undefined) await STORE(dash); await post({type: 'status', data: VIEW()}); }
const DEFAULT_IDS = ['job', 'heads', 'temps', 'controls', 'camera', 'screen', 'console'];
const DEFAULT_ORDER = ['job', 'temps', 'controls', 'heads', 'camera', 'screen', 'console'];
const ALL_IDS = ['job', 'heads', 'temps', 'controls', 'camera', 'console', 'screen', 'files', 'ace'];
const MOVER = 'camera', MOVER_FROM = '6 / span 3 | 8 / span 8', MOVE_COLS = -3, MOVER_TO = '9 / span 3 | 8 / span 8';
const CAM_W = 3, CAM_H = 8, TEMPS = 'temps', CONSOLE_LEAST = 'span 3 | span 5';
const OLD_DEFAULT = [{id: 'job', x: 0, y: 0, w: 12, h: 3}, {id: 'heads', x: 0, y: 3, w: 12, h: 10}, {id: 'controls', x: 0, y: 13, w: 8, h: 6},
  {id: 'camera', x: 8, y: 13, w: 4, h: 6}, {id: 'temps', x: 0, y: 19, w: 8, h: 7}, {id: 'screen', x: 8, y: 19, w: 4, h: 7}, {id: 'console', x: 0, y: 26, w: 12, h: 7}];
const MINE_CAMERA = '9 / span 4 | 14 / span 8';
// 0.16.0's default, also replaced while untouched
const DEFAULT_016 = [{id: 'job', x: 0, y: 0, w: 6, h: 2}, {id: 'heads', x: 0, y: 2, w: 6, h: 14}, {id: 'controls', x: 6, y: 0, w: 6, h: 4},
  {id: 'temps', x: 6, y: 4, w: 3, h: 8}, {id: 'camera', x: 9, y: 4, w: 3, h: 8}, {id: 'screen', x: 6, y: 12, w: 6, h: 4}, {id: 'console', x: 0, y: 16, w: 12, h: 6}];
// Narrow, a fan's field goes under its name instead of beside it.
const TEMPS_COMPACT = () => { const c = qa('.oui-control-row-control', cell('temps')); return c.length > 0 && c.every(e => e.getBoundingClientRect().top >= e.parentElement.firstElementChild.getBoundingClientRect().bottom - 1); };
`;
const CONSOLE_CHECK = `
  assert(q('#console-cmd', cell('console')) && q('[role=log]', cell('console')), 'the command line and its log');
`;
const SETTINGS_CHECK = `
  await click(q('[data-settings="temps"]'));
  await click(q('input', q('[data-setting="chamber"]', byTest('dash-settings'))));
`;
const SETTINGS_AFTER = `
  assert(!text(cell('temps')).includes('Chamber'), 'the temperatures widget leaves the chamber out: ' + text(cell('temps')));
  eq(itemOf(saved(), 'temps').cfg, {chamber: false}, 'its setting is saved');
`;
// ------------------------------------------------------------------ the dashboard as a layout the user arranges (OuiDashboard)
// Real pointer input (Input.dispatchMouseEvent): HTML5 drag and drop never reaches a page in OrcaSlicer on macOS.
const DASH_JS = DASH_PLUGIN + `
const cell = id => q('.oui-dash-cell[data-widget="' + id + '"]');
const frame = id => q('[data-frame="' + id + '"]');
const handle = (id, h) => q('[data-frame="' + id + '"] [data-handle="' + h + '"]');
const place = id => { const c = cell(id); return c ? c.style.gridColumn + ' | ' + c.style.gridRow : null; };
const step = () => (q('.oui-dash-grid').getBoundingClientRect().width + 12) / 12;
const ROW = 44;
const mouseAt = (type, x, y) => cdp({op: 'mouse', type, x, y});
async function grab(el, at) { el.scrollIntoView({block: 'center'}); await settle(); const r = el.getBoundingClientRect(); const p = at ? at(r) : [r.left + r.width / 2, r.top + r.height / 2]; await mouseAt('mousePressed', ...p); return p; }
async function dragBy(el, dx, dy, opts = {}) {
  const [x, y] = await grab(el, opts.at);
  for (let i = 1; i <= 5; i++) await mouseAt('mouseMoved', x + dx * i / 5, y + dy * i / 5);
  if (opts.during) await opts.during();
  await mouseAt('mouseReleased', x + dx, y + dy);
}
const saved = () => last('dashboard') && last('dashboard').value;
const itemOf = (st, id) => st.layouts[st.active].items.find(i => i.id === id);
const shown = () => qa('.oui-dash-cell').filter(c => c.getClientRects().length).map(c => c.dataset.widget);
async function edit() { await click(byTest('dash-edit')); assert(q('.oui-dash-board[data-editing]'), 'edit mode on'); }
`;

test('dashboard: the console is a widget of the default layout and there is no Console tab', DASH_JS + `
  await READY();
  assert(!q('[data-tab="console"]'), 'no Console tab');
  assert(cell('console') && cell('console').contains(byTest('console')), 'the console sits in a dashboard cell');
  eq(shown(), DEFAULT_IDS, 'the default layout');
  assert(!q('.oui-dash-frame') && !q('.oui-dash-handle'), 'no frames or handles outside edit mode');
` + CONSOLE_CHECK);

test('dashboard: drag a widget with the pointer; the others make room; Escape puts it back', DASH_JS + `
  await READY();
  await edit();
  eq(place(MOVER), MOVER_FROM, 'starts at its default place');
  const before = JSON.stringify(qa('.oui-dash-cell').map(c => [c.dataset.widget, c.style.gridColumn, c.style.gridRow]));
  await dragBy(frame(MOVER), -MOVE_COLS * step(), 0, { during: async () => { await settle();
    assert(q('.oui-dash-slot'), 'the place it would land is marked');
    assert(cell(MOVER).dataset.dragged !== undefined && cell(MOVER).style.transform.includes('translate'), 'the widget follows the pointer'); } });
  await settle();
  eq(place(MOVER), MOVER_TO, 'dropped where the pointer left it');
  assert(!q('.oui-dash-slot'), 'no marker after the release');
  const cells = qa('.oui-dash-cell').map(c => c.getBoundingClientRect());
  assert(cells.every((a, i) => cells.every((b, j) => i === j || a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1)), 'no widgets overlap');
  // a drag cancelled with Escape changes nothing
  const now = place(MOVER);
  const [x, y] = await grab(frame(MOVER));
  for (let i = 1; i <= 4; i++) await mouseAt('mouseMoved', x + i * step(), y + i * ROW);
  await cdp({op: 'key', key: 'Escape'});
  await mouseAt('mouseReleased', x + 4 * step(), y + 4 * ROW);
  eq(place(MOVER), now, 'Escape cancels the drag');
  eq(last('dashboard'), undefined, 'nothing stored before Save');
  await click(byTest('dash-cancel'));
  eq(JSON.stringify(qa('.oui-dash-cell').map(c => [c.dataset.widget, c.style.gridColumn, c.style.gridRow])), before, 'Cancel drops the edit');
`);

test('dashboard: resize from a corner and from an edge snaps to the grid, keeps a least size and is saved', DASH_JS + `
  await READY();
  await edit();
  await dragBy(handle('camera', 'se'), 2 * step(), 2 * ROW);
  eq(place('camera').replace(/\\d+ \\/ /g, ''), 'span ' + (CAM_W + 2) + ' | span ' + (CAM_H + 2), 'the corner grows width and height by whole cells');
  await dragBy(handle('camera', 's'), 0, -1 * ROW);
  eq(place('camera').split(' | ')[1].replace(/\\d+ \\/ /, ''), 'span ' + (CAM_H + 1), 'the bottom edge changes the height only');
  await dragBy(handle('camera', 'w'), 2 * step(), 0);
  eq(place('camera').split(' | ')[0].replace(/\\d+ \\/ /, ''), 'span ' + CAM_W, 'the left edge changes the width and the column');
  await dragBy(handle('camera', 'se'), -12 * step(), -12 * ROW);
  eq(place('camera').replace(/\\d+ \\/ /g, ''), 'span 3 | span 4', 'not smaller than the least size of the camera');
  await click(byTest('dash-save'));
  const cam = itemOf(saved(), 'camera');
  eq([cam.w, cam.h], [3, 4], 'the size is saved');
  assert(!q('.oui-dash-board[data-editing]'), 'Save ends edit mode');
  eq(place('camera').replace(/\\d+ \\/ /g, ''), 'span 3 | span 4', 'and stays after it');
`);

test('dashboard: widget content follows its size: the camera keeps its shape, the console shows more lines, temperatures go compact', DASH_JS + `
  await READY();
  const ratio = () => { const r = q('.oui-camera', cell('camera')).getBoundingClientRect(); return r.width / r.height; };
  assert(Math.abs(ratio() - 16 / 9) < 0.05, 'camera 16:9: ' + ratio());
  const logH = () => byTest('console-log').getBoundingClientRect().height;
  const small = logH();
  await edit();
  await dragBy(handle('camera', 'e'), 3 * step(), 0);
  await dragBy(handle('console', 's'), 0, 4 * ROW);
  if (!cell(TEMPS)) { await click(byTest('dash-add')); await click(q('[data-add="' + TEMPS + '"]')); }
  await dragBy(handle(TEMPS, 'e'), -12 * step(), 0);
  await dragBy(handle(TEMPS, 's'), 0, -12 * ROW);
  await click(byTest('dash-save'));
  assert(Math.abs(ratio() - 16 / 9) < 0.05, 'camera still 16:9 when wider: ' + ratio());
  assert(logH() > small + 3 * ROW, 'a taller console has a taller log: ' + small + ' -> ' + logH());
  assert(TEMPS_COMPACT(), 'a small temperatures widget is compact');
  await edit();
  await click(q('[data-settings="camera"]'));
  await pick(q('[data-setting="aspect"]', byTest('dash-settings')), '4:3');
  await click(byTest('dash-save'));
  eq(itemOf(saved(), 'camera').cfg, {aspect: '4/3'}, 'the setting is saved');
  assert(Math.abs(ratio() - 4 / 3) < 0.05, 'camera 4:3: ' + ratio());
`);

test('dashboard: keyboard moves, resizes and removes; the catalogue adds; settings apply', DASH_JS + `
  await READY();
  await edit();
  await click(byTest('dash-add'));
  const cat = byTest('dash-catalogue');
  eq(qa('[data-widget]', cat).map(e => e.dataset.widget), ALL_IDS, 'every widget is in the catalogue');
  assert(!q('[data-add="console"]', cat) && q('[data-add="files"]', cat), 'widgets on the layout are marked, the others can be added');
  await click(q('[data-add="files"]', cat));
  assert(cell('files') && frame('files'), 'added');
  frame('files').focus();
  const at = () => cell('files').style.gridColumn;
  const was = at();
  await cdp({op: 'key', key: 'ArrowRight'}); await cdp({op: 'key', key: 'ArrowRight'});
  assert(at() !== was, 'arrows move it: ' + was + ' -> ' + at());
  eq(document.activeElement, frame('files'), 'focus stays on the widget');
  const w = () => Number(/span (\\d+)/.exec(cell('files').style.gridColumn)[1]);
  const w0 = w();
  await cdp({op: 'key', key: 'ArrowLeft', shift: true});
  eq(w(), w0 - 1, 'Shift and an arrow resize');
  assert(text(q('.oui-dash-board > .oui-sr')).includes('column'), 'the new place is said');
  await cdp({op: 'key', key: 'Delete'});
  assert(!cell('files'), 'Delete removes it');
  await click(q('[data-remove="console"]'));
  assert(!cell('console'), 'Remove takes a widget off');
  assert(byTest('dash-catalogue'), 'the catalogue stays open');
  await click(q('[data-add="console"]'));
  await click(q('[data-settings="console"]'));
  await pick(q('[data-setting="lines"]', byTest('dash-settings')), '100');
` + SETTINGS_CHECK + `
  await click(byTest('dash-save'));
  eq(itemOf(saved(), 'console').cfg.lines, 100, 'console keeps 100 lines');
  assert(!itemOf(saved(), 'files'), 'the removed widget is not saved');
` + SETTINGS_AFTER);

test('dashboard: named layouts are created, switched, renamed, reset and deleted, and come back after a reload', DASH_JS + `
  await READY();
  await edit();
  await click(byTest('dash-new'));
  await type(q('#oui-dash-name'), 'default');
  await click(byTest('dash-name-ok'));
  assert(text(byTest('dash-strip')).includes('Another layout has this name'), 'a name in use is refused');
  await type(q('#oui-dash-name'), 'Watch');
  await click(byTest('dash-name-ok'));
  eq(saved().layouts.map(l => l.name), ['Default', 'Watch'], 'created');
  eq(saved().active, 1, 'and opened');
  await click(q('[data-remove="console"]'));
  await click(q('[data-remove="' + MOVER + '"]'));
  await click(byTest('dash-save'));
  eq(shown().includes('console'), false, 'Watch has no console');
  await pick(byTest('dash-layout'), 'Default');
  eq(saved().active, 0, 'switching is stored');
  assert(cell('console'), 'Default still has its console');
  await pick(byTest('dash-layout'), 'Watch');
  await edit();
  await click(byTest('dash-rename'));
  await type(q('#oui-dash-name'), 'Camera view');
  await press('Enter');
  eq(saved().layouts.map(l => l.name), ['Default', 'Camera view'], 'renamed');
  await click(byTest('dash-reset'));
  eq(shown(), DEFAULT_IDS, 'reset brings the default widgets back');
  await click(byTest('dash-cancel'));
  eq(shown().includes('console'), false, 'a reset is kept only by Save');
  await edit();
  await click(byTest('dash-delete'));
  await click(byTest('dash-delete-ok'));
  eq(saved().layouts.map(l => l.name), ['Default'], 'deleted');
  assert(!byTest('dash-delete') || byTest('dash-delete').disabled, 'the last layout cannot be deleted');
  await click(byTest('dash-cancel'));
  // a second layout to bring back after the reload
  await edit();
  await click(byTest('dash-new'));
  await type(q('#oui-dash-name'), 'Night');
  await press('Enter');
  await click(q('[data-remove="camera"]'));
  await click(byTest('dash-save'));
  return { carry: saved() };
`, { after: DASH_JS + `
  await READY(CARRY);
  eq(q('.oui-dash-pick .p-select-label') && text(q('.oui-dash-pick .p-select-label')), 'Night', 'the open layout is the one saved');
  assert(!cell('camera') && cell('console'), 'its widgets as saved');
  await pick(byTest('dash-layout'), 'Default');
  assert(cell('camera'), 'the other layout is there too');
` });

test('dashboard: a stored layout is checked: unknown widgets dropped, sizes brought within limits, broken data gives the default', DASH_JS + `
  await READY({v: 1, active: 0, layouts: [{name: 'Mine', items: [{id: 'ghost', x: 0, y: 0, w: 4, h: 4}, {id: 'camera', x: 9, y: 3, w: 99, h: 1}, {id: 'console', x: 0, y: 0, w: 2, h: 2, cfg: {lines: 7}}]}]});
  eq(shown().sort(), ['camera', 'console'], 'the unknown widget is dropped');
  eq(place('camera').replace(/\\d+ \\/ /g, ''), 'span 12 | span 4', 'too wide and too short: brought within limits');
  eq(place('console').replace(/\\d+ \\/ /g, ''), CONSOLE_LEAST, 'the least size of the console');
  await STORE('not a dashboard');
  eq(shown(), DEFAULT_IDS, 'broken data: the default layout');
`);

test('dashboard: a widget is maximised and restored', DASH_JS + `
  await READY();
  await click(q('[data-test="widget-max"]', cell('console')));
  eq(shown(), ['console'], 'only the console');
  assert(cell('console').getBoundingClientRect().height > 400, 'as tall as the window allows');
  await cdp({op: 'key', key: 'Escape'});
  eq(shown(), DEFAULT_IDS, 'Escape restores the dashboard');
`);

test('dashboard: a narrow window shows one column in reading order and is not edited', DASH_JS + `
  await READY();
  assert(q('.oui-dash-grid[data-narrow]'), 'one column');
  const tops = DEFAULT_ORDER.map(id => cell(id).getBoundingClientRect().top);
  assert(tops.every((t, i) => !i || t > tops[i - 1]), 'in reading order: ' + tops.join());
  assert(byTest('dash-edit').disabled, 'Edit layout is off');
`, { size: [480, 900] });


test('dashboard: a layout still as the first default gets the new one; an arranged one stays; Reset gives the new one', DASH_JS + `
  await READY({v: 1, active: 0, layouts: [{name: 'Default', items: OLD_DEFAULT}, {name: 'Mine', items: OLD_DEFAULT.map(i => i.id === 'camera' ? {...i, h: i.h + 2} : i)}]});
  eq(shown(), DEFAULT_IDS, 'the untouched default shows the new default');
  eq(place(MOVER), MOVER_FROM, 'at its new place');
  await pick(byTest('dash-layout'), 'Mine');
  eq(place('camera'), MINE_CAMERA, 'the arranged layout is as it was saved');
  await edit();
  await click(byTest('dash-reset'));
  await click(byTest('dash-save'));
  eq(saved().layouts[1].items.map(i => i.id), DEFAULT_IDS, 'Reset to default gives the new default');
  eq(place(MOVER), MOVER_FROM, 'with its places');
`);
test('dashboard: 0.16.0\'s untouched default gets the arranged one; with multiACE the filament units join under the toolheads', DASH_JS + `
  await READY({v: 1, active: 0, layouts: [{name: 'Default', items: DEFAULT_016}]});
  eq(shown(), DEFAULT_IDS, 'the new default');
  eq(place(MOVER), MOVER_FROM, 'camera at its new place');
  await post({type: 'status', data: {...VIEW(), ace: {mode: 'multi', swapping: false, heads: {'0': [0, 1]}, units: []}}});
  await settle();
  eq(place('ace'), '1 / span 5 | 19 / span 6', 'filament units under the toolheads');
  eq(place(MOVER), MOVER_FROM, 'nothing else moved');
`);
for (const size of [[1280, 800], [1920, 1080]]) test(`dashboard: at ${size.join('x')} no widget of the default layout clips or scrolls inside`, DASH_JS + `
  await READY();
  const bad = qa('.oui-dash-cell').map(c => [c.dataset.widget, q('.oui-panel-body', c)]).filter(([, b]) => b && (b.scrollHeight > b.clientHeight + 1 || b.scrollWidth > b.clientWidth + 1))
    .map(([id, b]) => id + ' ' + b.scrollHeight + '/' + b.clientHeight);
  eq(bad, [], 'every widget fits');
`, { size });


test('dashboard: a stored size too small for its content shows all of it and is kept as stored', DASH_JS + `
  await READY({v: 1, active: 0, layouts: [{name: 'Tiny', items: [{id: 'job', x: 0, y: 0, w: 6, h: 2}, {id: 'console', x: 0, y: 2, w: 12, h: 6}]}]});
  const body = q('.oui-panel-body', cell('job'));
  assert(body.scrollHeight <= body.clientHeight + 1 && cell('job').getBoundingClientRect().height > 76, 'its rows grew to the content: ' + cell('job').getBoundingClientRect().height);
  eq(place('job'), '1 / span 6 | 1 / span 2', 'its stored size is not changed');
  eq(last('dashboard'), undefined, 'nothing is saved');
`);

// ------------------------------------------------------------------ toolhead cards: multi-colour, unnamed filament, no gap
// The fake U1 of the GUI tests: T2 a three-colour silk (filament_color_multi), T4 loaded but never named (all NONE).
for (const size of [[1440, 1000], [1920, 1080]]) test(`toolheads at ${size.join('x')}: every colour of a multi-colour spool, unnamed filament is not empty, no gap inside a card`, DASH_JS + `
  await READY();
  await post({type: 'status', data: VIEW({feed: [0, 1, 2, 3].map(() => ({state: 'load_finish'})), heads: [
    head('PLA', {index: 0, colour: '#E53935', colours: ['#E53935']}),
    head('PLA', {index: 1, sub_type: 'Silk', colour: '#FF0000', colours: ['#FF0000', '#00FF00', '#0000FF']}),
    head('PLA', {index: 2, sub_type: 'Silk', colour: '#FDD835', colours: ['#FDD835']}),
    {index: 3, loaded: false, unnamed: true, type: '', vendor: '', sub_type: '', colour: '#FFFFFF', colours: ['#FFFFFF'], official: false}]})});
  const cards = qa('.hc', cell('heads'));
  eq(cards.length, 4, 'four cards');
  const RGB = ['rgb(255, 0, 0)', 'rgb(0, 255, 0)', 'rgb(0, 0, 255)'];
  const strip = getComputedStyle(q('.oui-slot-strip', cards[1])).backgroundImage;
  assert(RGB.every(c => strip.includes(c)), 'T2: the strip shows every colour: ' + strip);
  const paint = q('.oui-spool', cards[1]).style.getPropertyValue('--oui-spool-paint').toUpperCase();
  assert(['#FF0000', '#00FF00', '#0000FF'].every(c => paint.includes(c)), 'T2: so does the spool: ' + paint);
  assert(!getComputedStyle(q('.oui-slot-strip', cards[0])).backgroundImage.includes('gradient'), 'T1: one colour, no segments');
  assert(cards[3].hasAttribute('data-unnamed') && !cards[3].hasAttribute('data-empty'), 'T4: loaded, not empty');
  assert(text(cards[3]).includes('Unnamed filament') && !text(cards[3]).includes('No filament') && !/\\bEmpty\\b/.test(text(cards[3])), 'T4 says so: ' + text(cards[3]));
  assert(q('.oui-slot-strip', cards[3]) && q('.oui-spool', cards[3]).style.getPropertyValue('--oui-spool-paint').toUpperCase() === '#FFFFFF', 'T4: in its colour');
  for (const [a, b] of [[0, 1], [2, 3]]) {
    const ra = cards[a].getBoundingClientRect(), rb = cards[b].getBoundingClientRect();
    eq([Math.round(ra.top), Math.round(ra.height)], [Math.round(rb.top), Math.round(rb.height)], 'T' + (a + 1) + ' and T' + (b + 1) + ' share a row');
    const inner = c => { const acts = q('.oui-slot-actions', c); return Math.round(acts.getBoundingClientRect().top - acts.previousElementSibling.getBoundingClientRect().bottom); };
    const gaps = [inner(cards[a]), inner(cards[b])];
    assert(Math.min(...gaps) <= 8, 'the fuller card of the row has its actions right after its content: ' + gaps);
    assert(Math.max(...gaps) <= 48, 'the other only what its neighbour has more: ' + gaps);
  }
  const body = q('.oui-panel-body', cell('heads'));
  assert(body.scrollHeight <= body.clientHeight + 1, 'the widget still fits its content');
`, { size });

// ------------------------------------------------------------------ runner
const workers = Number(process.env.WORKERS ?? 4);
if (!Number.isSafeInteger(workers) || workers < 1) throw new Error('WORKERS must be a positive integer');
const filter = process.argv[2];
const chosen = scenarios.filter(s => !filter || s.name.includes(filter));
const page = await builtPage();
const dir = await mkdtemp(join(tmpdir(), 'u1-page-'));
const browser = await launch();
let failed = 0;
const results = [];
try {
  await Promise.all(Array.from({ length: Math.min(workers, chosen.length) }, async (_, worker) => {
    for (let k = worker; k < chosen.length; k += workers) {
      const sc = chosen[k];
      const boot = sc.mode === 'setup' ? { mode: 'setup', version: 'test', lang: sc.lang ?? 'en', data: sc.data ?? SETUP_DATA }
        : { mode: 'app', version: 'test', lang: sc.lang ?? 'en', pref: sc.pref ?? 'auto' };
      const file = join(dir, `p${k}.html`);
      await writeFile(file, preparePage(page, boot));
      const p = await browser.newPage();
      const started = Date.now();
      try {
        await p.size(...(sc.size ?? [1280, 900]));
        // seed: the settings page remembered from an earlier visit (OuiSettings' own key: page path and its page ids)
        const seed = sc.lastPage ? `localStorage.setItem('oui-settings:' + location.pathname + ':' + ${JSON.stringify(PAGES.join(','))}, ${JSON.stringify(sc.lastPage)});` : '';
        await p.init(MOCK_HOST + `try { localStorage.clear(); ${seed} } catch {}`);
        await p.goto(pathToFileURL(file).href);
        // A scenario may return { carry }; its `after` runs on the same page loaded again (what the plugin stored, CARRY).
        const body = (code, carry) => `(async () => { ${HELPERS} ${PRELUDE} const GROUPS = ${JSON.stringify(GROUPS)}; const HEADS = ${JSON.stringify(SETUP_DATA.heads)};
          const CARRY = ${JSON.stringify(carry ?? null)};
          await until(() => document.querySelector('#app > *'), 'app mounted');
          const __r = await (async () => { ${code} })();
          await settle();
          return { carry: __r && __r.carry, violations: __t.violations, rejections: __t.rejections, errors: __t.errors };
        })()`;
        let probe = await p.evaluate(body(sc.body));
        if (probe.violations.length || probe.rejections.length || probe.errors.length) throw new Error('page problems: ' + JSON.stringify(probe));
        if (sc.after) {
          await p.goto(pathToFileURL(file).href);
          probe = await p.evaluate(body(sc.after, probe.carry));
          if (probe.violations.length || probe.rejections.length || probe.errors.length) throw new Error('page problems after reload: ' + JSON.stringify(probe));
        }
        results.push({ name: sc.name, ok: true, ms: Date.now() - started });
        console.log(`ok   ${sc.name}`);
      } catch (e) {
        failed++;
        results.push({ name: sc.name, ok: false, error: String(e.message || e) });
        console.log(`FAIL ${sc.name}\n     ${String(e.message || e).split('\n')[0]}`);
      } finally {
        await p.close();
      }
    }
  }));
} finally {
  await browser.close();
  await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
if (process.env.RESULTS) await writeFile(process.env.RESULTS, JSON.stringify(results, null, 2));
console.log(`${chosen.length - failed}/${chosen.length} page scenarios passed`);
if (failed || !chosen.length) process.exit(1);
console.log('PASS');
