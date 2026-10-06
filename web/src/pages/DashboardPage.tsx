import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, fmt, Forecast, ModelItem, Op, OP_LABEL, OPS, Profile, PURPOSE_LABEL, Q_LABEL, QStatus, TYPES, WellItem } from "../api";
import ForecastPanel from "../components/ForecastPanel";
import LimitsPanel from "../components/LimitsPanel";
import QualityBadge from "../components/QualityBadge";
import ThreeProfileChart, {
  ChartOptions,
  flaggedIntervals,
  HOOKLOAD_OPS,
  TORQUE_OPS,
} from "../components/ThreeProfileChart";
import { DIFF_KEYS, DIFF_LABEL, DiffKey, OHFF_COLOR } from "../components/chartTheme";

const pctTxt = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export default function DashboardPage() {
  const { wellId } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const wells = useQuery({ queryKey: ["wells"], queryFn: () => api.get<WellItem[]>("/api/wells") });
  const [section, setSection] = useState("");
  const [wtype, setWtype] = useState("");
  const [units, setUnits] = useState<"imperial" | "si">("imperial");
  const [quality, setQuality] = useState<"" | QStatus>("");
  const [modelId, setModelId] = useState("");
  const [group, setGroup] = useState<"" | "training" | "monitoring">("");
  const [calibration, setCalibration] = useState<"" | "calibrated" | "raw">("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const models = useQuery({ queryKey: ["models"], queryFn: () => api.get<ModelItem[]>("/api/models") });
  const usable = (models.data ?? []).filter((m) => m.status === "done" || m.status === "held");
  const [opts, setOpts] = useState<ChartOptions>({
    ops: Object.fromEntries(OPS.map((o) => [o, true])) as Record<Op, boolean>,
    showFF: true,
    diffTarget: "pick_up",
    diffMode: "abs",
    flagSeries: "ml_minus_actual",
    threshold: 5,
    showBand: false,
  });

  const filtered = (wells.data ?? []).filter(
    (w) =>
      (!group || w.purpose === group) &&
      (!section || String(w.section_in) === section) &&
      (!wtype || w.well_type === wtype) &&
      (!quality || w.quality === quality),
  );
  const selectedId = wellId ? Number(wellId) : filtered.find((w) => w.actual_points > 0)?.id ?? filtered[0]?.id;

  useEffect(() => {
    if (!wellId && selectedId) nav(`/dashboard/${selectedId}`, { replace: true });
  }, [wellId, selectedId, nav]);

  const qs = `units=${units}${modelId ? `&model_id=${modelId}` : ""}${calibration ? `&calibration=${calibration}` : ""}`;
  const profile = useQuery({
    queryKey: ["profile", selectedId, units, modelId, calibration],
    queryFn: () => api.get<Profile>(`/api/wells/${selectedId}/profile?${qs}`),
    enabled: !!selectedId,
  });
  // a forecast belongs to one well / unit system / model
  useEffect(() => setForecast(null), [selectedId, units, modelId, calibration]);
  const predict = useMutation({
    mutationFn: () => api.post(`/api/wells/${selectedId}/predict${modelId ? `?model_id=${modelId}` : ""}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["wells"] });
    },
    onError: (e) => alert((e as Error).message),
  });

  const p = profile.data;
  // Without actual data only ML − WellPlan can be flagged
  const flagSeries: DiffKey = p && !p.has_actual ? "ml_minus_wp" : opts.flagSeries;
  const target = p?.operations[opts.diffTarget];
  const flagData = target?.diff[flagSeries];
  const flagVals = flagData ? (opts.diffMode === "abs" ? flagData.abs : flagData.pct) : [];
  const intervals = useMemo(
    () => (flagData ? flaggedIntervals(flagData.depth, flagVals, opts.threshold) : []),
    [flagData, flagVals, opts.threshold],
  );

  const top5 = useMemo(() => {
    if (!flagData) return [];
    return flagData.depth
      .map((d, i) => ({ d, abs: flagData.abs[i], pct: flagData.pct[i] }))
      .sort((a, b) => (opts.diffMode === "abs" ? Math.abs(b.abs) - Math.abs(a.abs) : Math.abs(b.pct) - Math.abs(a.pct)))
      .slice(0, 5);
  }, [flagData, opts.diffMode]);

  const set = <K extends keyof ChartOptions>(k: K, v: ChartOptions[K]) => setOpts((o) => ({ ...o, [k]: v }));
  const sections = [...new Set((wells.data ?? []).map((w) => w.section_in).filter((s) => s !== null))];
  const modeUnit = opts.diffMode === "abs" ? target?.unit ?? "" : "%";

  return (
    <div className="page wide">
      <section className="card filters">
        <div className="row gap wrap">
          <label className="inline">
            Data group
            <select value={group} onChange={(e) => setGroup(e.target.value as typeof group)}>
              <option value="">All</option>
              <option value="training">{PURPOSE_LABEL.training}</option>
              <option value="monitoring">{PURPOSE_LABEL.monitoring}</option>
            </select>
          </label>
          <label className="inline">
            Well section
            <select value={section} onChange={(e) => setSection(e.target.value)}>
              <option value="">All</option>
              {sections.map((s) => (
                <option key={s} value={String(s)}>
                  {s}"
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Well type
            <select value={wtype} onChange={(e) => setWtype(e.target.value)}>
              <option value="">All</option>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="inline">
            Quality
            <select value={quality} onChange={(e) => setQuality(e.target.value as "" | QStatus)}>
              <option value="">All</option>
              {(["A", "B", "C", "X"] as QStatus[]).map((q) => (
                <option key={q} value={q}>
                  {q} · {Q_LABEL[q]}
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Well
            <select value={selectedId ?? ""} onChange={(e) => nav(`/dashboard/${e.target.value}`)}>
              {!filtered.some((w) => w.id === selectedId) && selectedId && <option value={selectedId}>(outside the filter)</option>}
              {filtered.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.purpose === "monitoring" ? "[Monitoring] " : ""}
                  {w.name} · {w.section_in}" · {w.well_type ?? "?"} · {w.quality} {w.actual_points ? "" : "· no actual data"}
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Units
            <select value={units} onChange={(e) => setUnits(e.target.value as "imperial" | "si")}>
              <option value="imperial">Imperial (ft, klbf, ft-lbf)</option>
              <option value="si">SI (m, kN, kN·m)</option>
            </select>
          </label>
          <label className="inline">
            Model
            <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
              <option value="">active</option>
              {usable.map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.id} · dataset v{m.dataset_version ?? "?"} {m.active ? "(active)" : m.status === "held" ? "(held)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="inline" title="DD Calibrate offsets from the roadmap file (as the Excel 'Graph reference')">
            WellPlan curves
            <select value={calibration} onChange={(e) => setCalibration(e.target.value as typeof calibration)}>
              <option value="">Automatic</option>
              <option value="calibrated">With DD Calibrate</option>
              <option value="raw">As modelled</option>
            </select>
          </label>
          <div className="spacer" />
          {selectedId && (
            <>
              <button className="btn" onClick={() => predict.mutate()} disabled={predict.isPending}>
                {predict.isPending ? "Predicting…" : "Run prediction again"}
              </button>
              <a
                className="btn"
                href={`/api/wells/${selectedId}/report.pdf?${qs}&target=${opts.diffTarget}`}
              >
                PDF
              </a>
              <a
                className="btn primary"
                href={`/api/wells/${selectedId}/export.xlsx?${qs}&target=${opts.diffTarget}`}
              >
                Export Excel
              </a>
            </>
          )}
        </div>
        {!filtered.length && wells.isSuccess && <div className="alert">No wells for this filter.</div>}
      </section>

      <section className="card filters">
        <div className="row gap wrap">
          <fieldset>
            <legend>Hookload</legend>
            {HOOKLOAD_OPS.map((o) => (
              <label key={o} className="check">
                <input type="checkbox" checked={opts.ops[o]} onChange={(e) => set("ops", { ...opts.ops, [o]: e.target.checked })} />
                {OP_LABEL[o]}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Torque</legend>
            {TORQUE_OPS.map((o) => (
              <label key={o} className="check">
                <input type="checkbox" checked={opts.ops[o]} onChange={(e) => set("ops", { ...opts.ops, [o]: e.target.checked })} />
                {OP_LABEL[o]}
              </label>
            ))}
            <label className="check">
              <input type="checkbox" checked={opts.showFF} onChange={(e) => set("showFF", e.target.checked)} />
              All OHFF curves
            </label>
            <label className="check">
              <input type="checkbox" checked={opts.showBand} onChange={(e) => set("showBand", e.target.checked)} />
              Uncertainty band (P10–P90)
            </label>
          </fieldset>
          <fieldset>
            <legend>Difference (Δ) chart</legend>
            <select value={opts.diffTarget} onChange={(e) => set("diffTarget", e.target.value as Op)}>
              {OPS.map((o) => (
                <option key={o} value={o}>
                  {OP_LABEL[o]}
                </option>
              ))}
            </select>
            <div className="seg">
              <button className={opts.diffMode === "abs" ? "on" : ""} onClick={() => setOpts((o) => ({ ...o, diffMode: "abs", threshold: 5 }))}>
                Absolute
              </button>
              <button className={opts.diffMode === "pct" ? "on" : ""} onClick={() => setOpts((o) => ({ ...o, diffMode: "pct", threshold: 5 }))}>
                Percent
              </button>
            </div>
          </fieldset>
          <fieldset>
            <legend>Flag intervals</legend>
            <select
              value={flagSeries}
              disabled={!!p && !p.has_actual}
              onChange={(e) => set("flagSeries", e.target.value as DiffKey)}
            >
              {DIFF_KEYS.map((k) => (
                <option key={k} value={k}>
                  {DIFF_LABEL[k]}
                </option>
              ))}
            </select>
            <label className="inline">
              |Δ| &gt;
              <input
                type="number"
                min={0}
                step="any"
                value={opts.threshold}
                onChange={(e) => set("threshold", Number(e.target.value))}
                style={{ width: 80 }}
              />
              {modeUnit}
            </label>
          </fieldset>
        </div>
      </section>

      {profile.isLoading && <div className="card muted">Loading profile…</div>}
      {profile.isError && <div className="alert error">{(profile.error as Error).message}</div>}

      {p && (
        <>
          {p.warnings.length > 0 && (
            <div className="alert warn">
              {p.warnings.map((w, i) => (
                <div key={i}>⚠ {w}</div>
              ))}
            </div>
          )}
          <section className="card">
            <div className="row space wrap">
              <h2>
                {p.well.name} · {p.well.section_in}" · {p.well.well_type ?? "?"}
              </h2>
              <span className="row gap">
                <QualityBadge s={p.quality.status} long />
                <span className="muted small">
                {p.prediction
                  ? p.prediction.kind === "oof"
                    ? `ML prediction out-of-fold (model #${p.prediction.model_id} never saw this well)`
                    : `ML prediction, model #${p.prediction.model_id}`
                  : "No ML prediction yet"}
                {p.model?.dataset_version ? ` · dataset v${p.model.dataset_version}` : ""}
                </span>
              </span>
            </div>
            <div className="small legend-note">
              <div>
                <b>T&amp;D Model (one colour per OHFF):</b>{" "}
                {Object.entries(OHFF_COLOR).map(([ff, c]) => (
                  <span key={ff} className="nowrap">
                    <span className="sw" style={{ background: c }} /> {ff}&nbsp;{" "}
                  </span>
                ))}
                · <span className="sw ml" /> ML prediction{opts.showBand ? " (dashed = P10–P90 band)" : ""} ·{" "}
                <span className="dot act" /> Actual (points) · <span className="sw limit" /> operating limit (dotted)
                {p.calibration.mode === "calibrated" && <> · T&amp;D Model includes the DD Calibrate offsets</>}
                {forecast && (
                  <>
                    {" "}
                    · <span className="sw" style={{ background: "#4a3aa7", height: 4 }} /> <b>Prediction ahead</b> (thick purple line,
                    shaded band = P10–P90, value at the end of the window)
                  </>
                )}
              </div>
              <div>
                <b>Names:</b> PU = pick up, SO = slack off, ROT = rotating weight (one curve). Actual markers: ● PU / torque
                off bottom · ▲ SO / torque on bottom · ■ ROT.
              </div>
              <div>
                <b>Difference (Δ):</b> ● T&amp;D Model − Actual (blue) · ◆ ML − Actual (orange) · <span className="sw mlwp" /> ML −
                T&amp;D Model. <b>A − B: right (+) = A is higher, left (−) = A is lower.</b>
                {intervals.length > 0 && (
                  <>
                    {" "}
                    <span className="sw flag" /> {intervals.length} intervals |{DIFF_LABEL[flagSeries]}| &gt;{" "}
                    {opts.threshold} {modeUnit}
                  </>
                )}
              </div>
            </div>
            <ThreeProfileChart profile={p} options={{ ...opts, flagSeries }} intervals={intervals} forecast={forecast} />
          </section>

          <ForecastPanel
            wellId={p.well.id}
            units={units}
            modelId={modelId}
            calibration={calibration}
            forecast={forecast}
            onForecast={setForecast}
            hasActual={p.has_actual}
            key={`${p.well.id}-${p.has_actual}`}
          />

          {p.quality.issues.length > 0 && (
            <details className="card">
              <summary>
                Data quality notes ({p.quality.issues.length}){p.quality.review ? ` · review: ${p.quality.review.decision}` : ""}
              </summary>
              <ul className="issues">
                {p.quality.issues.map((c, i) => (
                  <li key={i} className={c.level === "critical" ? "error" : "warning"}>
                    {c.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <LimitsPanel profile={p} />
          <div className="grid2">
            <section className="card">
              <h3>
                5 depths with the largest difference · {DIFF_LABEL[flagSeries]} · {OP_LABEL[opts.diffTarget]}
              </h3>
              {top5.length ? (
                <table>
                  <thead>
                    <tr>
                      <th className="num">Depth ({p.depth_unit})</th>
                      <th>Direction</th>
                      <th className="num">Δ ({target?.unit})</th>
                      <th className="num">Δ (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top5.map((r) => (
                      <tr key={r.d}>
                        <td className="num">{fmt(r.d, 0)}</td>
                        <td>{r.abs >= 0 ? "→ Right (higher)" : "← Left (lower)"}</td>
                        <td className="num">
                          {r.abs > 0 ? "+" : ""}
                          {fmt(r.abs)}
                        </td>
                        <td className="num">
                          {r.pct > 0 ? "+" : ""}
                          {fmt(r.pct, 1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">No difference data for this selection.</p>
              )}
              {intervals.length > 0 && (
                <>
                  <h3>Flagged intervals</h3>
                  <ul className="small">
                    {intervals.map((iv, i) => (
                      <li key={i}>
                        {fmt(iv.from, 0)} – {fmt(iv.to, 0)} {p.depth_unit}: peak {iv.peak > 0 ? "+" : ""}
                        {fmt(iv.peak)} {modeUnit} ({iv.peak > 0 ? "right" : "left"})
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
            <section className="card">
              <h3>Metrics for this well</h3>
              {p.has_actual ? (
                <table>
                  <thead>
                    <tr>
                      <th>Operation</th>
                      <th className="num">RMSE WP</th>
                      <th className="num">RMSE ML</th>
                      <th className="num">MAPE WP</th>
                      <th className="num">MAPE ML</th>
                      <th className="num">R² WP</th>
                      <th className="num">R² ML</th>
                      <th className="num" title="Share of actual points with |error| below the client tolerance">
                        Within tol. WP → ML
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {OPS.map((o) => {
                      const m = p.operations[o].metrics;
                      return (
                        <tr key={o}>
                          <td>
                            {OP_LABEL[o]} <span className="muted small">({p.operations[o].unit})</span>
                          </td>
                          <td className="num">{fmt(m?.wellplan?.rmse)}</td>
                          <td className="num">{fmt(m?.ml?.rmse)}</td>
                          <td className="num">{fmt(m?.wellplan?.mape, 1)}%</td>
                          <td className="num">{fmt(m?.ml?.mape, 1)}%</td>
                          <td className="num">{fmt(m?.wellplan?.r2)}</td>
                          <td className="num">{fmt(m?.ml?.r2)}</td>
                          <td className="num nowrap">
                            {pctTxt(m?.wellplan?.within)} → <b>{pctTxt(m?.ml?.within)}</b>{" "}
                            <span className="muted small">(&lt; {p.operations[o].tolerance})</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <p className="muted">No actual data for this well yet; metrics cannot be computed.</p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
