import { useState } from "react";
import { api, ApiError, Forecast, fmt, Op, OPS, SERIES_PREFIX } from "../api";

type Props = {
  wellId: number;
  units: "imperial" | "si";
  modelId: string;
  calibration: string;
  forecast: Forecast | null;
  onForecast: (f: Forecast | null) => void;
  hasActual: boolean;
};

/** Forecast N ft ahead of the last actual depth, with cause and effect. */
export default function ForecastPanel({ wellId, units, modelId, calibration, forecast, onForecast, hasActual }: Props) {
  const [distance, setDistance] = useState(300);
  const [step, setStep] = useState(30);
  const [start, setStart] = useState("");
  // default on when the well already has actual readings (most accurate in the backtest)
  const [bias, setBias] = useState(hasActual);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const body = () => ({
    distance_ft: distance,
    step_ft: step,
    start_depth_ft: start ? Number(start) : null,
    bias_correction: bias,
    units,
    model_id: modelId ? Number(modelId) : null,
    calibration: calibration || null,
  });

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      onForecast(await api.post<Forecast>(`/api/wells/${wellId}/forecast`, body()));
      // show the result where it is drawn: the charts zoom to the forecast window
      setTimeout(() => document.getElementById("profile-charts")?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
    } catch (e) {
      setErr((e as Error).message);
      onForecast(null);
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    const res = await fetch(`/api/wells/${wellId}/forecast.xlsx`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body()),
    });
    if (!res.ok) {
      setErr(new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? res.statusText).message);
      return;
    }
    const blob = await res.blob();
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "prediction.xlsx";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const ops = forecast ? OPS.filter((o) => forecast.operations[o]) : [];
  const last = (a: (number | null)[]) => (a.length ? a[a.length - 1] : null);
  // the band moves with the bias correction (same as the shaded band in the charts)
  const shifted = (v: number | null, b: number | null) => (v == null ? null : v + (forecast?.bias_correction ? (b ?? 0) : 0));

  return (
    <section className="card">
      <div className="row space wrap">
        <h2>Prediction ahead</h2>
        <div className="row gap wrap small">
          <label className="inline">
            Distance
            <input type="number" min={10} step={50} value={distance} onChange={(e) => setDistance(Number(e.target.value))} style={{ width: 90 }} />
            ft
          </label>
          <label className="inline" title="Depth interval between computed prediction points (one dot on the purple line per point)">
            Step
            <select value={step} onChange={(e) => setStep(Number(e.target.value))}>
              <option value={10}>10 ft</option>
              <option value={30}>30 ft</option>
              <option value={100}>100 ft</option>
            </select>
          </label>
          <label className="inline" title="Default: the last actual depth">
            From depth
            <input type="number" min={0} value={start} onChange={(e) => setStart(e.target.value)} placeholder="last actual" style={{ width: 110 }} />
            ft
          </label>
          <label className="check" title="Shift the prediction by the median (actual − ML) of the last actual points">
            <input type="checkbox" checked={bias} onChange={(e) => setBias(e.target.checked)} />
            Local bias correction
          </label>
          <button className="btn primary" onClick={run} disabled={busy || !(distance > 0)}>
            {busy ? "Predicting…" : "Run prediction"}
          </button>
          <button className="btn" onClick={download} disabled={!forecast}>
            ⬇ Prediction (.xlsx)
          </button>
          {forecast && (
            <button className="btn ghost" onClick={() => onForecast(null)}>
              Clear
            </button>
          )}
        </div>
      </div>
      <p className="muted small">
        <b>To test the model on a well that already has actual readings</b>, enter an earlier <i>From depth</i>: the prediction
        then only uses data above that depth, and the column <i>Check against actual</i> compares it with the readings
        that follow. Predicts hookload and torque for the next N ft from the last actual depth with the active model: ML prediction,
        uncertainty band (P10–P90) and the T&amp;D Model curve per OHFF. The explanation lists what drives the change (local SHAP
        contributions), plan changes (inclination, dogleg, interval type) and operating limits that would be reached. The
        prediction window is shaded in the charts above.
      </p>
      {err && <div className="alert error">{err}</div>}
      {forecast && (
        <>
          {forecast.warnings.length > 0 && (
            <div className="alert warn">
              {forecast.warnings.map((w, i) => (
                <div key={i}>⚠ {w}</div>
              ))}
            </div>
          )}
          <p className="small">
            <b>
              {fmt(forecast.start_depth, 0)} → {fmt(forecast.end_depth, 0)} {forecast.depth_unit}
            </b>{" "}
            <span className="muted">
              · last actual depth {forecast.last_actual_depth === null ? "–" : `${fmt(forecast.last_actual_depth, 0)} ${forecast.depth_unit}`} ·
              model #{forecast.model_id} · T&amp;D Model {forecast.calibration === "calibrated" ? "with DD Calibrate" : "as modelled"}
            </span>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th className="num">ML at start</th>
                  <th className="num">ML at end</th>
                  <th className="num">Change</th>
                  <th className="num">P10–P90 at end</th>
                  {forecast.bias_correction && <th className="num">Bias-corrected at end</th>}
                  <th className="num" title="Backtest on unseen wells for this distance">Expected accuracy</th>
                  {ops.some((op) => forecast.operations[op]?.actual_check) && (
                    <th className="num" title="Actual readings that lie inside the prediction window (prediction started before the last actual depth)">
                      Check against actual
                    </th>
                  )}
                  <th>Main drivers (contribution to the change)</th>
                </tr>
              </thead>
              <tbody>
                {ops.map((op: Op) => {
                  const o = forecast.operations[op]!;
                  return (
                    <tr key={op}>
                      <td>
                        {SERIES_PREFIX[op]} <span className="muted small">({o.unit})</span>
                      </td>
                      <td className="num">{fmt(o.ml[0], 1)}</td>
                      <td className="num">
                        <b>{fmt(last(o.ml), 1)}</b>
                      </td>
                      <td className="num">
                        {o.change > 0 ? "+" : ""}
                        {fmt(o.change, 1)}
                      </td>
                      <td className="num">
                        {fmt(shifted(last(o.p10), o.bias), 1)} – {fmt(shifted(last(o.p90), o.bias), 1)}
                      </td>
                      {forecast.bias_correction && (
                        <td className="num">
                          {o.ml_corrected ? `${fmt(last(o.ml_corrected), 1)} (bias ${o.bias! > 0 ? "+" : ""}${fmt(o.bias, 1)})` : "–"}
                        </td>
                      )}
                      <td className="num small nowrap">
                        {o.backtest ? (
                          <span title={`${o.backtest.method}, backtest ${o.backtest.horizon_ft} ft, P90 error ${fmt(o.backtest.p90, 1)} ${o.unit}`}>
                            <b>{Math.round(o.backtest.within * 100)}%</b> &lt; {o.tolerance}
                          </span>
                        ) : (
                          "–"
                        )}
                      </td>
                      {ops.some((op) => forecast.operations[op]?.actual_check) && (
                        <td className="num small nowrap">
                          {o.actual_check ? (
                            <span
                              title={`${o.actual_check.n} actual readings in the window. Mean |error|: ML ${fmt(o.actual_check.ml_mean_abs, 1)}${o.actual_check.ml_bias_mean_abs != null ? `, ML + bias ${fmt(o.actual_check.ml_bias_mean_abs, 1)}` : ""} ${o.actual_check.unit}`}
                            >
                              T&amp;D {Math.round(o.actual_check.td_within * 100)}% · ML{" "}
                              {o.actual_check.ml_bias_within != null
                                ? `+ bias ${Math.round(o.actual_check.ml_bias_within * 100)}%`
                                : `${Math.round(o.actual_check.ml_within * 100)}%`}{" "}
                              <span className="muted">(n={o.actual_check.n})</span>
                            </span>
                          ) : (
                            "–"
                          )}
                        </td>
                      )}
                      <td className="small">
                        {o.explanation.drivers.slice(0, 3).map((d) => (
                          <span key={d.feature} className="nowrap">
                            {d.label} {d.delta > 0 ? "+" : ""}
                            {fmt(d.delta, 1)};{" "}
                          </span>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h3>Cause and effect</h3>
          {ops.map((op) => (
            <p key={op} className="small forecast-sentence">
              {forecast.operations[op]!.explanation.sentence}
            </p>
          ))}
          <p className="muted small">
            Expected accuracy = share of actual points within the client tolerance (8 klbf hookload, 0.8 kft-lbf torque)
            when this model predicted the same distance on wells it never saw
            {forecast.bias_correction ? ", with local bias correction" : ", without bias correction"}. Contributions: {forecast.operations[ops[0]]?.explanation.method ?? "SHAP"} (the change of each feature's
            contribution between the start and the end of the window; "T&amp;D Model" = the change of the T&amp;D Model curve
            itself).
          </p>
        </>
      )}
    </section>
  );
}
