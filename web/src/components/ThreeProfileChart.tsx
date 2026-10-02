import { useEffect, useMemo, useRef, useState } from "react";
import type * as Plotly from "plotly.js";
import PlotlyChart from "./PlotlyChart";
import { Op, OP_LABEL, Profile } from "../api";
import { COLOR, DASH, DIFF_COLOR, DIFF_KEYS, DIFF_LABEL, DiffKey, SYMBOL } from "./chartTheme";

const CONFIG: Partial<Plotly.Config> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

export const HOOKLOAD_OPS: Op[] = ["pick_up", "slack_off", "rotating_weight"];
export const TORQUE_OPS: Op[] = ["torque_off_bottom", "torque_on_bottom"];

export type ChartOptions = {
  ops: Record<Op, boolean>;
  showFF: boolean;
  diffTarget: Op;
  diffMode: "abs" | "pct";
  flagSeries: DiffKey;
  threshold: number;
};

export type Interval = { from: number; to: number; peak: number };

/** Interval kedalaman dengan |selisih| > ambang. Batas = titik tengah ke tetangga. */
export function flaggedIntervals(depth: number[], vals: number[], threshold: number): Interval[] {
  if (!depth.length || !(threshold > 0)) return [];
  const idx = depth.map((_, i) => i).sort((a, b) => depth[a] - depth[b]);
  const d = idx.map((i) => depth[i]);
  const v = idx.map((i) => vals[i]);
  const steps = d.slice(1).map((x, i) => x - d[i]).sort((a, b) => a - b);
  const half = steps.length ? steps[Math.floor(steps.length / 2)] / 2 : 10;
  const out: Interval[] = [];
  let cur: Interval | null = null;
  for (let i = 0; i < d.length; i++) {
    const over = Math.abs(v[i]) > threshold;
    if (over) {
      const lo = i > 0 ? Math.max((d[i - 1] + d[i]) / 2, d[i] - half) : d[i] - half;
      const hi = i < d.length - 1 ? Math.min((d[i] + d[i + 1]) / 2, d[i] + half) : d[i] + half;
      if (cur && lo <= cur.to + 1e-9) {
        cur.to = hi;
        if (Math.abs(v[i]) > Math.abs(cur.peak)) cur.peak = v[i];
      } else {
        cur = { from: lo, to: hi, peak: v[i] };
        out.push(cur);
      }
    } else {
      cur = null;
    }
  }
  return out;
}

function useNarrow(limit = 960) {
  const [narrow, setNarrow] = useState(window.innerWidth < limit);
  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < limit);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [limit]);
  return narrow;
}

function interpAt(depth: number[], value: number[], at: number): number | null {
  if (depth.length < 2 || at < depth[0] || at > depth[depth.length - 1]) return null;
  let i = 1;
  while (i < depth.length && depth[i] < at) i++;
  const t = (at - depth[i - 1]) / (depth[i] - depth[i - 1] || 1);
  return value[i - 1] + t * (value[i] - value[i - 1]);
}

function nearest(depth: number[], value: number[], at: number, tol: number): number | null {
  let best: number | null = null;
  let bd = Infinity;
  depth.forEach((d, i) => {
    const dd = Math.abs(d - at);
    if (dd < bd && dd <= tol) {
      bd = dd;
      best = value[i];
    }
  });
  return best;
}

