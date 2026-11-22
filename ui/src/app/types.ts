/** A toolhead (u1.describe_toolheads). loaded: a named filament; unnamed: filament nobody has named (its record says NONE). */
export interface Head { loaded: boolean; unnamed?: boolean; type: string; vendor: string; sub_type: string; colour: string; colours?: string[]; official?: boolean;
  /** standard | high_flow; '' when the firmware doesn't say (before 1.6.0). */ nozzle?: string }
export interface Heater { temp: number | null; target: number | null; active?: boolean; picked?: boolean; /** pressure advance now */ pa?: number | null }
export interface Tag { vendor?: string; manufacturer?: string; type?: string; sub_type?: string; uid?: string; official?: boolean;
  hotend_min?: number; hotend_max?: number; bed_temp?: number; sku?: string }
/** A stepper driver (u1.driver_states): temp and state are null while its motor is off. */
export interface Driver { name: string; temp: number | null; state: 'ok' | 'otpw' | 'ot' | null }
export interface Status {
  state: string; message?: string; filename?: string; progress?: number; layer?: number; total_layers?: number;
  print_duration?: number; total_duration?: number; left?: number | null; extruders: Heater[]; bed: Heater; heads: Head[];
  rfid?: (Tag | null)[]; options?: Record<string, boolean>; features?: string[]; purifier?: { fitted?: boolean; mode?: string | number; recirculating?: boolean; exhaust?: number | null; inner?: number | null };
  fan?: number | null; aux_fan?: number | null; chamber?: number | null; drivers?: Driver[];
  feed?: { state?: string; detected?: boolean }[]; busy?: boolean; machine_state?: string; bindings?: Record<string, number>;
  light?: boolean | null; speed_factor?: number; power_loss?: boolean; reprint?: unknown; exceptions?: unknown[];
  firmware?: { kind: string; version?: string }; ace?: Ace | null;
}
/** multiACE (u1.ace_view): null without it. heads: which unit and slot feeds each toolhead. */
export interface Ace { mode: string; swapping: boolean; heads: Record<string, [number, number] | null>;
  units: { index: number; name: string; connected: boolean; temp: number | null; humidity: number | null; dryer: boolean;
    drying: { temp: number | null; left: number | null } | null; slots: { material: string; status: string; brand: string; colour: string | null }[] }[] }
export interface Info { address: string; firmware: { kind: string; version?: string }; printer: string; generation: number;
  limits?: { hotend: number; bed: number } }
export interface Spool { id: number; name: string; vendor: string; material: string; colour?: string; colours?: string[];
  remaining?: number | null; initial?: number | null; location?: string; filament_id?: number; low?: boolean; use_first?: boolean;
  /** pressure_advance_matrix: {"0.4_standard": 0.032} */ pa?: Record<string, number> }
export interface StockView {
  spooler: { state: string; text: string; detail?: string; version?: string; links?: number };
  /** code 'own': U1 Control's own Spoolman list, as Spooler shares none (origin 'printer' when read through the U1). */
  stock: { state: string; code?: string; text: string; detail?: string; rows: Spool[]; key: string; ts?: number; origin?: string; source?: string };
  same_spoolman: boolean | null; usage: string; bindings: Record<string, number>;
}
export interface UsageEntry { id: string; at: number | null; spool?: number | null; grams?: number; head?: number; file?: string;
  error?: string; printer?: string; printer_name?: string; acknowledged_at?: number }
export interface UsageView { pending: { file: string; printer: string }[]; unconfirmed: UsageEntry[]; acknowledged: UsageEntry[];
  acknowledged_total: number; save_error: string; restore_notice: string }
export interface Automation { key: string; label: string; help: string; automagic: unknown; choices: string[] | null }
export interface Config { settings: Record<string, any>; automations: Automation[]; mode: string; stored: Record<string, unknown>;
  spooler: { installed?: boolean; url?: string; dismissed?: boolean }; version: string;
  /** Whether the selected U1 process preset runs "U1 print setup"; null when no U1 is selected. */
  pipeline?: { preset: string; on: boolean } | null }
/** What the plugin needs and can't install (requirements.py): ok, missing, or unknown (not known yet / can't be read). */
export interface Requirement { id: 'printer_agents' | 'extended_firmware' | 'spoolman' | 'spooler'; status: 'ok' | 'missing' | 'unknown';
  details: { version?: string; url?: string; via?: string } }
/** A toolhead's OrcaSlicer preset as Apply to project filaments picks it (preset_matches): reasons are filmatch [code, value]. */
export interface PresetMatch { head: number; name: string; source: 'linked' | 'remembered' | 'spooler' | 'auto' | 'none'; score: number | null;
  reasons: unknown; confident: boolean; candidates: { name: string; score: number; reasons: unknown }[]; remembered_key: string }
