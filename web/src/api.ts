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
      /* bukan JSON */
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
export type FileItem = {
  id: number;
  filename: string;
  kind: string | null;
  status: string;
  well_id: number | null;
  well_name: string | null;
  created_at: string;
  issues: Issue[];
  summary: { kinds?: string[]; plan_points?: number; actual_points?: number; survey_points?: number };
};
export type WellItem = {
  id: number;
  name: string;
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
  files: { id: number; filename: string; status: string }[];
};
export type Metric = { rmse: number | null; mape: number | null; r2: number | null; n: number };
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
  candidates: Record<string, Metric>;
  overall: { wellplan: Metric; ml: Metric; n_wells: number };
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
  message: string | null;
  created_at: string;
  finished_at: string | null;
  summary?: Record<string, { chosen: string; wellplan_rmse: number; ml_rmse: number; n_wells: number }>;
  metrics?: { operations: Record<string, OpMetrics>; notes: string[]; dataset?: { rows: number; wells: number } };
};
export type Series = { depth: number[]; value: number[] };
export type DiffSeries = { depth: number[]; abs: number[]; pct: number[] };
export type OpProfile = {
  label: string;
  unit: string;
  wellplan: { ff: number | null; depth: number[]; value: number[] }[];
  wellplan_baseline_ff: number | null;
  ml: Series;
  actual: Series;
  diff: { wp_minus_actual: DiffSeries; ml_minus_actual: DiffSeries; ml_minus_wp: DiffSeries };
  metrics: { wellplan: Metric | null; ml: Metric | null } | null;
};
export type Profile = {
  well: { id: number; name: string; section_in: number | null; well_type: string | null };
  unit_system: "imperial" | "si";
  depth_unit: string;
  has_actual: boolean;
  prediction: { id: number; kind: "oof" | "full"; model_id: number } | null;
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
  v === null || v === undefined || Number.isNaN(v) ? "–" : v.toLocaleString("id-ID", { maximumFractionDigits: d, minimumFractionDigits: d });
