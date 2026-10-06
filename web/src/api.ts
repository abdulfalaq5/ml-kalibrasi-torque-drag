export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(url, init);
  if (res.status === 401 && !url.endsWith("/api/auth/login")) {
    window.dispatchEvent(new Event("tdml:unauthorized"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(url: string) => request<T>("GET", url),
  post: <T,>(url: string, body?: unknown) => request<T>("POST", url, body),
  patch: <T,>(url: string, body?: unknown) => request<T>("PATCH", url, body),
  del: <T,>(url: string) => request<T>("DELETE", url),
};

export type Issue = { level: "error" | "warning"; message: string; location: string | null };
export type Purpose = "training" | "monitoring";
export const PURPOSE_LABEL: Record<Purpose, string> = { training: "Training Data", monitoring: "Monitoring" };
export const SECTIONS = [26, 22, 17.5, 12.25, 8.5, 6.125];
export const TYPES = ["J", "S", "Horizontal"];

export const FILE_STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  warning: "Warning",
  failed: "Failed",
  replaced: "Replaced",
  deleted: "Deleted",
  processing: "Processing",
};
export const WELL_STATUS_LABEL: Record<string, string> = { ready: "Ready", no_actual: "No actual data", new: "New" };
export const MODEL_STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  held: "Held",
  failed: "Failed",
};
export const SCAN_STATUS_LABEL: Record<string, string> = {
  accepted: "Accepted",
  "accepted with warnings": "Accepted with warnings",
  duplicate: "Duplicate",
  skipped: "Skipped",
  rejected: "Rejected",
  running: "Running",
  done: "Done",
  failed: "Failed",
};
export const statusTone = (s: string) =>
  ["ok", "ready", "done", "accepted"].includes(s)
    ? "ok"
    : ["failed", "rejected"].includes(s)
      ? "bad"
      : ["warning", "no_actual", "held", "accepted with warnings", "duplicate", "skipped"].includes(s)
        ? "warn"
        : "";

