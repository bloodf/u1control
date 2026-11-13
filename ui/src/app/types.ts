export interface Head { loaded: boolean; type: string; vendor: string; sub_type: string; colour: string; official?: boolean }
export interface Heater { temp: number | null; target: number | null; active?: boolean }
export interface Tag { vendor?: string; manufacturer?: string; type?: string; sub_type?: string; uid?: string; official?: boolean;
  hotend_min?: number; hotend_max?: number; bed_temp?: number; sku?: string }
export interface Status {
  state: string; message?: string; filename?: string; progress?: number; layer?: number; total_layers?: number;
  print_duration?: number; total_duration?: number; extruders: Heater[]; bed: Heater; heads: Head[];
  rfid?: (Tag | null)[]; options?: Record<string, boolean>; purifier?: { fitted?: boolean; mode?: string };
  feed?: { state?: string; detected?: boolean }[]; busy?: boolean; machine_state?: string; bindings?: Record<string, number>;
  light?: boolean | null; speed_factor?: number; power_loss?: boolean; reprint?: unknown; exceptions?: unknown[];
}
export interface Info { address: string; firmware: { kind: string; version?: string }; printer: string; generation: number;
  limits?: { hotend: number; bed: number } }
export interface Spool { id: number; name: string; vendor: string; material: string; colour?: string; colours?: string[];
  remaining?: number | null; initial?: number | null; location?: string; filament_id?: number; low?: boolean; use_first?: boolean }
export interface StockView {
  spooler: { state: string; text: string; detail?: string; version?: string };
  stock: { state: string; code?: string; text: string; detail?: string; rows: Spool[]; key: string; ts?: number };
  same_spoolman: boolean | null; usage: string; bindings: Record<string, number>;
}
export interface UsageEntry { id: string; at: number | null; spool?: number | null; grams?: number; head?: number; file?: string;
  error?: string; printer?: string; printer_name?: string; acknowledged_at?: number }
export interface UsageView { pending: { file: string; printer: string }[]; unconfirmed: UsageEntry[]; acknowledged: UsageEntry[];
  acknowledged_total: number; save_error: string; restore_notice: string }
export interface Automation { key: string; label: string; help: string; automagic: unknown; choices: string[] | null }
export interface Config { settings: Record<string, any>; automations: Automation[]; mode: string; stored: Record<string, unknown>;
  spooler: { installed?: boolean; url?: string; dismissed?: boolean }; version: string }
