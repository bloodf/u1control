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
const alerts = () => qa('[role=alert] .oui-banner').map(text).join(' | ');
const ROWS = [{id: 7, filament_id: 70, name: 'Matte Black', vendor: 'Generic', material: 'PLA', colour: '#111111', colours: [], remaining: 500, low: false, use_first: false, location: 'Shelf A'},
  {id: 11, filament_id: 110, name: 'White', vendor: 'Acme', material: 'PETG', colour: '#FAFAFA', colours: [], remaining: 40, low: true, use_first: true, location: ''}];
const SP = state => ({state, text: state === 'active' ? 'Spooler is running' : 'Spooler was unloaded or disabled.', detail: '', version: '0.21.0', origin: 'http://box:7912'});
const STOCK = extra => ({spooler: SP('active'), stock: {state: 'ok', code: 'ok', text: '', rows: ROWS, key: 's1:3', ts: Date.now() / 1000, origin: 'http://box:7912'},
  same_spoolman: true, usage: 'u1control', bindings: {}, ...extra});
const stockRows = () => qa('[data-stock]');
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

test('thumbnails only for visible rows, two at a time, dropped on folder change', `
  await connect();
  await tab('files');
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
  await click(btn('Open folder sub'));
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
  await tab('console');
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

test('setup warning needs an acknowledgement tied to the current mapping', `
  const send = () => byTest('send');
  await until(() => send());
  assert(alerts().includes('PETG'), 'warning announced: ' + alerts());
  assert(send().disabled, 'send waits for the acknowledgement');
  await click(send());
  eq(__t.submits, [], 'nothing sent without it');
  await click(q('#su-ack'));
  assert(!send().disabled && text(send()).includes('1 warning'), 'says it sends with a warning: ' + text(send()));
  await click(q('button[data-f="1"][data-t="2"]'));      // PETG -> empty T3: another warning
  assert(!q('#su-ack').checked && send().disabled, 'a new warning needs a new acknowledgement');
  assert(document.body.textContent.includes('previous check was cleared'), 'says why the box was cleared');
  await click(q('#su-ack'));
  await click(send());
  eq(__t.submits.map(m => m.acknowledged), [['empty:1:2']], 'sends the ids it acknowledged');
  await click(send());
  eq(__t.submits.length, 1, 'a second click does not send twice');
`, { mode: 'setup' });

test('setup without warnings keeps the plain flow; empty toolhead is labelled, not faded', `
  await click(q('button[data-f="1"][data-t="3"]'));
  await post({heads: HEADS.map(h => h.index === 3 ? {...h, type: 'PETG'} : h), map: {}});
  assert(!alerts() && !q('#su-ack') && !byTest('send').disabled && text(byTest('send')) === 'Send to U1', 'no warning: unchanged flow');
  const empty = q('button[data-f="0"][data-t="2"]');
  assert(text(empty).includes('empty') && getComputedStyle(empty).opacity === '1' && !empty.disabled, 'empty is text, still selectable (B-08)');
  await click(byTest('send'));
  eq(__t.submits[0].acknowledged, [], 'nothing to acknowledge');
`, { mode: 'setup' });

test('setup keeps focus on the chosen button across clicks and refreshes', `
  const b = q('button[data-f="0"][data-t="3"]');
  b.focus();
  await press('Space');
  const at = () => [document.activeElement.dataset.f, document.activeElement.dataset.t];
  eq(at(), ['0', '3'], 'focus after choosing');
  assert(b.isConnected && document.activeElement === b, 'same element kept');
  await post({heads: HEADS, map: {}});
  eq(at(), ['0', '3'], 'focus after a live refresh');
  await post({heads: HEADS.map(h => ({...h, colour: '#654321'})), map: {}});
  eq(at(), ['0', '3'], 'focus after a changed refresh');
  eq(b.getAttribute('aria-pressed'), 'true', 'pressed state');
`, { mode: 'setup' });

test('stock card stays hidden without Spooler', `
  await connect();
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), {spooler: {...SP('absent'), text: "Spooler isn't running"}, stock: {state: 'unavailable', rows: [], key: ''}, same_spoolman: null, usage: 'u1control', bindings: {}});
  assert(!byTest('stock-card'), 'solo U1 Control shows no stock card');
  await sleep(2100);
  eq(last('lease').stock, false, 'no stock lease while hidden');
