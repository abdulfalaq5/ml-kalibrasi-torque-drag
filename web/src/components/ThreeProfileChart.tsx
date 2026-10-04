import { useEffect, useMemo, useRef, useState } from "react";
import type * as Plotly from "plotly.js";
import PlotlyChart from "./PlotlyChart";
import { Forecast, Op, OP_LABEL, Profile, SERIES_PREFIX } from "../api";
import { COLOR, DIFF_COLOR, DIFF_KEYS, DIFF_LABEL, DiffKey, ohffColor, SYMBOL } from "./chartTheme";

export const HOOKLOAD_OPS: Op[] = ["pick_up", "slack_off", "rotating_weight"];
export const TORQUE_OPS: Op[] = ["torque_off_bottom", "torque_on_bottom"];

export type ChartOptions = {
  ops: Record<Op, boolean>;
  showFF: boolean;
  diffTarget: Op;
  diffMode: "abs" | "pct";
  flagSeries: DiffKey;
  threshold: number;
  showBand: boolean;
};

export type Interval = { from: number; to: number; peak: number };

const CONFIG: Partial<Plotly.Config> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
  toImageButtonOptions: { format: "png", scale: 2 },
};

/** Depth intervals with |difference| > threshold. Bounds = midpoint to the neighbour. */
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

