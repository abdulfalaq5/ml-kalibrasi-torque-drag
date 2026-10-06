import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type * as Plotly from "plotly.js";
import { api, BlindSet, DatasetItem, fmt, fmtDate, GroupRow, MODEL_STATUS_LABEL, ModelItem, Op, OP_LABEL, OPS, statusTone } from "../api";
import PlotlyChart from "../components/PlotlyChart";
import { COLOR } from "../components/chartTheme";

const UNIT: Record<Op, string> = {
  pick_up: "kN",
  slack_off: "kN",
  rotating_weight: "kN",
  torque_off_bottom: "kN·m",
  torque_on_bottom: "kN·m",
};
const ALGO_NAME: Record<string, string> = { ridge: "Ridge", xgboost: "XGBoost", random: "Random Forest", svr: "SVR", mlp: "MLP" };
const GROUP_LABEL: Record<string, string> = {
  base: "Base features",
  survey: "Survey (inclination, dogleg)",
  casing_shoe: "Casing shoe / open hole",
  bha_mud: "BHA & mud weight",
  kop_interval: "KOP & interval type",
  block_weight: "Block weight",
  calibration: "DD Calibrate offset",
};

function Improvement({ wp, ml }: { wp: number | null; ml: number | null }) {
  if (wp === null || ml === null || !wp) return <>–</>;
  const pct = ((wp - ml) / wp) * 100;
  return (
    <span className={pct >= 0 ? "pos" : "neg"}>
      {pct >= 0 ? "▲ " : "▼ "}
      {fmt(Math.abs(pct), 1)}% {pct >= 0 ? "better" : "worse"}
    </span>
  );
}

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function GroupTable({ rows, cols }: { rows: GroupRow[]; cols: ("section" | "well_type")[] }) {
  return (
    <table>
      <thead>
        <tr>
          {cols.includes("section") && <th>Section</th>}
          {cols.includes("well_type") && <th>Type</th>}
          <th className="num">Wells</th>
          <th className="num">Points</th>
          <th className="num">RMSE T&amp;D Model</th>
          <th className="num">RMSE ML</th>
          <th className="num">MAPE T&amp;D Model</th>
          <th className="num">MAPE ML</th>
          <th className="num">ML closer</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((g, i) => (
          <tr key={i} className={g.warning ? "row-warn" : ""}>
            {cols.includes("section") && <td>{g.section}"</td>}
            {cols.includes("well_type") && <td>{g.well_type}</td>}
            <td className="num">{g.n_wells}</td>
            <td className="num">{g.ml.n}</td>
            <td className="num">{fmt(g.wellplan.rmse)}</td>
            <td className="num">{fmt(g.ml.rmse)}</td>
            <td className="num">{fmt(g.wellplan.mape, 1)}%</td>
            <td className="num">{fmt(g.ml.mape, 1)}%</td>
            <td className="num">{pct((g as GroupRow & { ml_better_frac?: number }).ml_better_frac)}</td>
            <td className="small">{g.warning ? "⚠ limited data (< 3 wells)" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SmallChart({ data, layout }: { data: Plotly.Data[]; layout: Partial<Plotly.Layout> }) {
  const l = useMemo(
    () => ({
      height: 260,
      margin: { l: 50, r: 10, t: 30, b: 40 },
      paper_bgcolor: COLOR.surface,
      plot_bgcolor: COLOR.surface,
      font: { family: "inherit", size: 11, color: COLOR.text },
      xaxis: { gridcolor: COLOR.grid },
      yaxis: { gridcolor: COLOR.grid },
      legend: { orientation: "h" as const, y: -0.25 },
      ...layout,
    }),
    [layout],
  );
  return <PlotlyChart data={data} layout={l} config={{ displaylogo: false, responsive: true }} />;
}

type View =
  | "by_section_type"
  | "by_section"
  | "by_type"
  | "by_depth"
  | "per_well"
  | "worst"
  | "candidates"
  | "strategy"
  | "learning"
  | "explain"
  | "backtest";

function ModelDetail({ id }: { id: number }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["model", id], queryFn: () => api.get<ModelItem>(`/api/models/${id}`) });
  const [op, setOp] = useState<Op>("pick_up");
  const [view, setView] = useState<View>("by_section_type");
  const blind = useMutation({
    mutationFn: () => api.post(`/api/models/${id}/blind-test`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model", id] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (e) => alert((e as Error).message),
  });
  const m = q.data?.metrics;
  if (!m || !q.data) return null;
  const om = m.operations[op];
  const br = q.data.blind_result;
  return (
    <section className="card">
      <div className="row space wrap">
        <h2>Model evaluation report #{id}</h2>
        <div className="row gap wrap">
          <a className="btn" href={`/api/models/${id}/report.xlsx`}>
            Report (.xlsx)
          </a>
          <a className="btn primary" href={`/api/models/${id}/report.pdf`}>
            PDF summary
          </a>
        </div>
      </div>
      <p className="muted small">
        Dataset v{m.dataset?.version} (hash {m.dataset?.hash?.slice(0, 12)}) · {m.dataset?.wells_train} training wells,{" "}
        {m.dataset?.rows_train} points · {m.dataset?.wells_blind} blind test wells set aside. Cross-validation grouped by well
        (GroupKFold 5): a well being scored is never in that fold's training data. RMSE in SI. Mean RMSE ML/T&amp;D Model ratio:{" "}
        <b>{fmt(m.skill, 3)}</b> (&lt; 1 = ML is better). <b>Inside P10–P90 band</b>: share of actual readings inside
        the ML uncertainty band; the target is 80% (exactly 80% on cross-validation by construction, the blind-test
        value shows how well it holds on unseen wells).
      </p>
      {q.data.comparison?.decision && <div className={`alert ${q.data.status === "held" ? "warn" : ""}`}>{q.data.comparison.decision}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Operation</th>
              <th>Selected model</th>
              <th className="num">Wells</th>
              <th className="num">RMSE T&amp;D Model</th>
              <th className="num">RMSE ML</th>
              <th>ML vs T&amp;D Model</th>
              <th className="num">ML closer</th>
              <th className="num">R² ML</th>
              <th className="num" title="Share of actual points with |error| < 10 klbf (hookload) / < 2 kft-lbf (torque)">
                Within tolerance T&amp;D → ML
              </th>
              <th className="num">Blind: RMSE WP → ML</th>
              <th className="num">Blind within tolerance</th>
              <th
                className="num"
                title="Share of actual readings inside the ML uncertainty band (P10–P90). Design target 80%: cross-validation is 80% by construction; the blind-test wells show how well the band holds on wells the model never saw."
              >
                Inside P10–P90 band (CV / blind)
              </th>
            </tr>
          </thead>
          <tbody>
            {OPS.filter((o) => m.operations[o]).map((o) => {
              const d = m.operations[o];
              const b = br?.operations[o];
              return (
                <tr key={o}>
                  <td>{OP_LABEL[o]}</td>
                  <td className="small">{d.chosen_label ?? d.chosen}</td>
                  <td className="num">{d.overall.n_wells}</td>
                  <td className="num">
                    {fmt(d.overall.wellplan.rmse)} {UNIT[o]}
                  </td>
                  <td className="num">
                    {fmt(d.overall.ml.rmse)} {UNIT[o]}
                  </td>
                  <td>
                    <Improvement wp={d.overall.wellplan.rmse} ml={d.overall.ml.rmse} />
                  </td>
                  <td className="num">{pct(d.overall.ml_better_frac)}</td>
                  <td className="num">{fmt(d.overall.ml.r2)}</td>
                  <td className="num nowrap">
                    {pct(d.overall.within?.wellplan)} → <b>{pct(d.overall.within?.ml)}</b>
                  </td>
                  <td className="num">{b ? `${fmt(b.wellplan.rmse)} → ${fmt(b.ml.rmse)}` : "–"}</td>
                  <td className="num nowrap">{b?.within ? `${pct(b.within.wellplan)} → ${pct(b.within.ml)}` : "–"}</td>
                  <td className="num nowrap">
                    {pct(d.overall.band_coverage)} / <b>{pct(b?.band_coverage)}</b>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="blind-box">
        <b>Blind test</b>{" "}
        {br ? (
          <span className="small">
            run {fmtDate(br.run_at)} on {br.wells.length} wells: {br.wells.join(", ")}. The result is recorded as is and
            cannot be repeated for this model.
          </span>
        ) : (
          <>
            <span className="small muted">
              Blind test wells were locked when the first dataset was frozen and are never used for tuning. Run it{" "}
              <b>once</b>, after the final model is chosen.
            </span>{" "}
            <button
              className="btn small"
              disabled={blind.isPending}
              onClick={() => confirm("The blind test can run only once for this model. Continue?") && blind.mutate()}
            >
              {blind.isPending ? "Running…" : "Run blind test"}
            </button>
          </>
        )}
      </div>

      {m.feature_selection && (
        <details>
          <summary>Feature group tests ({m.feature_selection.filter((r) => r.used).length} groups used)</summary>
          <table>
            <thead>
              <tr>
                <th>Feature group</th>
                <th className="num">Score (RMSE ML/WP)</th>
                <th>Used</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {m.feature_selection.map((r) => (
                <tr key={r.group}>
                  <td>{GROUP_LABEL[r.group] ?? r.group}</td>
                  <td className="num">{fmt(r.score, 4)}</td>
                  <td>{r.used ? "yes" : "no"}</td>
                  <td className="small">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">A group is kept only if the cross-validation score improves by ≥ 1% (features without proven benefit are not used).</p>
        </details>
      )}

      <div className="row gap wrap" style={{ marginTop: 16 }}>
        <label className="inline">
          Operation
          <select value={op} onChange={(e) => setOp(e.target.value as Op)}>
            {OPS.filter((o) => m.operations[o]).map((o) => (
              <option key={o} value={o}>
                {OP_LABEL[o]}
              </option>
            ))}
          </select>
        </label>
        <div className="seg wrap-seg">
          {(
            [
              ["by_section_type", "Section × type"],
              ["by_section", "Section"],
              ["by_type", "Type"],
              ["by_depth", "Depth"],
              ["per_well", "By well"],
              ["worst", "Worst points"],
              ["candidates", "Algorithms"],
              ["strategy", "Single vs combination"],
              ["learning", "Learning curve"],
              ["explain", "SHAP"],
              ["backtest", "Prediction backtest"],
            ] as const
          ).map(([k, l]) => (
            <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>
              {l}
            </button>
          ))}
        </div>
      </div>
      {om && (
        <div className="table-wrap" style={{ marginTop: 8 }}>
          {view === "by_section_type" && <GroupTable rows={om.by_section_type} cols={["section", "well_type"]} />}
          {view === "by_section" && <GroupTable rows={om.by_section} cols={["section"]} />}
          {view === "by_type" && <GroupTable rows={om.by_type} cols={["well_type"]} />}
          {view === "by_depth" && (
            <table>
              <thead>
                <tr>
                  <th className="num">From (m)</th>
                  <th className="num">To (m)</th>
                  <th className="num">Points</th>
                  <th className="num">RMSE T&amp;D Model</th>
                  <th className="num">RMSE ML</th>
                  <th className="num">ML closer</th>
                </tr>
              </thead>
              <tbody>
                {(om.by_depth ?? []).map((g, i) => (
                  <tr key={i}>
                    <td className="num">{fmt(g.depth_from_m, 0)}</td>
                    <td className="num">{fmt(g.depth_to_m, 0)}</td>
                    <td className="num">{g.ml.n}</td>
                    <td className="num">{fmt(g.wellplan.rmse)}</td>
                    <td className="num">{fmt(g.ml.rmse)}</td>
                    <td className="num">{pct(g.ml_better_frac)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {view === "per_well" && (
            <table>
              <thead>
                <tr>
                  <th>Well</th>
                  <th>Section</th>
                  <th>Type</th>
                  <th className="num">Points</th>
                  <th className="num">RMSE T&amp;D Model</th>
                  <th className="num">RMSE ML</th>
                  <th>ML vs T&amp;D Model</th>
                </tr>
              </thead>
              <tbody>
                {om.per_well.map((w, i) => (
                  <tr key={i}>
                    <td>{w.well_name}</td>
                    <td>{w.section}"</td>
                    <td>{w.well_type}</td>
                    <td className="num">{w.ml.n}</td>
                    <td className="num">{fmt(w.wellplan.rmse)}</td>
                    <td className="num">{fmt(w.ml.rmse)}</td>
                    <td>
                      <Improvement wp={w.wellplan.rmse} ml={w.ml.rmse} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {view === "worst" && (
            <table>
              <thead>
                <tr>
                  <th>Well</th>
                  <th>Section</th>
                  <th className="num">Depth (m)</th>
                  <th className="num">Actual</th>
                  <th className="num">T&amp;D Model</th>
                  <th className="num">ML</th>
                </tr>
              </thead>
              <tbody>
                {(om.worst_points ?? []).map((p, i) => (
                  <tr key={i}>
                    <td>{p.well_name}</td>
                    <td>{p.section}"</td>
                    <td className="num">{fmt(p.depth_m, 0)}</td>
                    <td className="num">{fmt(p.actual)}</td>
                    <td className="num">{fmt(p.wellplan)}</td>
                    <td className="num">{fmt(p.ml)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {view === "candidates" && (
            <>
              <p className="small muted">Best cross-validation RMSE per algorithm (over several settings × direct/residual target).</p>
              <SmallChart
                data={[
                  {
                    type: "bar",
                    orientation: "h",
                    y: Object.keys(om.algo_best ?? {}).map((k) => ALGO_NAME[k] ?? k),
                    x: Object.values(om.algo_best ?? {}).map((v) => v.rmse ?? 0),
                    marker: { color: COLOR.ml },
                    name: "RMSE ML",
                    hovertemplate: "%{y}: %{x:.2f}<extra></extra>",
                  },
                ]}
                layout={{
                  shapes: [
                    {
                      type: "line",
                      x0: om.overall.wellplan.rmse ?? 0,
                      x1: om.overall.wellplan.rmse ?? 0,
                      yref: "paper",
                      y0: 0,
                      y1: 1,
                      line: { color: COLOR.wellplan, dash: "dash", width: 2 },
                    },
                  ],
                  annotations: [
                    {
                      x: om.overall.wellplan.rmse ?? 0,
                      yref: "paper",
                      y: 1.08,
                      text: "T&D Model",
                      showarrow: false,
                      font: { color: COLOR.wellplan, size: 11 },
                    },
                  ],
                  xaxis: { title: { text: `RMSE (${UNIT[op]})` }, gridcolor: COLOR.grid },
                  margin: { l: 110, r: 20, t: 30, b: 45 },
                }}
              />
              <table>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th className="num">RMSE</th>
                    <th className="num">MAPE</th>
                    <th className="num">R²</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(om.candidates)
                    .sort((a, b) => (a[1].rmse ?? 0) - (b[1].rmse ?? 0))
                    .map(([k, s]) => (
                      <tr key={k} className={k === om.chosen ? "row-sel" : ""}>
                        <td>{k}</td>
                        <td className="num">{fmt(s.rmse)}</td>
                        <td className="num">{fmt(s.mape, 1)}%</td>
                        <td className="num">{fmt(s.r2)}</td>
                        <td>{k === om.chosen ? "selected" : ""}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </>
          )}
          {view === "strategy" && (
            <table>
              <thead>
                <tr>
                  <th>Section | type</th>
                  <th className="num">Wells</th>
                  <th className="num">RMSE single model</th>
                  <th className="num">RMSE combination model</th>
                  <th>Used</th>
                </tr>
              </thead>
              <tbody>
                {(om.strategy ?? []).map((s) => (
                  <tr key={s.combo}>
                    <td>{s.combo.replace("|", '" · ')}</td>
                    <td className="num">{s.n_wells}</td>
                    <td className="num">{fmt(s.rmse_single)}</td>
                    <td className="num">{fmt(s.rmse_combo)}</td>
                    <td>{s.used}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {view === "learning" && (
            <>
              <SmallChart
                data={[
                  {
                    type: "scatter",
                    mode: "lines+markers",
                    x: (om.learning_curve ?? []).map((p) => p.label),
                    y: (om.learning_curve ?? []).map((p) => p.rmse_ml),
                    name: "ML",
                    line: { color: COLOR.ml, width: 2 },
                    marker: { size: 8 },
                  },
                  {
                    type: "scatter",
                    mode: "lines",
                    x: (om.learning_curve ?? []).map((p) => p.label),
                    y: (om.learning_curve ?? []).map((p) => p.rmse_wp),
                    name: "T&D Model",
                    line: { color: COLOR.wellplan, dash: "dash", width: 2 },
                  },
                ]}
                layout={{
                  xaxis: { title: { text: "Number of training wells" }, type: "category", gridcolor: COLOR.grid },
                  yaxis: { title: { text: `RMSE (${UNIT[op]})` }, gridcolor: COLOR.grid },
                }}
              />
              <p className="small muted">
                A curve still falling at the right end means more wells still help; when it is flat, the limit is in the data or
                the features.
              </p>
            </>
          )}
          {view === "backtest" && (
            <>
              <p className="small muted">
                Prediction N ft ahead from every actual depth on wells the model never saw. Share of actual points in the
                window within the client tolerance (&lt; 10 klbf hookload, &lt; 2 kft-lbf torque). "+ bias" = local bias
                correction from the last actual readings (the Prediction default when actual data exists).
              </p>
              {om.forecast_backtest ? (
                <table>
                  <thead>
                    <tr>
                      <th>Horizon</th>
                      {["T&D model", "T&D model + bias", "T&D + DD Calibrate", "ML", "ML + bias"].map((k) => (
                        <th key={k} className="num">
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(om.forecast_backtest.horizons).map(([h, rows]) => (
                      <tr key={h}>
                        <td>{Number(h).toLocaleString("en-US")} ft</td>
                        {["T&D model", "T&D model + bias", "T&D + DD Calibrate", "ML", "ML + bias"].map((k) => (
                          <td key={k} className="num">
                            {rows[k] ? (k === "ML + bias" ? <b>{pct(rows[k].within)}</b> : pct(rows[k].within)) : "–"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Not available for this model (trained before this report existed). Train a new model.</p>
              )}
            </>
          )}
          {view === "explain" && om.explain && (
            <>
              <SmallChart
                data={[
                  {
                    type: "bar",
                    orientation: "h",
                    y: om.explain.features.slice(0, 10).map((f) => f.feature).reverse(),
                    x: om.explain.features.slice(0, 10).map((f) => f.importance).reverse(),
                    marker: { color: COLOR.wellplan },
                    hovertemplate: "%{y}: %{x:.3f}<extra></extra>",
                  },
                ]}
                layout={{ height: 320, margin: { l: 140, r: 20, t: 20, b: 45 }, xaxis: { title: { text: om.explain.method } } }}
              />
              <div className={`alert ${om.explain.physics_ok ? "" : "warn"}`}>{om.explain.note}</div>
            </>
          )}
        </div>
      )}
      {m.notes.length > 0 && (
        <details>
          <summary>Dataset notes ({m.notes.length})</summary>
          <ul className="small">
            {m.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function DatasetPanel() {
  const qc = useQueryClient();
  const ds = useQuery({ queryKey: ["datasets"], queryFn: () => api.get<DatasetItem[]>("/api/datasets") });
  const blind = useQuery({ queryKey: ["blind"], queryFn: () => api.get<BlindSet>("/api/datasets/blind") });
  const freeze = useMutation({
    mutationFn: () => api.post<DatasetItem>("/api/datasets/freeze"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["blind"] });
    },
    onError: (e) => alert((e as Error).message),
  });
  const list = ds.data ?? [];
  return (
    <section className="card">
      <div className="row space wrap">
        <h2>Datasets (frozen versions)</h2>
        <button className="btn" onClick={() => freeze.mutate()} disabled={freeze.isPending}>
          {freeze.isPending ? "Freezing…" : "Freeze a new dataset"}
        </button>
      </div>
      <p className="muted small">
        Freezing = saving a copy of the dataset from all <b>Training Data</b> wells with data quality A/B, with a content hash.
        Monitoring wells are never included. Every model records the dataset version it used so the result can be reproduced.
        The first dataset also locks ~20% of the wells as the blind test (proportional per well type).
      </p>
      {blind.data && (
        <p className="small">
          <b>Blind test locked</b> ({blind.data.note}): {blind.data.wells.join(", ")}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Created</th>
              <th className="num">Well sections</th>
              <th className="num">Blind</th>
              <th className="num">Excluded</th>
              <th className="num">Rows</th>
              <th>Hash</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.id}>
                <td>v{d.version}</td>
                <td className="small">{fmtDate(d.created_at)}</td>
                <td className="num">{d.n_wells}</td>
                <td className="num">{d.n_blind}</td>
                <td className="num">{d.n_excluded}</td>
                <td className="num">{d.n_rows.toLocaleString("en-US")}</td>
                <td className="small mono">{d.hash.slice(0, 12)}</td>
                <td>
                  <a className="btn small ghost" href={`/api/datasets/${d.id}/download.csv.gz`}>
                    Download
                  </a>
                </td>
              </tr>
            ))}
            {!list.length && (
              <tr>
                <td colSpan={8} className="muted">
                  None yet. A dataset is frozen automatically at the first training run.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function ModelsPage() {
  const qc = useQueryClient();
  const [algo, setAlgo] = useState("all");
  const [mlp, setMlp] = useState(false);
  const [datasetId, setDatasetId] = useState("");
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => api.get<DatasetItem[]>("/api/datasets") });
  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => api.get<ModelItem[]>("/api/models"),
    refetchInterval: (q) => ((q.state.data ?? []).some((m) => m.status === "queued" || m.status === "running") ? 3000 : false),
  });
  const train = useMutation({
    mutationFn: () =>
      api.post<ModelItem>(`/api/models/train?algorithm=${algo}&include_mlp=${mlp}${datasetId ? `&dataset_id=${datasetId}` : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
    onError: (e) => alert((e as Error).message),
  });
  const activate = useMutation({
    mutationFn: (id: number) => api.post(`/api/models/${id}/activate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      qc.invalidateQueries({ queryKey: ["wells"] });
    },
  });
  const list = models.data ?? [];
  const running = list.some((m) => m.status === "queued" || m.status === "running");
  const [selected, setSelected] = useState<number | null>(null);
  const shown = selected ?? list.find((m) => m.active)?.id ?? list.find((m) => m.status === "done")?.id ?? null;

  return (
    <div className="page">
      <section className="card">
        <h2>Train a model</h2>
        <p className="muted small">
          One model per operation from a frozen dataset of <b>Training Data</b> (blind test wells set aside). Candidates: Ridge,
          XGBoost, Random Forest, SVR (+ optional MLP), with a direct target or a residual to WellPlan, scored with
          cross-validation grouped by well. A new model is compared with the active model: if it is worse it is <b>held</b>{" "}
          (not activated automatically). Takes about 3–5 minutes.
        </p>
        <div className="row gap wrap">
          <label className="inline">
            Dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">latest (frozen automatically if none)</option>
              {(datasets.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  v{d.version} · {d.n_wells} well sections
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Algorithm
            <select value={algo} onChange={(e) => setAlgo(e.target.value)}>
              <option value="all">Compare all (best per operation)</option>
              <option value="xgboost">XGBoost only</option>
              <option value="random_forest">Random Forest only</option>
              <option value="ridge">Ridge only</option>
              <option value="svr">SVR only</option>
              <option value="mlp">MLP only</option>
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={mlp} onChange={(e) => setMlp(e.target.checked)} disabled={algo !== "all"} />
            Include MLP (slower)
          </label>
          <button className="btn primary" onClick={() => train.mutate()} disabled={running || train.isPending}>
            {running ? "Training…" : "Train model"}
          </button>
          <a className="btn ghost" href="/api/models/dataset.csv">
            Download live dataset (CSV)
          </a>
        </div>
      </section>

      <DatasetPanel />

      <section className="card">
        <h2>Model history</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Dataset</th>
                <th>Algorithm</th>
                <th>Status</th>
                <th className="num">ML/WP ratio</th>
                <th>Blind test</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((m) => (
                <tr key={m.id} className={m.id === shown ? "row-sel" : ""}>
                  <td>{m.id}</td>
                  <td>{m.dataset_version ? `v${m.dataset_version}` : "–"}</td>
                  <td>{m.algorithm}</td>
                  <td>
                    <span className={`badge ${statusTone(m.status)}`}>{MODEL_STATUS_LABEL[m.status] ?? m.status}</span>{" "}
                    {m.active && <span className="badge ok">active</span>}
                    {m.message && <div className="small bad-text">{m.message}</div>}
                    {m.status === "held" && <div className="small">{m.comparison?.decision}</div>}
                  </td>
                  <td className="num">{fmt(m.skill, 3)}</td>
                  <td>{m.blind_done ? "done" : "–"}</td>
                  <td className="small">{fmtDate(m.created_at)}</td>
                  <td className="nowrap">
                    {(m.status === "done" || m.status === "held") && (
                      <>
                        <button className="btn small" onClick={() => setSelected(m.id)}>
                          Report
                        </button>{" "}
                        {!m.active && (
                          <button
                            className="btn small ghost"
                            onClick={() =>
                              (m.status !== "held" || confirm("This model is worse than the active model. Activate it anyway?")) &&
                              activate.mutate(m.id)
                            }
                          >
                            Activate
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {!list.length && (
                <tr>
                  <td colSpan={8} className="muted">
                    No models yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      {shown !== null && <ModelDetail id={shown} />}
    </div>
  );
}
