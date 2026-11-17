// The print setup's boot data for the page scenarios and the screenshots (plugin.ask_setup builds the real one).
const ring = (cx, cy, r, n = 48) => Array.from({ length: n }, (_, i) => {
  const a = (i / n) * 2 * Math.PI, b = ((i + 1) / n) * 2 * Math.PI;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a), cx + r * Math.cos(b), cy + r * Math.sin(b)];
}).flat();
const box = (x0, y0, x1, y1) => [x0, y0, x1, y0, x1, y0, x1, y1, x1, y1, x0, y1, x0, y1, x0, y0];
const rings = (cx, cy, from, to) => Array.from({ length: to - from }, (_, k) => ring(cx, cy, from + k * 1.5)).flat();
const boxes = (x0, y0, x1, y1, n) => Array.from({ length: n }, (_, k) => box(x0 + k * 1.5, y0 + k * 1.5, x1 - k * 1.5, y1 - k * 1.5)).flat();

export const SETUP_FULL = {
  job: { name: 'Desk organiser — plate 1', time: '2h 12m 34s', weight: '26.4', layers: 175, tool_changes: 522, address: '192.168.1.40',
    preview: { bounds: [60, 60, 210, 210], tools: { 0: boxes(60, 60, 210, 210, 6), 1: rings(110, 110, 4, 22), 2: rings(165, 165, 4, 22), 3: boxes(150, 70, 200, 120, 12) } } },
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
  spools: { 0: { name: 'Generic Leaf Green', colour: '#6CBF5A' }, 2: { name: 'Elegoo Sky Blue', colour: '#5B9BEA' } }, remember: true,
};
