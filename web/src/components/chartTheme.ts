// Fixed colours per profile (categorical slots 1-3, validated for all pairs incl. colour-blind).
// Identity is also encoded by name / marker symbol, never by colour alone.
export const COLOR = {
  wellplan: "#2a78d6",
  ml: "#eb6834",
  actual: "#1baf7a",
  mlMinusWp: "#4a3aa7",
  limit: "#e34948",
  flag: "rgba(237, 161, 0, 0.20)",
  forecastZone: "rgba(74, 58, 167, 0.07)",
  guide: "#52514e",
  grid: "#e7e6e2",
  zero: "#0b0b0b",
  text: "#0b0b0b",
  textMuted: "#52514e",
  surface: "#fcfcfb",
};

// One fixed colour per OHFF value in every chart (ordinal blue ramp, light = low OHFF; validated).
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