export type FileItem = {
  id: number;
  purpose: Purpose;
  filename: string;
  kind: string | null;
  status: string;
  well_id: number | null;
  well_name: string | null;
  section_in: number | null;
  well_type: string | null;
  created_at: string;
  issues: Issue[];
  summary: { kinds?: string[]; plan_points?: number; actual_points?: number; survey_points?: number };
};
export type WellItem = {
  id: number;
  name: string;
  purpose: Purpose;
  quality: QStatus;
  quality_score: number | null;
  plan_format: string | null;
  section_in: number | null;
  well_type: string | null;
  section_source: string;
  type_source: string;
  status: string;
  survey_points: number;
  plan_points: number;
  actual_points: number;
  ff_scenarios: number[];
  prediction: "oof" | "full" | null;
  files: { id: number; filename: string; status: string; version: number }[];
};
export type QStatus = "A" | "B" | "C" | "X";
export const Q_LABEL: Record<QStatus, string> = {
  A: "Accepted",
  B: "Accepted with warnings",
  C: "On hold",
  X: "Excluded",
};
export type Check = { code: string; level: "critical" | "warning" | "pass"; message: string };
export type QualityRow = {
  well_id: number;
  well: string;
  purpose: Purpose;
  section_in: number | null;
  well_type: string | null;
  auto_status: QStatus | null;
  status: QStatus;
  status_label: string;
  score: number | null;
  checks: Check[];
  stats: Record<string, number>;
  reviews: { decision: string; reason: string; reviewer: string; created_at: string }[];
};
export type ScanRun = {
  id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  counts: Record<string, number> | null;
  quality: Record<string, number> | null;
  error?: string | null;
  files?: { file: string; well: string | null; section: number | null; status: string; message: string; version?: number }[];
  wells?: { well: string; section: number; type: string; quality: QStatus; reasons: string[] }[];
};
export type InboxStatus = {
  inbox_dir: string;
  exists: boolean;
  pending: number;
  too_new: number;
  wells: number;
  move_after_import: boolean;
};
export type DatasetItem = {
  id: number;
  version: number;
  created_at: string;
  hash: string;
  n_rows: number;
  n_wells: number;
  n_excluded: number;
  n_blind: number;
  wells?: { well_id: number; name: string; section: string; type: string; blind: boolean; rows: number }[];
  excluded?: { name: string; section: number; status: string }[];
};
export type BlindSet = { id: number; wells: string[]; note: string; created_at: string } | null;
export type LimitItem = {
  id: number;
  well_id: number | null;
  section_in: number | null;
  operation: string;
  kind: "max" | "min";
  value: number;
  unit: string;
  note: string | null;
  scope: string;
};
export type EvaluationItem = {
  id: number;
  well_id: number;
  well: string;
  section_in: number;
  model_id: number;
  predicted_at: string;
  evaluated_at: string;
  metrics: { operations: Record<string, { ml: Metric; wellplan: Metric | null; ml_better_frac: number | null }> };
};
export type Metric = { rmse: number | null; mape: number | null; r2: number | null; n: number; within?: number | null };
export type Within = { wellplan: number | null; ml: number | null };
export type Backtest = { tolerance_si: number; horizons: Record<string, Record<string, { within: number; p90_si: number; n: number }>> };
export type GroupRow = {
  section?: string;
  well_type?: string;
  n_wells: number;
  wellplan: Metric;
  ml: Metric;
  warning: boolean;
};
export type OpMetrics = {
  chosen: string;
  chosen_label?: string;
  strategy?: { combo: string; n_wells: number; rmse_single: number; rmse_combo?: number; used: string }[];
  by_depth?: { depth_from_m: number; depth_to_m: number; wellplan: Metric; ml: Metric; ml_better_frac: number }[];
  worst_points?: { well_name: string; section: string; depth_m: number; actual: number; wellplan: number; ml: number }[];
  learning_curve?: { label: string; n_wells: number; rmse_ml: number; rmse_wp: number }[];
  explain?: { method: string; features: { feature: string; importance: number; direction: number }[]; note: string; physics_ok: boolean };
  algo_best?: Record<string, Metric & { candidate: string }>;
  candidates: Record<string, Metric>;
  overall: { wellplan: Metric; ml: Metric; n_wells: number; ml_better_frac?: number; within?: Within; band_coverage?: number };
  forecast_backtest?: Backtest;
  by_section: GroupRow[];
  by_type: GroupRow[];
  by_section_type: GroupRow[];
  per_well: { well_name: string; section: string; well_type: string; wellplan: Metric; ml: Metric }[];
};
export type ModelItem = {
  id: number;
  algorithm: string;
  status: string;
  active: boolean;
  dataset_version?: number;
  skill?: number | null;
  comparison?: { decision?: string; new_skill?: number; active_skill?: number; active_id?: number };
  blind_done?: boolean;
  blind_result?: {
    wells: string[];
    run_at: string;
    operations: Record<string, { wellplan: Metric; ml: Metric; ml_better_frac: number; within?: Within; band_coverage?: number }>;
  } | null;
  message: string | null;
  created_at: string;
  finished_at: string | null;
  summary?: Record<string, { chosen: string; wellplan_rmse: number; ml_rmse: number; n_wells: number }>;
  metrics?: {
    operations: Record<string, OpMetrics>;
    notes: string[];
    skill?: number;
    feature_selection?: { group: string; score: number; used: boolean; note: string }[];
    dataset?: { version: number; hash: string; rows_train: number; wells_train: number; rows_blind: number; wells_blind: number };
  };
};
export type Series = { depth: number[]; value: number[] };
export type DiffSeries = { depth: number[]; abs: number[]; pct: number[] };
export type OpProfile = {
  label: string;
  unit: string;
  wellplan: { ff: number | null; name: string; depth: number[]; value: number[] }[];
  wellplan_baseline_ff: number | null;
  calibration_offset: number | null;
  ml: Series & { lo: number[]; hi: number[] };
  actual: Series;
  limits: {
    id: number;
    kind: "max" | "min";
    scope: string;
    value: number;
    note: string | null;
    cross_ml: number | null;
    cross_ml_band: number | null;
    cross_wellplan: number | null;
    margin_ml: number | null;
  }[];
  diff: { wp_minus_actual: DiffSeries; ml_minus_actual: DiffSeries; ml_minus_wp: DiffSeries };
  metrics: { wellplan: Metric | null; ml: Metric | null } | null;
  tolerance: string;
};
export type Profile = {
  well: { id: number; name: string; section_in: number | null; well_type: string | null; purpose: Purpose };
  calibration: { available: boolean; mode: "calibrated" | "raw" };
  unit_system: "imperial" | "si";
  depth_unit: string;
  has_actual: boolean;
  prediction: { id: number; kind: "oof" | "full"; model_id: number } | null;
  model: { id: number; active: boolean; dataset_version: number | null } | null;
  quality: { status: QStatus; auto_status: QStatus | null; score: number | null; issues: Check[]; review: { decision: string; reason: string } | null };
  warnings: string[];
  sign_convention: string;
  operations: Record<string, OpProfile>;
};

