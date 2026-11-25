// The print setup's top view as preview.top_view (src/u1control/preview.py) sends it: a cell map of the print seen
// from the top, run-length encoded. TopView.vue draws it.

export interface TopViewData { w: number; h: number; bounds: [number, number, number, number]; runs: string }
export interface Cells { tool: Uint8Array; height: Uint8Array; tools: Uint8Array }
export const NONE = 255;   // the tool of a cell with nothing printed

/** The run-length map as one array per property (the cell's top tool, its height 1-255, a bit per tool anywhere in
 * its column), row by row from the front of the bed. A short or broken map leaves the rest empty. */
export function decode(view: TopViewData): Cells {
  const n = Math.max(0, view.w * view.h);
  const tool = new Uint8Array(n).fill(NONE), height = new Uint8Array(n), tools = new Uint8Array(n);
  let raw = '';
  try { raw = atob(view.runs); } catch { return { tool, height, tools }; }
  let i = 0;
  for (let k = 0; k + 3 < raw.length && i < n; k += 4) {
    const end = Math.min(n, i + raw.charCodeAt(k));
    tool.fill(raw.charCodeAt(k + 1), i, end);
    height.fill(raw.charCodeAt(k + 2), i, end);
    tools.fill(raw.charCodeAt(k + 3), i, end);
    i = end;
  }
  return { tool, height, tools };
}