`);

test('stock lists, filters and links with the list key and printer generation', `
  await connect('stock', 4);
  await post({type: 'status', data: VIEW()});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
  assert(byTest('stock-card'), 'card shown while Spooler runs');
  assert(text(q('#stock-h')).includes('Stock (Spooler)'), 'named as stock of Spooler (X02)');
  eq(stockRows().length, 2, 'both spools listed');
  assert(text(byTest('stock-card')).includes('recorded in Spoolman by U1 Control'), 'says who records filament use');
  await type(q('input[type=search]'), 'white');
  eq(stockRows().length, 1, 'search filters');
  await type(q('input[type=search]'), '');
  await pick(q('[aria-label="Material"]').closest('.p-select') || q('[aria-label="Material"]'), 'PLA');
  eq(stockRows().map(b => b.dataset.stock), ['7'], 'material filter');
  await pick(byTest('stock-head'), 'T2');
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
`);

test('stock: a tagged head needs FORCE confirmation', `
  await connect();
  await post({type: 'status', data: VIEW({rfid: [{uid: 'AA'}, null, null, null]})});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
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
  assert(!byTest('stock-card'), 'an answer asked before the printer changed is not shown');
  await connect('stock', 2);
  await until(() => cmds('stock').length >= 2);
  await reply(last('cmd', 'stock'), STOCK());
  assert(byTest('stock-card') && !text(byTest('stock-card')).includes('on T1'), 'only the new answer counts');
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
  assert(stockRows().every(b => b.disabled), 'no link from another Spoolman');
  assert(q('.sc-notes .oui-banner[data-tone="danger"]') && text(q('.sc-notes .oui-banner[data-tone="danger"]')).includes('different Spoolman'), 'blocking reason as an error');
  assert(text(byTest('stock-why')).includes('Linking unavailable'), 'visible reason (U06)');
  await click(btn('Refresh stock'));
  eq(last('cmd', 'stock').args, {refresh: true}, 'Refresh asks Spooler for a new list');
  await reply(last('cmd', 'stock'), STOCK({stock: {...STOCK().stock, state: 'stale', ts: Date.now() / 1000 - 600}}));
  assert(byTest('stock-stale') && byTest('stock-stale').dataset.tone === 'warn' && text(byTest('stock-stale')).includes('out of date') && stockRows().length === 2, 'stale list stays, marked as a warning');
  assert(!q('[data-test="stock-card"] [data-tone="danger"], [data-test="stock-card"] [data-state="error"]'), 'stale is not shown as an error (U09)');
  await click(btn('Refresh stock'));
  await reply(last('cmd', 'stock'), STOCK({spooler: SP('stopped'), stock: {state: 'unavailable', rows: [], key: '', text: 'x'}}));
  assert(byTest('stock-card') && !stockRows().length && text(byTest('stock-card')).includes('unloaded'), 'stopped Spooler explained');
  await click(btn('Refresh stock'));
  await fail(last('cmd', 'stock'), 'the selected printer changed; nothing was sent to it');
  assert(q('.sc-notes .oui-empty[data-state="error"]') && text(q('.sc-notes')).includes('printer changed'), 'errors are shown, not swallowed');
