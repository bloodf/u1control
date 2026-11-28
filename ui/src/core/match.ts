// The name a toolhead card shows for an OrcaSlicer preset: without the plugin bundle folder ("_local/spooler/"), the
// "Spooler/" the plugin marks its presets with, and the "@Printer" suffix. The real name is what is picked and applied.
export function presetLabel(name: string): string {
  return name.replace(/^_local\/[^/]+\//, '').replace(/^Spooler\//, '').replace(/\s*@[^@]*$/, '').trim() || name;
}
