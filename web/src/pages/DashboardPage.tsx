import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, fmt, ModelItem, Op, OP_LABEL, OPS, Profile, Q_LABEL, QStatus, WellItem } from "../api";
import LimitsPanel from "../components/LimitsPanel";
import QualityBadge from "../components/QualityBadge";
import ThreeProfileChart, {
  ChartOptions,
  flaggedIntervals,
  HOOKLOAD_OPS,
  TORQUE_OPS,
} from "../components/ThreeProfileChart";
import { DIFF_KEYS, DIFF_LABEL, DiffKey } from "../components/chartTheme";

const TYPES = ["J", "S", "Horizontal"];

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
  const models = useQuery({ queryKey: ["models"], queryFn: () => api.get<ModelItem[]>("/api/models") });
  const usable = (models.data ?? []).filter((m) => m.status === "selesai" || m.status === "ditahan");
  const [opts, setOpts] = useState<ChartOptions>({
    ops: Object.fromEntries(OPS.map((o) => [o, true])) as Record<Op, boolean>,
    showFF: false,
    diffTarget: "pick_up",
    diffMode: "abs",
    flagSeries: "ml_minus_actual",
    threshold: 5,
    showBand: true,
  });

  const filtered = (wells.data ?? []).filter(
    (w) =>
      (!section || String(w.section_in) === section) &&
      (!wtype || w.well_type === wtype) &&
      (!quality || w.quality === quality),
  );
  const selectedId = wellId ? Number(wellId) : filtered.find((w) => w.actual_points > 0)?.id ?? filtered[0]?.id;

  useEffect(() => {
    if (!wellId && selectedId) nav(`/dashboard/${selectedId}`, { replace: true });
  }, [wellId, selectedId, nav]);

  const profile = useQuery({
    queryKey: ["profile", selectedId, units, modelId],
    queryFn: () => api.get<Profile>(`/api/wells/${selectedId}/profile?units=${units}${modelId ? `&model_id=${modelId}` : ""}`),
    enabled: !!selectedId,
  });
  const predict = useMutation({
    mutationFn: () => api.post(`/api/wells/${selectedId}/predict${modelId ? `?model_id=${modelId}` : ""}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["wells"] });
    },
    onError: (e) => alert((e as Error).message),
  });

  const p = profile.data;
  // Tanpa data aktual: hanya ML − WellPlan yang bisa ditandai
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
            Section
            <select value={section} onChange={(e) => setSection(e.target.value)}>
              <option value="">Semua</option>
              {sections.map((s) => (
                <option key={s} value={String(s)}>
                  {s}"
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Tipe sumur
            <select value={wtype} onChange={(e) => setWtype(e.target.value)}>
              <option value="">Semua</option>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="inline">
            Kualitas
            <select value={quality} onChange={(e) => setQuality(e.target.value as "" | QStatus)}>
              <option value="">Semua</option>
              {(["A", "B", "C", "X"] as QStatus[]).map((q) => (
                <option key={q} value={q}>
                  {q} · {Q_LABEL[q]}
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Sumur
            <select value={selectedId ?? ""} onChange={(e) => nav(`/dashboard/${e.target.value}`)}>
              {!filtered.some((w) => w.id === selectedId) && selectedId && <option value={selectedId}>(di luar filter)</option>}
              {filtered.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} · {w.section_in}" · {w.well_type ?? "?"} · {w.quality} {w.actual_points ? "" : "· tanpa aktual"}
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Satuan
            <select value={units} onChange={(e) => setUnits(e.target.value as "imperial" | "si")}>
              <option value="imperial">Imperial (ft, klbf, ft-lbf)</option>
              <option value="si">SI (m, kN, kN·m)</option>
            </select>
          </label>
          <label className="inline">
            Model
            <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
              <option value="">aktif</option>
              {usable.map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.id} · dataset v{m.dataset_version ?? "?"} {m.active ? "(aktif)" : m.status === "ditahan" ? "(ditahan)" : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="spacer" />
          {selectedId && (
            <>
              <button className="btn" onClick={() => predict.mutate()} disabled={predict.isPending}>
                {predict.isPending ? "Memprediksi…" : "Prediksi ulang"}
              </button>
              <a
                className="btn"
                href={`/api/wells/${selectedId}/report.pdf?units=${units}&target=${opts.diffTarget}${modelId ? `&model_id=${modelId}` : ""}`}
              >
                PDF
              </a>
              <a
                className="btn primary"
                href={`/api/wells/${selectedId}/export.xlsx?units=${units}&target=${opts.diffTarget}${modelId ? `&model_id=${modelId}` : ""}`}
              >
                Ekspor Excel
              </a>
            </>
          )}
        </div>
        {!filtered.length && wells.isSuccess && <div className="alert">Tidak ada sumur untuk filter ini.</div>}
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
              Semua kurva FF
            </label>
            <label className="check">
              <input type="checkbox" checked={opts.showBand} onChange={(e) => set("showBand", e.target.checked)} />
              Pita ketidakpastian ML
            </label>
          </fieldset>
          <fieldset>
            <legend>Grafik Selisih</legend>
            <select value={opts.diffTarget} onChange={(e) => set("diffTarget", e.target.value as Op)}>
              {OPS.map((o) => (
                <option key={o} value={o}>
                  {OP_LABEL[o]}
                </option>
              ))}
            </select>
            <div className="seg">
              <button className={opts.diffMode === "abs" ? "on" : ""} onClick={() => setOpts((o) => ({ ...o, diffMode: "abs", threshold: 5 }))}>
                Absolut
              </button>
              <button className={opts.diffMode === "pct" ? "on" : ""} onClick={() => setOpts((o) => ({ ...o, diffMode: "pct", threshold: 5 }))}>
                Persen
              </button>
            </div>
          </fieldset>
          <fieldset>
            <legend>Penandaan interval</legend>
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
              |selisih| &gt;
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

      {profile.isLoading && <div className="card muted">Memuat profil…</div>}
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
                    ? `Prediksi ML out-of-fold (model #${p.prediction.model_id} tanpa melihat sumur ini)`
                    : `Prediksi ML model #${p.prediction.model_id}`
                  : "Belum ada prediksi ML"}
                {p.model?.dataset_version ? ` · dataset v${p.model.dataset_version}` : ""}
                </span>
              </span>
            </div>
            <div className="small legend-note">
              <div>
                <b>Profil:</b> <span className="sw wp" /> WellPlan (FF {p.operations.pick_up.wellplan_baseline_ff ?? "–"}
                {opts.showFF ? "; FF lain lebih tipis" : ""}) &nbsp; <span className="sw ml" /> Prediksi ML &nbsp;{" "}
                <span className="dot act" /> Aktual (titik)
              </div>
              <div>
                <b>Operasi:</b> garis penuh / ● = pick up, torque off bottom · putus-putus / ▲ = slack off, torque on
                bottom · titik-titik / ■ = rotating weight
              </div>
              <div>
                <b>Selisih:</b> ● WellPlan − Aktual (biru) · ◆ ML − Aktual (oranye) · <span className="sw mlwp" /> ML −
                WellPlan. <b>A − B: kanan (+) = A lebih tinggi, kiri (−) = A lebih rendah.</b>
                {intervals.length > 0 && (
                  <>
                    {" "}
                    <span className="sw flag" /> {intervals.length} interval |{DIFF_LABEL[flagSeries]}| &gt;{" "}
                    {opts.threshold} {modeUnit}
                  </>
                )}
              </div>
            </div>
            <ThreeProfileChart profile={p} options={{ ...opts, flagSeries }} intervals={intervals} />
          </section>

          {p.quality.issues.length > 0 && (
            <details className="card">
              <summary>
                Catatan kualitas data ({p.quality.issues.length}){p.quality.review ? ` · tinjauan: ${p.quality.review.decision}` : ""}
              </summary>
              <ul className="issues">
                {p.quality.issues.map((c, i) => (
                  <li key={i} className={c.level === "kritis" ? "error" : "warning"}>
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
                5 kedalaman dengan selisih terbesar · {DIFF_LABEL[flagSeries]} · {OP_LABEL[opts.diffTarget]}
              </h3>
              {top5.length ? (
                <table>
                  <thead>
                    <tr>
                      <th className="num">Kedalaman ({p.depth_unit})</th>
                      <th>Arah</th>
                      <th className="num">Selisih ({target?.unit})</th>
                      <th className="num">Selisih (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top5.map((r) => (
                      <tr key={r.d}>
                        <td className="num">{fmt(r.d, 0)}</td>
                        <td>{r.abs >= 0 ? "→ Kanan (lebih tinggi)" : "← Kiri (lebih rendah)"}</td>
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
                <p className="muted">Tidak ada data selisih untuk pilihan ini.</p>
              )}
              {intervals.length > 0 && (
                <>
                  <h3>Interval ditandai</h3>
                  <ul className="small">
                    {intervals.map((iv, i) => (
                      <li key={i}>
                        {fmt(iv.from, 0)} – {fmt(iv.to, 0)} {p.depth_unit}: puncak {iv.peak > 0 ? "+" : ""}
                        {fmt(iv.peak)} {modeUnit} ({iv.peak > 0 ? "kanan" : "kiri"})
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
            <section className="card">
              <h3>Ringkasan metrik sumur ini</h3>
              {p.has_actual ? (
                <table>
                  <thead>
                    <tr>
                      <th>Operasi</th>
                      <th className="num">RMSE WP</th>
                      <th className="num">RMSE ML</th>
                      <th className="num">MAPE WP</th>
                      <th className="num">MAPE ML</th>
                      <th className="num">R² WP</th>
                      <th className="num">R² ML</th>
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
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Belum ada data aktual untuk sumur ini, metrik belum bisa dihitung.</p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
