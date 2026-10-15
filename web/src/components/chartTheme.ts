// Fixed colours per profile (categorical slots 1-3, validated for all pairs incl. colour-blind).
// Identity is also encoded by name / marker symbol, never by colour alone.
export const COLOR = {
  wellplan: "#2a78d6",
  ml: "#eb6834",
  actual: "#0e9f6e", // darker green: >= 3:1 on the surface
  markerEdge: "#0b2e22", // dark outline so point symbols stand out on lines
  mlMinusWp: "#4a3aa7",
  limit: "#e34948",
  flag: "rgba(237, 161, 0, 0.20)",
  forecastZone: "rgba(74, 58, 167, 0.08)",
  forecast: "#4a3aa7",
  forecastBand: "rgba(74, 58, 167, 0.18)",
  guide: "#52514e",
  grid: "#e7e6e2",
  zero: "#0b0b0b",
  text: "#0b0b0b",
  textMuted: "#52514e",
  surface: "#fcfcfb",
};

// One fixed colour per OHFF value (ordinal blue ramp, light = low OHFF); Excel/PDF and help. Dashboard: OP_COLOR.
export const OHFF_COLOR: Record<string, string> = {
  "0.1": "#86b6ef",
  "0.2": "#5598e7",
  "0.3": "#2a78d6",
  "0.4": "#1c5cab",
  "0.5": "#104281",
};
export function ohffColor(ff: number | null): string {
  if (ff === null) return OHFF_COLOR["0.3"];
  const keys = Object.keys(OHFF_COLOR).map(Number);
  const k = keys.reduce((a, b) => (Math.abs(b - ff) < Math.abs(a - ff) ? b : a));
  return OHFF_COLOR[k.toFixed(1)];
}

// Dashboard (K-52): one colour family per operation, so PU / SO / ROT / torque lines are told apart.
// WellPlan = ramp light -> dark for OHFF 0.1 -> 0.5 (thin), ML = "main" (thick), actual = "main" points.
export const OP_COLOR: Record<string, { label: string; main: string; ramp: string[] }> = {
  pick_up: { label: "Pick up (PU)", main: "#1f5fbf", ramp: ["#a9cdf5", "#78aeee", "#4a8fe2", "#2a6fc4", "#174f96"] },
  slack_off: { label: "Slack off (SO)", main: "#0e7a4f", ramp: ["#a6dfc4", "#6fc9a0", "#3aae7c", "#1d8a5c", "#0f6641"] },
  rotating_weight: { label: "Rotating weight (ROT)", main: "#b86e00", ramp: ["#f5d39b", "#efb85c", "#e09a1f", "#c27f06", "#935f00"] },
  torque_off_bottom: {
    label: "Torque off bottom",
    main: "#1f5fbf",
    ramp: ["#a9cdf5", "#78aeee", "#4a8fe2", "#2a6fc4", "#174f96"],
  },
  torque_on_bottom: {
    label: "Torque on bottom",
    main: "#a83f1c",
    ramp: ["#f2b8a2", "#e88d6c", "#d8653f", "#b44a26", "#863415"],
  },
};
/** WellPlan line colour of an operation at an OHFF (single curve -> middle shade). */
export function opWpColor(op: string, ff: number | null): string {
  const ramp = OP_COLOR[op]?.ramp ?? Object.values(OHFF_COLOR);
  if (ff === null) return ramp[2];
  const i = Math.min(4, Math.max(0, Math.round(ff * 10) - 1));
  return ramp[i];
}

export const DASH: Record<string, "solid" | "dash" | "dot"> = {
  pick_up: "solid",
  slack_off: "dash",
  rotating_weight: "dot",
  torque_off_bottom: "solid",
  torque_on_bottom: "dash",
};

export const SYMBOL: Record<string, string> = {
  pick_up: "circle",
  slack_off: "triangle-up",
  rotating_weight: "square",
  torque_off_bottom: "circle",
  torque_on_bottom: "triangle-up",
};

export const DIFF_KEYS = ["wp_minus_actual", "ml_minus_actual", "ml_minus_wp"] as const;
export type DiffKey = (typeof DIFF_KEYS)[number];
export const DIFF_LABEL: Record<DiffKey, string> = {
  wp_minus_actual: "T&D Model − Actual",
  ml_minus_actual: "ML − Actual",
  ml_minus_wp: "ML − T&D Model",
};
export const DIFF_COLOR: Record<DiffKey, string> = {
  wp_minus_actual: COLOR.wellplan,
  ml_minus_actual: COLOR.ml,
  ml_minus_wp: COLOR.mlMinusWp,
};
