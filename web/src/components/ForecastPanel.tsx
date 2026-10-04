import { useState } from "react";
import { api, ApiError, Forecast, fmt, Op, OPS, SERIES_PREFIX } from "../api";

type Props = {
  wellId: number;
  units: "imperial" | "si";
  modelId: string;
  calibration: string;
  forecast: Forecast | null;
  onForecast: (f: Forecast | null) => void;
};

/** Forecast N ft ahead of the last actual depth, with cause and effect. */
export default function ForecastPanel({ wellId, units, modelId, calibration, forecast, onForecast }: Props) {
  const [distance, setDistance] = useState(300);
  const [start, setStart] = useState("");
  const [bias, setBias] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const body = () => ({
    distance_ft: distance,
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
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "forecast.xlsx";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const ops = forecast ? OPS.filter((o) => forecast.operations[o]) : [];
  const last = (a: (number | null)[]) => (a.length ? a[a.length - 1] : null);

  return (
    <section className="card">
      <div className="row space wrap">
        <h2>Forecast ahead</h2>
        <div className="row gap wrap small">
          <label className="inline">
            Distance
            <input type="number" min={10} step={50} value={distance} onChange={(e) => setDistance(Number(e.target.value))} style={{ width: 90 }} />
            ft
          </label>
          <label className="inline" title="Default: the last actual depth">
            From depth
            <input type="number" min={0} value={start} onChange={(e) => setStart(e.target.value)} placeholder="last actual" style={{ width: 110 }} />
            ft
          </label>
          <label className="check" title="Shift the forecast by the median (actual − ML) of the last actual points">
            <input type="checkbox" checked={bias} onChange={(e) => setBias(e.target.checked)} />
            Local bias correction
          </label>
          <button className="btn primary" onClick={run} disabled={busy || !(distance > 0)}>
            {busy ? "Forecasting…" : "Forecast"}
          </button>
          <button className="btn" onClick={download} disabled={!forecast}>
            ⬇ Forecast (.xlsx)
          </button>
          {forecast && (
            <button className="btn ghost" onClick={() => onForecast(null)}>
              Clear
            </button>
          )}
        </div>
      </div>
      <p className="muted small">
        Forecasts hookload and torque for the next N ft from the last actual depth with the active model: ML forecast,
        uncertainty band (P10–P90) and the T&amp;D Model curve per OHFF. The explanation lists what drives the change (local SHAP
        contributions), plan changes (inclination, dogleg, interval type) and operating limits that would be reached. The
        forecast window is shaded in the charts above.
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
                        {fmt(last(o.p10), 1)} – {fmt(last(o.p90), 1)}
                      </td>
                      {forecast.bias_correction && (
                        <td className="num">
                          {o.ml_corrected ? `${fmt(last(o.ml_corrected), 1)} (bias ${o.bias! > 0 ? "+" : ""}${fmt(o.bias, 1)})` : "–"}
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
            Contributions: {forecast.operations[ops[0]]?.explanation.method ?? "SHAP"} (the change of each feature's
            contribution between the start and the end of the window; "T&amp;D Model" = the change of the T&amp;D Model curve
            itself).
          </p>
        </>
      )}
    </section>
  );
}
