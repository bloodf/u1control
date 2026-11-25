// The print setup's boot data for the page scenarios and the screenshots (plugin.ask_setup builds the real one).
// A top view as preview.top_view sends it: a cell map run-length encoded as (count, tool, height, tools) quads.
const topView = (w, h, cell) => {
  const quads = [];
  let last = null;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [tool, height, tools] = cell(x, y), key = `${tool},${height},${tools}`;
    if (last && last.key === key && last.q[0] < 255) last.q[0]++;
    else quads.push((last = { key, q: [1, tool, height, tools] }).q);
  }
  return { w, h, bounds: [60, 60, 210, 210], runs: btoa(String.fromCharCode(...quads.flat())) };
};
const ring = (x, y, cx, cy, r0, r1) => { const d = Math.hypot(x - cx, y - cy); return d >= r0 && d <= r1; };
const DESK = topView(120, 120, (x, y) => {   // a tray (T0) with two cups (T1, T2), a block (T3) and an inlay under the top
  if (ring(x, y, 40, 40, 6, 18)) return [1, 255, 3];
  if (ring(x, y, 84, 84, 6, 18)) return [2, 255, 5];
  if (x >= 72 && x < 108 && y >= 8 && y < 44) return [3, 200, 9];
  if (x >= 4 && x < 116 && y >= 4 && y < 116) return [0, x > 4 && x < 115 && y > 4 && y < 115 ? 60 : 160, x > 14 && x < 60 && y > 80 && y < 96 ? 3 : 1];
  return [255, 0, 0];
});

export const SETUP_FULL = {
  job: { name: 'Desk organiser — plate 1', time: '2h 12m 34s', weight: '26.4', layers: 175, tool_changes: 522, address: '192.168.1.40',
    preview: DESK },
  purifier: 'auto', auto_purifier: 'weak',
  filaments: [{ index: 0, type: 'PETG', colour: '#3B82F6', weight: 6.9 }, { index: 1, type: 'PLA', colour: '#7C3AED', weight: 6.3 },
    { index: 2, type: 'PETG', colour: '#F97316', weight: 6.8 }, { index: 3, type: 'PLA', colour: '#FACC15', weight: 6.3 }],
  heads: [
    { index: 0, loaded: true, type: 'PETG', vendor: 'Generic', sub_type: 'Basic', colour: '#7BC86C' },
    { index: 1, loaded: true, type: 'PETG', vendor: 'Snapmaker', sub_type: 'Basic', colour: '#D946A8', official: true },
    { index: 2, loaded: true, type: 'PLA', vendor: 'Elegoo', sub_type: 'Matte', colour: '#60A5FA' },
    { index: 3, loaded: true, type: 'PLA', vendor: 'Generic', sub_type: 'Matte', colour: '#F59E0B' }],
  map: { 0: 0, 1: 2, 2: 1, 3: 3 },
  prefs: { bed_level: true, flow_calibrate: false, time_lapse_camera: true, auto_refill: true, refill_any_colour: false, tangle_detect: true, light_off_when_done: false,
    spaghetti_detect: true, bed_check: false, spaghetti_level: 'low', bed_check_level: 'high', tangle_level: 'medium', flow_calibrate_heads: [0, 1, 2, 3],
    exhaust_fan: 60, inner_fan: 60 },
  labels: {}, levels: { spaghetti_level: ['low', 'high'], bed_check_level: ['low', 'high'], tangle_level: ['low', 'medium', 'high'] },
  features: ['spaghetti_detect', 'spaghetti_level', 'bed_check', 'bed_check_level', 'tangle_level', 'flow_calibrate_heads', 'exhaust_fan', 'inner_fan', 'cover_fan'],
  printer: { name: 'Snapmaker U1', busy: false, address: '192.168.1.40' },
  spools: { 0: { name: 'Generic Leaf Green', colour: '#6CBF5A', remaining: 720, initial: 1000 }, 2: { name: 'Elegoo Sky Blue', colour: '#5B9BEA', remaining: 150, initial: 1000 } }, remember: true,
};