export default function ThreeProfileChart({
  profile,
  options,
  intervals,
}: {
  profile: Profile;
  options: ChartOptions;
  intervals: Interval[];
}) {
  const narrow = useNarrow();
  const [hoverDepth, setHoverDepth] = useState<number | null>(null);
  const raf = useRef<number | null>(null);
  const du = profile.depth_unit;
  const hkUnit = profile.operations.pick_up.unit;
  const tqUnit = profile.operations.torque_off_bottom.unit;
  const target = profile.operations[options.diffTarget];

  const { data, diffRange } = useMemo(() => {
    const traces: Plotly.Data[] = [];
    const axes = (k: 1 | 2 | 3) =>
      narrow
        ? { xaxis: k === 1 ? "x" : `x${k}`, yaxis: k === 1 ? "y" : `y${k}` }
        : { xaxis: k === 1 ? "x" : `x${k}`, yaxis: "y" };

    const addProfiles = (ops: Op[], k: 1 | 2) => {
      for (const op of ops) {
        if (!options.ops[op]) continue;
        const o = profile.operations[op];
        const label = OP_LABEL[op];
        for (const s of o.wellplan) {
          const isBase = s.ff === o.wellplan_baseline_ff || o.wellplan.length === 1;
          if (!isBase && !options.showFF) continue;
          traces.push({
            ...axes(k),
            type: "scatter",
            mode: "lines",
            x: s.value,
            y: s.depth,
            name: `WellPlan ${label}${s.ff !== null ? ` FF ${s.ff}` : ""}`,
            legendgroup: "wellplan",
            line: { color: COLOR.wellplan, width: isBase ? 2 : 1, dash: DASH[op] },
            opacity: isBase ? 1 : 0.45,
            hovertemplate: `WellPlan ${label}${s.ff !== null ? ` FF ${s.ff}` : ""}<br>%{y:,.0f} ${du}: %{x:,.1f} ${o.unit}<extra></extra>`,
          });
        }
        if (o.ml.depth.length) {
          traces.push({
            ...axes(k),
            type: "scatter",
            mode: "lines",
            x: o.ml.value,
            y: o.ml.depth,
            name: `ML ${label}`,
            legendgroup: "ml",
            line: { color: COLOR.ml, width: 2, dash: DASH[op] },
            hovertemplate: `ML ${label}<br>%{y:,.0f} ${du}: %{x:,.1f} ${o.unit}<extra></extra>`,
          });
        }
        if (o.actual.depth.length) {
          traces.push({
            ...axes(k),
            type: "scatter",
            mode: "markers",
            x: o.actual.value,
            y: o.actual.depth,
            name: `Aktual ${label}`,
            legendgroup: "actual",
            marker: { color: COLOR.actual, size: 8, symbol: SYMBOL[op] as "circle", line: { color: COLOR.surface, width: 1.5 } },
            hovertemplate: `Aktual ${label}<br>%{y:,.0f} ${du}: %{x:,.1f} ${o.unit}<extra></extra>`,
          });
        }
      }
    };
    addProfiles(HOOKLOAD_OPS, 1);
    addProfiles(TORQUE_OPS, 2);

    let maxAbs = 0;
    const unit = options.diffMode === "abs" ? target.unit : "%";
    for (const key of DIFF_KEYS) {
      const s = target.diff[key];
      if (!s.depth.length) continue;
      const vals = options.diffMode === "abs" ? s.abs : s.pct;
      vals.forEach((v) => (maxAbs = Math.max(maxAbs, Math.abs(v))));
      const isLine = key === "ml_minus_wp";
      traces.push({
        ...axes(3),
        type: "scatter",
        mode: isLine ? "lines" : "markers",
        x: vals,
        y: s.depth,
        name: DIFF_LABEL[key],
        legendgroup: key,
        customdata: s.abs.map((a, i) => [a, s.pct[i]]),
        ...(isLine
          ? { line: { color: DIFF_COLOR[key], width: 2 } }
          : {
              marker: {
                color: DIFF_COLOR[key],
                size: 8,
                symbol: key === "wp_minus_actual" ? "circle" : "diamond",
                line: { color: COLOR.surface, width: 1.5 },
              },
            }),
        hovertemplate:
          `${DIFF_LABEL[key]}<br>Kedalaman %{y:,.0f} ${du}<br>` +
          `Selisih %{customdata[0]:+,.2f} ${target.unit} (%{customdata[1]:+.1f}%)<extra></extra>`,
      });
    }
    const m = maxAbs > 0 ? maxAbs * 1.15 : 1;
    return { data: traces, diffRange: [-m, m], diffUnit: unit };
  }, [profile, options, narrow, target, du]);

  const layout = useMemo(() => {
    const ys = narrow ? ["y", "y2", "y3"] : ["y"];
    const shapes: Partial<Plotly.Shape>[] = [];
    for (const yref of ys) {
      for (const iv of intervals) {
        shapes.push({
          type: "rect",
          xref: "paper",
          yref: yref as Plotly.YAxisName,
          x0: 0,
          x1: 1,
          y0: iv.from,
          y1: iv.to,
          fillcolor: COLOR.flag,
          line: { width: 0 },
          layer: "below",
        });
      }
      if (hoverDepth !== null) {
        shapes.push({
          type: "line",
          xref: "paper",
          yref: yref as Plotly.YAxisName,
          x0: 0,
          x1: 1,
          y0: hoverDepth,
          y1: hoverDepth,
          line: { color: COLOR.guide, width: 1, dash: "dot" },
        });
      }
    }
    const axisBase = {
      gridcolor: COLOR.grid,
      zeroline: false,
      linecolor: COLOR.grid,
      tickfont: { color: COLOR.textMuted, size: 11 },
      title: { font: { color: COLOR.textMuted, size: 12 } },
      automargin: true,
    };
    const diffUnit = options.diffMode === "abs" ? target.unit : "%";
    const xTitles = [
      `Hookload (${hkUnit})`,
      `Torque (${tqUnit})`,
      `← lebih rendah (−)   ${diffUnit}   lebih tinggi (+) →`,
    ];
    const titles = [`Hookload`, `Torque`, `Selisih: ${OP_LABEL[options.diffTarget]}`];
    const doms = narrow
      ? [
          [0.7, 1],
          [0.36, 0.64],
          [0, 0.3],
        ]
      : [
          [0, 0.3],
          [0.35, 0.65],
          [0.7, 1],
        ];
    const l: Partial<Plotly.Layout> = {
      height: narrow ? 1500 : 720,
      margin: { l: 60, r: 16, t: 36, b: 50 },
      paper_bgcolor: COLOR.surface,
      plot_bgcolor: COLOR.surface,
      font: { family: "inherit", color: COLOR.text },
      hovermode: "y unified",
      hoverlabel: { bgcolor: "#ffffff", bordercolor: COLOR.grid, font: { color: COLOR.text } },
      showlegend: false, // legenda HTML di atas grafik (warna + gaya garis + simbol)
      shapes: shapes as Plotly.Shape[],
      annotations: titles.map((t, i) => ({
        text: `<b>${t}</b>`,
        showarrow: false,
        xref: "paper",
        yref: "paper",
        x: narrow ? 0 : (doms[i][0] + doms[i][1]) / 2,
        xanchor: narrow ? "left" : "center",
        y: narrow ? doms[i][1] + 0.005 : 1.0,
        yanchor: "bottom",
        font: { size: 13 },
      })) as Partial<Plotly.Annotations>[],
    };
    const anyL = l as Record<string, unknown>;
    [1, 2, 3].forEach((k) => {
      const xa = k === 1 ? "xaxis" : `xaxis${k}`;
      const ya = narrow ? (k === 1 ? "y" : `y${k}`) : "y";
      anyL[xa] = {
        ...axisBase,
        title: { ...axisBase.title, text: xTitles[k - 1] },
        anchor: ya,
        ...(narrow ? {} : { domain: doms[k - 1] }),
        ...(k === 3
          ? { zeroline: true, zerolinecolor: COLOR.zero, zerolinewidth: 2, range: diffRange }
          : {}),
      };
    });
    const yBase = { ...axisBase, autorange: "reversed", title: { ...axisBase.title, text: `Kedalaman (${du})` } };
    anyL.yaxis = { ...yBase, ...(narrow ? { domain: doms[0] } : {}) };
    if (narrow) {
      anyL.yaxis2 = { ...yBase, domain: doms[1], matches: "y" };
      anyL.yaxis3 = { ...yBase, domain: doms[2], matches: "y" };
      anyL.xaxis = { ...(anyL.xaxis as object), domain: [0, 1] };
      anyL.xaxis2 = { ...(anyL.xaxis2 as object), domain: [0, 1] };
      anyL.xaxis3 = { ...(anyL.xaxis3 as object), domain: [0, 1] };
    }
    return l;
  }, [narrow, intervals, hoverDepth, options, target, hkUnit, tqUnit, du, diffRange]);

  const onHover = (e: Plotly.PlotHoverEvent) => {
    const y = e.points?.[0]?.y;
    if (typeof y !== "number") return;
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => setHoverDepth(y));
  };

  // Pembacaan tersinkron: nilai semua profil di kedalaman penuntun
  const readout = useMemo(() => {
    if (hoverDepth === null) return null;
    const tol = du === "ft" ? 60 : 20;
    const rows: { label: string; wp: number | null; ml: number | null; act: number | null; unit: string }[] = [];
    for (const op of [...HOOKLOAD_OPS, ...TORQUE_OPS]) {
      if (!options.ops[op]) continue;
      const o = profile.operations[op];
      const base = o.wellplan.find((s) => s.ff === o.wellplan_baseline_ff) ?? o.wellplan[0];
      rows.push({
        label: OP_LABEL[op],
        wp: base ? interpAt(base.depth, base.value, hoverDepth) : null,
        ml: interpAt(o.ml.depth, o.ml.value, hoverDepth),
        act: nearest(o.actual.depth, o.actual.value, hoverDepth, tol),
        unit: o.unit,
      });
    }
    const t = target.diff;
    const diffs = DIFF_KEYS.map((k) => ({
      key: k,
      v:
        k === "ml_minus_wp"
          ? interpAt(t[k].depth, t[k].abs, hoverDepth)
          : nearest(t[k].depth, t[k].abs, hoverDepth, tol),
    }));
    return { rows, diffs };
  }, [hoverDepth, profile, options.ops, target, du]);

  const f = (v: number | null) => (v === null ? "–" : v.toLocaleString("id-ID", { maximumFractionDigits: 1 }));

  return (
    <div className="chart-wrap" onMouseLeave={() => setHoverDepth(null)}>
      <PlotlyChart data={data} layout={layout} config={CONFIG} onHover={onHover} />
      <div className="readout" aria-live="polite">
        {readout ? (
          <>
            <b>
              Kedalaman {hoverDepth!.toLocaleString("id-ID", { maximumFractionDigits: 0 })} {du}
            </b>
            {readout.rows.map((r) => (
              <span key={r.label}>
                {r.label}: <i className="k wp">WP</i> {f(r.wp)} · <i className="k ml">ML</i> {f(r.ml)} ·{" "}
                <i className="k act">Akt</i> {f(r.act)} {r.unit}
              </span>
            ))}
            <span>
              Selisih {OP_LABEL[options.diffTarget]}:{" "}
              {readout.diffs.map((d) => (
                <span key={d.key} className="nowrap">
                  {DIFF_LABEL[d.key]} {d.v === null ? "–" : `${d.v > 0 ? "+" : ""}${f(d.v)}`};{" "}
                </span>
              ))}
              {target.unit}
            </span>
          </>
        ) : (
          <span className="muted">
            Arahkan kursor ke grafik: garis penuntun memotong ketiga grafik di kedalaman yang sama. Zoom/geser pada satu
            grafik ikut menggeser kedalaman grafik lain.
          </span>
        )}
      </div>
    </div>
  );
}