`);

test('stock: busy printer disables links with a visible reason; refresh keeps focus', `
  await connect();
  await post({type: 'status', data: VIEW({busy: true, state: 'printing'})});
  await until(() => last('cmd', 'stock'));
  await reply(last('cmd', 'stock'), STOCK());
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
  const after = q('[data-test="stock-card"] .oui-panel-foot');
  assert(after && after.getBoundingClientRect().top >= wrap.getBoundingClientRect().bottom - 0.5, 'what follows the table starts below it');
  const note = byTest('stock-via');
  assert(note && text(note).includes('through the printer') && !note.closest('.oui-banner'), 'via-printer note is a plain line');
  eq(getComputedStyle(note).borderTopStyle, 'none', 'no border around the note');
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
  assert(byTest('estop') && byTest('estop').disabled && byTest('pause').disabled, 'connecting: E-stop and Pause shown, off');
  eq(byTest('estop').getAttribute('aria-describedby'), 'heads-why', 'connecting: E-stop points at the reason');
  assert(text(q('#heads-why')).includes('Connecting'), 'the reason says it is connecting: ' + text(q('#heads-why')));
  await connect();
  await post({type: 'status', data: VIEW({state: 'printing', busy: true})});
  for (const name of ['dash', 'files', 'console', 'settings']) {
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
  assert(byTest('pause').disabled && byTest('cancel').disabled, 'normal commands off');
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
  const dismiss = qa('[role=alert] .oui-banner').find(m => text(m).includes('Emergency stop failed')).querySelector('button');
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
  assert(!byTest('usage-card'), 'gone once checked');
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
  assert(!text(q('header')).toLowerCase().includes('stock'), 'header has no "stock"');
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

test('i18n: Deutsch, Español and 简体中文 can be chosen by hand and are kept', `
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
  eq(getComputedStyle(document.body).backgroundColor, 'rgb(17, 24, 42)', 'dark palette background (cobalt-tinted 4.0 palette)');
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
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(btn('Open folder sub'));
  eq(last('cmd', 'files').args.path, 'gcodes/sub', 'in the folder');
  await reply(last('cmd', 'files'), {path: 'gcodes/sub', dirs: [], files: []});
  const before = cmds('files').length;
  await post({type: 'selection_changed'});
  await connect('stock', 2);
  await until(() => cmds('files').length > before, 'listed again');
  eq(last('cmd', 'files').args.path, 'gcodes', 'top folder of the new printer');
`);

test('files: rename asks for the new name and never sends an unchanged one', `
  await connect();
  await tab('files');
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(btn('Rename benchy.gcode'));
  await until(dialogOpen);
  eq(q('#dlg-input').value, 'benchy.gcode', 'starts from the current name');
  await yes();
  eq(cmds('rename'), [], 'same name: nothing sent');
  await click(btn('Rename benchy.gcode'));
  await until(() => document.activeElement === q('#dlg-input'));
  await type(q('#dlg-input'), 'boat.gcode');
  await yes();
  eq(last('cmd', 'rename').args, {path: 'gcodes/benchy.gcode', name: 'boat.gcode'}, 'path and new name');
  const listed = cmds('files').length;
  await reply(last('cmd', 'rename'), {path: 'gcodes/boat.gcode'});
  await until(() => cmds('files').length > listed, 'listed again after the rename');
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(btn('Rename sub'));
  await until(dialogOpen);
  await no();
  eq(cmds('rename').length, 1, 'cancel sends nothing');
`);

test('files: filter by name and show each file\'s filament', `
  await connect();
  await tab('files');
  await until(() => last('cmd', 'files'));
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  assert(text(q('.u1-table')).includes('12 g'), 'filament weight shown: ' + text(q('.u1-table')));
  await type(q('#files-filter'), 'BEN');
  eq(qa('.fv-name').map(text), ['benchy.gcode'], 'case-insensitive match');
  assert(!btn('Open folder sub'), 'folders filtered too');
  await type(q('#files-filter'), 'zzz');
  assert(text(q('.u1-table')).includes('No file or folder matches'), 'says nothing matches');
  await type(q('#files-filter'), '');
  eq(qa('.fv-name').length, 2, 'all back');
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
  await reply(last('cmd', 'files'), ${JSON.stringify(FILES)});
  await click(btn('Refresh', q('#files-h').closest('section')));
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
  await until(() => text(q('.notices [role=status]')).includes('Saved to /home/u/Downloads/u1control/benchy_20261116130921.mp4'), 'says where it was saved');
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
  assert(text(q('.notices [role=status]')).includes('Deleted'), 'success is said');
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
  await click(byTest('camera'));
  eq(byTest('cam-save'), null, 'no button before the first picture');
  await post({type: 'frame', image: 'data:image/jpeg;base64,/9j/'});
  await click(byTest('cam-save'));
  const cmd = last('cmd', 'snapshot');
  eq(cmd.args, {}, 'asks the plugin to save its last picture');
  await reply(cmd, '/home/u/Downloads/u1control/Bench U1 2026-11-14 10-00-00.jpg');
  await until(() => text(q('.notices [role=status]')).includes('Saved to'), 'says where it was saved');
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
for (const [lang, shown] of [['de_DE', '2,5'], ['es_ES', '2,5'], ['pt_BR', '2,5'], ['en', '2.5']]) {
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
      const boot = sc.mode === 'setup' ? { mode: 'setup', version: 'test', lang: sc.lang ?? 'en', data: SETUP_DATA }
        : { mode: 'app', version: 'test', lang: sc.lang ?? 'en', pref: sc.pref ?? 'auto' };
      const file = join(dir, `p${k}.html`);
      await writeFile(file, preparePage(page, boot));
      const p = await browser.newPage();
      const started = Date.now();
      try {
        await p.size(1280, 900);
        await p.init(MOCK_HOST + 'try { localStorage.clear(); } catch {}');
        await p.goto(pathToFileURL(file).href);
        const body = `(async () => { ${HELPERS} ${PRELUDE} const GROUPS = ${JSON.stringify(GROUPS)}; const HEADS = ${JSON.stringify(SETUP_DATA.heads)};
          await until(() => document.querySelector('#app > *'), 'app mounted');
          ${sc.body}
          await settle();
          return { violations: __t.violations, rejections: __t.rejections, errors: __t.errors };
        })()`;
        const probe = await p.evaluate(body);
        if (probe.violations.length || probe.rejections.length || probe.errors.length) throw new Error('page problems: ' + JSON.stringify(probe));
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