function useNarrow(limit = 760) {
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

/** Y-axis range from a Plotly relayout event. null = autorange, undefined = not a Y change. */
function yRangeFromRelayout(e: Plotly.PlotRelayoutEvent): [number, number] | null | undefined {
  const r = e as Record<string, unknown>;
  if (r["yaxis.autorange"]) return null;
  if (typeof r["yaxis.range[0]"] === "number" && typeof r["yaxis.range[1]"] === "number") {
    return [r["yaxis.range[0]"] as number, r["yaxis.range[1]"] as number];
  }
  if (Array.isArray(r["yaxis.range"])) return r["yaxis.range"] as [number, number];
  return undefined;
}

type PanelKey = "hookload" | "torque" | "diff";

export default function ThreeProfileChart({
  profile,
  options,
  intervals,
  forecast,
}: {
  profile: Profile;
  options: ChartOptions;
  intervals: Interval[];
  forecast?: Forecast | null;
}) {
  const narrow = useNarrow();
  const [hoverDepth, setHoverDepth] = useState<number | null>(null);
  // Shared depth range (null = automatic) + revision to reset the X zoom
  const [yRange, setYRange] = useState<[number, number] | null>(null);
  const [syncDepth, setSyncDepth] = useState(true);
  const [panelY, setPanelY] = useState<Record<PanelKey, [number, number] | null>>({
    hookload: null,
    torque: null,
    diff: null,
  });
  const [zoomRev, setZoomRev] = useState(0);
  const raf = useRef<number | null>(null);
  const du = profile.depth_unit;
  const hkUnit = profile.operations.pick_up.unit;
  const tqUnit = profile.operations.torque_off_bottom.unit;
  const target = profile.operations[options.diffTarget];

  // Reset zoom when the well / unit system changes
  useEffect(() => {
    setYRange(null);
    setPanelY({ hookload: null, torque: null, diff: null });
    setZoomRev((r) => r + 1);
  }, [profile.well.id, profile.unit_system]);

  const traces = useMemo(() => {
    const profileTraces = (ops: Op[]): Plotly.Data[] => {
      const out: Plotly.Data[] = [];
      for (const op of ops) {
        if (!options.ops[op]) continue;
        const o = profile.operations[op];
        const p = SERIES_PREFIX[op];
        for (const s of o.wellplan) {
          const isBase = s.ff === o.wellplan_baseline_ff || o.wellplan.length === 1;
          if (!isBase && !options.showFF) continue;
          // standard names from the API: "PU - OHFF : 0.3", "SO - OHFF : 0.5", "ROT"
          out.push({
            type: "scatter",
            mode: "lines",
            x: s.value,
            y: s.depth,
            name: s.name,
            line: { color: ohffColor(s.ff), width: 1.75 },
            hovertemplate: `%{x:,.1f} ${o.unit}<extra>${s.name}</extra>`,
          });
        }
        if (o.ml.depth.length && options.showBand && o.ml.lo?.length) {
          // uncertainty band P10–P90: two dashed bound lines
          for (const [k, xs] of [
            ["P10", o.ml.lo],
            ["P90", o.ml.hi],
          ] as const) {
            out.push({
              type: "scatter",
              mode: "lines",
              x: xs,
              y: o.ml.depth,
              name: `${p} - ML P10–P90`,
              legendgroup: `band-${op}`,
              showlegend: k === "P10",
              line: { color: COLOR.ml, width: 1, dash: "dash" },
              hovertemplate: `%{x:,.1f} ${o.unit}<extra>${p} - ML ${k}</extra>`,
            });
          }
        }
        if (o.ml.depth.length) {
          out.push({
            type: "scatter",
            mode: "lines",
            x: o.ml.value,
            y: o.ml.depth,
            name: `${p} - ML`,
            line: { color: COLOR.ml, width: 2.5 },
            hovertemplate: `%{x:,.1f} ${o.unit}<extra>${p} - ML</extra>`,
          });
        }
        const fo = forecast?.operations[op];
        if (fo?.ml_corrected) {
          out.push({
            type: "scatter",
            mode: "lines",
            x: fo.ml_corrected,
            y: fo.depth,
            name: `${p} - ML forecast (bias-corrected)`,
            line: { color: COLOR.mlMinusWp, width: 2.5 },
            hovertemplate: `%{x:,.1f} ${o.unit}<extra>${p} - ML forecast (bias-corrected)</extra>`,
          });
        }
        if (o.actual.depth.length) {
          out.push({
            type: "scatter",
            mode: "markers",
            x: o.actual.value,
            y: o.actual.depth,
            name: `${p} Actual`,
            marker: {
              color: COLOR.actual,
              size: 8,
              symbol: SYMBOL[op] as "circle",
              line: { color: COLOR.surface, width: 1.5 },
            },
            hovertemplate: `%{x:,.1f} ${o.unit}<extra>${p} Actual</extra>`,
          });
        }
      }
      return out;
    };

    const diff: Plotly.Data[] = [];
    let maxAbs = 0;
    for (const key of DIFF_KEYS) {
      const s = target.diff[key];
      if (!s.depth.length) continue;
      const vals = options.diffMode === "abs" ? s.abs : s.pct;
      vals.forEach((v) => (maxAbs = Math.max(maxAbs, Math.abs(v))));
      const isLine = key === "ml_minus_wp";
      diff.push({
        type: "scatter",
        mode: isLine ? "lines" : "markers",
        x: vals,
        y: s.depth,
        name: DIFF_LABEL[key],
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
          `%{customdata[0]:+,.2f} ${target.unit} (%{customdata[1]:+.1f}%)` + `<extra>${DIFF_LABEL[key]}</extra>`,
      });
    }
    const m = maxAbs > 0 ? maxAbs * 1.15 : 1;
    return {
      hookload: profileTraces(HOOKLOAD_OPS),
      torque: profileTraces(TORQUE_OPS),
      diff,
      diffRange: [-m, m] as [number, number],
    };
  }, [profile, options, target, forecast]);

  // Same full depth range for all panels (reversed: deeper is lower)
  const fullRange = useMemo((): [number, number] | null => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const d of [traces.hookload, traces.torque, traces.diff]) {
      for (const t of d) {
        for (const v of (t as { y: number[] }).y) {
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
      }
    }
    if (!Number.isFinite(lo)) return null;
    const pad = (hi - lo) * 0.03 || 10;
    return [hi + pad, lo >= 0 ? Math.max(0, lo - pad) : lo - pad];
  }, [traces]);

  const makeLayout = (key: PanelKey, xTitle: string): Partial<Plotly.Layout> => {
    const limitOps = key === "hookload" ? HOOKLOAD_OPS : key === "torque" ? TORQUE_OPS : [];
    const limitShapes: Partial<Plotly.Shape>[] = [];
    const limitNotes: Partial<Plotly.Annotations>[] = [];
    for (const op of limitOps) {
      if (!options.ops[op]) continue;
      for (const lim of profile.operations[op].limits ?? []) {
        limitShapes.push({
          type: "line",
          xref: "x",
          yref: "paper",
          x0: lim.value,
          x1: lim.value,
          y0: 0,
          y1: 1,
          line: { color: COLOR.limit, width: 2, dash: "dot" },
        });
        limitNotes.push({
          x: lim.value,
          xref: "x",
          yref: "paper",
          y: 1,
          yanchor: "bottom",
          showarrow: false,
          text: `${lim.kind === "max" ? "max" : "min"} ${SERIES_PREFIX[op]}`,
          font: { size: 10, color: COLOR.limit },
        });
        if (lim.cross_ml !== null) {
          limitShapes.push({
            type: "rect",
            xref: "paper",
            yref: "y",
            x0: 0,
            x1: 1,
            y0: lim.cross_ml,
            y1: (fullRange ?? [lim.cross_ml + 1, 0])[0],
            fillcolor: "rgba(227, 73, 72, 0.06)",
            line: { width: 0 },
            layer: "below",
          });
        }
      }
    }
    const zone: Partial<Plotly.Shape>[] = forecast
      ? [
          {
            type: "rect",
            xref: "paper",
            yref: "y",
            x0: 0,
            x1: 1,
            y0: forecast.start_depth,
            y1: forecast.end_depth,
            fillcolor: COLOR.forecastZone,
            line: { width: 0 },
            layer: "below",
          },
        ]
      : [];
    const zoneNote: Partial<Plotly.Annotations>[] = forecast
      ? [
          {
            x: 0,
            xref: "paper",
            y: forecast.start_depth,
            yref: "y",
            yanchor: "top",
            xanchor: "left",
            showarrow: false,
            text: `Forecast ${forecast.distance_ft} ft ahead`,
            font: { size: 10, color: COLOR.mlMinusWp },
          },
        ]
      : [];
    const shapes: Partial<Plotly.Shape>[] = intervals.map((iv) => ({
      type: "rect",
      xref: "paper",
      yref: "y",
      x0: 0,
      x1: 1,
      y0: iv.from,
      y1: iv.to,
      fillcolor: COLOR.flag,
      line: { width: 0 },
      layer: "below",
    }));
    const axisBase = {
      gridcolor: COLOR.grid,
      linecolor: COLOR.grid,
      tickfont: { color: COLOR.textMuted, size: 11 },
      automargin: true,
    };
    const range = (syncDepth ? yRange : panelY[key]) ?? fullRange;
    return {
      height: narrow ? 520 : 640,
      margin: { l: 64, r: 16, t: 12, b: 48 },
      paper_bgcolor: COLOR.surface,
      plot_bgcolor: COLOR.surface,
      font: { family: "inherit", color: COLOR.text },
      hovermode: "y unified",
      hoverlabel: { bgcolor: "#ffffff", bordercolor: COLOR.grid, font: { color: COLOR.text } },
      dragmode: "zoom",
      // UI revision: per-panel X zoom survives hover/flag changes
      uirevision: `${key}-${zoomRev}-${options.diffTarget}-${options.diffMode}`,
      showlegend: !narrow,
      legend: { orientation: "v", x: 1.02, y: 1, font: { size: 11, color: COLOR.textMuted } },
      shapes: [...zone, ...shapes, ...limitShapes] as Plotly.Shape[],
      annotations: [...zoneNote, ...limitNotes] as Plotly.Annotations[],
      xaxis: {
        ...axisBase,
        title: { text: xTitle, font: { color: COLOR.textMuted, size: 12 } },
        ...(key === "diff"
          ? { zeroline: true, zerolinecolor: COLOR.zero, zerolinewidth: 2, range: [...traces.diffRange] }
          : { zeroline: false }),
      },
      yaxis: {
        ...axisBase,
        zeroline: false,
        title: { text: `Depth (${du})`, font: { color: COLOR.textMuted, size: 12 } },
        // depth is controlled by app state: the revision changes whenever the range changes
        uirevision: `${range ? range.join(",") : "auto"}-${zoomRev}`,
        // copy: Plotly writes the zoom result into the range array it is given
        ...(range ? { range: [...range], autorange: false } : { autorange: "reversed" }),
      },
    };
  };

  const diffUnit = options.diffMode === "abs" ? target.unit : "%";
  const panels: { key: PanelKey; title: string; data: Plotly.Data[]; xTitle: string }[] = [
    { key: "hookload", title: `Hookload (${hkUnit})`, data: traces.hookload, xTitle: `Hookload (${hkUnit})` },
    { key: "torque", title: `Torque (${tqUnit})`, data: traces.torque, xTitle: `Torque (${tqUnit})` },
    {
      key: "diff",
      title: `Difference (Δ): ${OP_LABEL[options.diffTarget]} (${diffUnit})`,
      data: traces.diff,
      xTitle: `← lower (−)   Difference Δ (${diffUnit})   higher (+) →`,
    },
  ];
  // layouts are rebuilt only when inputs change (Plotly.react is cheap when equal)
  const layouts = useMemo(
    () => Object.fromEntries(panels.map((p) => [p.key, makeLayout(p.key, p.xTitle)])) as Record<
      PanelKey,
      Partial<Plotly.Layout>
    >,
    [narrow, intervals, yRange, fullRange, panelY, syncDepth, zoomRev, traces, options, du, hkUnit, tqUnit, target, forecast],
  );

  const onHover = (e: Plotly.PlotHoverEvent) => {
    const y = e.points?.[0]?.y;
    if (typeof y !== "number") return;
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => setHoverDepth(y));
  };

  const resetZoom = () => {
    setYRange(null);
    setPanelY({ hookload: null, torque: null, diff: null });
    setZoomRev((x) => x + 1);
  };

  const onRelayout = (key: PanelKey) => (e: Plotly.PlotRelayoutEvent) => {
    const r = yRangeFromRelayout(e);
    if (r === undefined) return;
    if (r === null) {
      // double click: back to the shared full range (still reversed, aligned)
      resetZoom();
      return;
    }
    if (syncDepth) setYRange(r);
    else setPanelY((p) => ({ ...p, [key]: r }));
  };

  // Synchronised readout: values of all profiles at the guide depth
  const readout = useMemo(() => {
    if (hoverDepth === null) return null;
    const tol = du === "ft" ? 60 : 20;
    const rows: { label: string; wp: number | null; ml: number | null; act: number | null; unit: string }[] = [];
    for (const op of [...HOOKLOAD_OPS, ...TORQUE_OPS]) {
      if (!options.ops[op]) continue;
      const o = profile.operations[op];
      const base = o.wellplan.find((s) => s.ff === o.wellplan_baseline_ff) ?? o.wellplan[0];
      rows.push({
        label: SERIES_PREFIX[op],
        wp: base ? interpAt(base.depth, base.value, hoverDepth) : null,
        ml: interpAt(o.ml.depth, o.ml.value, hoverDepth),
        act: nearest(o.actual.depth, o.actual.value, hoverDepth, tol),
        unit: o.unit,
      });
    }
    const t = target.diff;
    const diffs = DIFF_KEYS.map((k) => ({
      key: k,
      v: k === "ml_minus_wp" ? interpAt(t[k].depth, t[k].abs, hoverDepth) : nearest(t[k].depth, t[k].abs, hoverDepth, tol),
    }));
    return { rows, diffs };
  }, [hoverDepth, profile, options.ops, target, du]);

  const f = (v: number | null) => (v === null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: 1 }));
  const zoomed = yRange !== null || Object.values(panelY).some((r) => r !== null);

  return (
    <div className="chart-stack" onMouseLeave={() => setHoverDepth(null)}>
      <div className="chart-toolbar">
        <label className="check">
          <input
            type="checkbox"
            checked={syncDepth}
            onChange={(e) => {
              setSyncDepth(e.target.checked);
              setPanelY({ hookload: null, torque: null, diff: null });
            }}
          />
          Same depth in all panels when zooming
        </label>
        <span className="muted small">
          Zoom: drag a box on a chart · pan: hand icon in the chart toolbar · double click: full view
        </span>
        <div className="spacer" />
        <button className="btn small" onClick={resetZoom} disabled={!zoomed}>
          Reset zoom
        </button>
      </div>

      {panels.map((p) => (
        <section key={p.key} className="chart-panel" aria-label={p.title}>
          <h3>{p.title}</h3>
          {p.data.length ? (
            <PlotlyChart
              data={p.data}
              layout={layouts[p.key]}
              config={CONFIG}
              onHover={onHover}
              onRelayout={onRelayout(p.key)}
              guideY={hoverDepth}
            />
          ) : (
            <p className="muted">No data for this panel (check the operation checkboxes).</p>
          )}
        </section>
      ))}

      <div className="readout" aria-live="polite">
        {readout ? (
          <>
            <b>
              Depth {hoverDepth!.toLocaleString("en-US", { maximumFractionDigits: 0 })} {du}
            </b>
            {readout.rows.map((r) => (
              <span key={r.label}>
                {r.label}: <i className="k wp">WP</i> {f(r.wp)} · <i className="k ml">ML</i> {f(r.ml)} ·{" "}
                <i className="k act">Act</i> {f(r.act)} {r.unit}
              </span>
            ))}
            <span>
              Δ {OP_LABEL[options.diffTarget]}:{" "}
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
            Hover over any chart: a guide line appears in all panels at the same depth and the values are shown
            here.
          </span>
        )}
      </div>
    </div>
  );
}
