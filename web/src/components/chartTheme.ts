// Warna tetap per profil (slot kategorikal 1-3 yang tervalidasi untuk semua pasangan,
// termasuk buta warna). Identitas juga dikodekan lewat gaya garis/simbol, bukan warna saja.
export const COLOR = {
  wellplan: "#2a78d6",
  ml: "#eb6834",
  actual: "#1baf7a",
  mlMinusWp: "#4a3aa7",
  limit: "#e34948",
  flag: "rgba(237, 161, 0, 0.20)",
  guide: "#52514e",
  grid: "#e7e6e2",
  zero: "#0b0b0b",
  text: "#0b0b0b",
  textMuted: "#52514e",
  surface: "#fcfcfb",
};

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
  wp_minus_actual: "WellPlan − Aktual",
  ml_minus_actual: "ML − Aktual",
  ml_minus_wp: "ML − WellPlan",
};
export const DIFF_COLOR: Record<DiffKey, string> = {
  wp_minus_actual: COLOR.wellplan,
  ml_minus_actual: COLOR.ml,
  ml_minus_wp: COLOR.mlMinusWp,
};