export const OPS = [
  "pick_up",
  "slack_off",
  "rotating_weight",
  "torque_off_bottom",
  "torque_on_bottom",
] as const;
export type Op = (typeof OPS)[number];
export const OP_LABEL: Record<Op, string> = {
  pick_up: "Pick up",
  slack_off: "Slack off",
  rotating_weight: "Rotating weight",
  torque_off_bottom: "Torque off bottom",
  torque_on_bottom: "Torque on bottom",
};

export const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });

export const fmtDate = (s: string) =>
  new Date(s).toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/* Standard series names (same as the client's Excel): "PU - OHFF : 0.3", "SO - OHFF : 0.5", "ROT". */
export const SERIES_PREFIX: Record<Op, string> = {
  pick_up: "PU",
  slack_off: "SO",
  rotating_weight: "ROT",
  torque_off_bottom: "Torque Off Bottom",
  torque_on_bottom: "Torque On Bottom",
};

export type ForecastOp = {
  label: string;
  unit: string;
  depth: number[];
  ml: (number | null)[];
  p10: (number | null)[];
  p90: (number | null)[];
  ml_corrected: (number | null)[] | null;
  bias: number | null;
  wellplan: { ff: number | null; name: string; value: (number | null)[] }[];
  change: number;
  tolerance: string;
  backtest: { horizon_ft: number; method: string; within: number; p90: number; td_within: number | null } | null;
  actual_check: {
    n: number;
    td_within: number | null;
    ml_within: number;
    ml_mean_abs: number;
    ml_bias_within?: number;
    ml_bias_mean_abs?: number;
    unit: string;
  } | null;
  explanation: {
    method: string;
    drivers: { feature: string; label: string; delta: number }[];
    plan_changes: { inclination_deg?: [number, number]; max_dls_deg_100ft?: number; intervals?: { type: string; from: number }[] };
    limit_crossings: { kind: string; value: number; scope: string; cross_ml: number | null; cross_band: number | null }[];
    sentence: string;
  };
};
export type Forecast = {
  well: { id: number; name: string; section_in: number | null; well_type: string | null; purpose: Purpose };
  model_id: number;
  depth_unit: string;
  start_depth: number;
  end_depth: number;
  last_actual_depth: number | null;
  distance_ft: number;
  bias_correction: boolean;
  calibration: "calibrated" | "raw";
  warnings: string[];
  summary: string;
  /** request parameters, reused to draw the same prediction in the Excel export */
  request?: { distance_ft: number; step_ft: number; start_depth_ft: number | null; bias_correction: boolean | null };
  operations: Partial<Record<Op, ForecastOp>>;
};
