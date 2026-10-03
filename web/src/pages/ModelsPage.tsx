import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type * as Plotly from "plotly.js";
import { api, BlindSet, DatasetItem, fmt, GroupRow, ModelItem, Op, OP_LABEL, OPS } from "../api";
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
const STATUS_CLS: Record<string, string> = { selesai: "ok", gagal: "bad", ditahan: "warn", antri: "warn", berjalan: "warn" };

function Improvement({ wp, ml }: { wp: number | null; ml: number | null }) {
  if (wp === null || ml === null || !wp) return <>–</>;
  const pct = ((wp - ml) / wp) * 100;
  return (
    <span className={pct >= 0 ? "pos" : "neg"}>
      {pct >= 0 ? "▲ " : "▼ "}
      {fmt(Math.abs(pct), 1)}% {pct >= 0 ? "lebih baik" : "lebih buruk"}
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
          {cols.includes("well_type") && <th>Tipe</th>}
          <th className="num">Sumur</th>
          <th className="num">Titik</th>
          <th className="num">RMSE WellPlan</th>
          <th className="num">RMSE ML</th>
          <th className="num">MAPE WellPlan</th>
          <th className="num">MAPE ML</th>
          <th className="num">ML lebih dekat</th>
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
            <td className="small">{g.warning ? "⚠ data sedikit (< 3 sumur)" : ""}</td>
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
  | "explain";

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
        <h2>Laporan evaluasi model #{id}</h2>
        <div className="row gap wrap">
          <a className="btn" href={`/api/models/${id}/report.xlsx`}>
            Laporan (.xlsx)
          </a>
          <a className="btn primary" href={`/api/models/${id}/report.pdf`}>
            Ringkasan PDF
          </a>
        </div>
      </div>
      <p className="muted small">
        Dataset v{m.dataset?.version} (hash {m.dataset?.hash?.slice(0, 12)}) · {m.dataset?.wells_train} sumur latih,{" "}
        {m.dataset?.rows_train} titik · {m.dataset?.wells_blind} sumur blind test disisihkan. Validasi silang per kelompok sumur
        (GroupKFold 5): sumur yang dinilai tidak pernah ada di data latih fold itu. RMSE dalam SI. Rasio RMSE ML/WellPlan rata-rata:{" "}
        <b>{fmt(m.skill, 3)}</b> (&lt; 1 = ML lebih baik).
      </p>
      {q.data.comparison?.decision && <div className={`alert ${q.data.status === "ditahan" ? "warn" : ""}`}>{q.data.comparison.decision}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Operasi</th>
              <th>Model terpilih</th>
              <th className="num">Sumur</th>
              <th className="num">RMSE WellPlan</th>
              <th className="num">RMSE ML</th>
              <th>ML vs WellPlan</th>
              <th className="num">ML lebih dekat</th>
              <th className="num">R² ML</th>
              <th className="num">Blind: RMSE WP → ML</th>
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
                  <td className="num">{b ? `${fmt(b.wellplan.rmse)} → ${fmt(b.ml.rmse)}` : "–"}</td>
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
            dijalankan {new Date(br.run_at).toLocaleString("id-ID")} pada {br.wells.length} sumur: {br.wells.join(", ")}. Hasil
            dicatat apa adanya dan tidak bisa diulang untuk model ini.
          </span>
        ) : (
          <>
            <span className="small muted">
              Sumur blind test dikunci sejak dataset pertama dibekukan dan tidak dipakai untuk tuning. Jalankan <b>sekali</b>, setelah
              model final dipilih.
            </span>{" "}
            <button
              className="btn small"
              disabled={blind.isPending}
              onClick={() => confirm("Blind test hanya bisa dijalankan sekali untuk model ini. Lanjutkan?") && blind.mutate()}
            >
              {blind.isPending ? "Menjalankan…" : "Jalankan blind test"}
            </button>
          </>
        )}
      </div>

      {m.feature_selection && (
        <details>
          <summary>Uji manfaat fitur ({m.feature_selection.filter((r) => r.dipakai).length} grup dipakai)</summary>
          <table>
            <thead>
              <tr>
                <th>Grup fitur</th>
                <th className="num">Skor (RMSE ML/WP)</th>
                <th>Dipakai</th>
                <th>Keterangan</th>
              </tr>
            </thead>
            <tbody>
              {m.feature_selection.map((r) => (
                <tr key={r.grup}>
                  <td>{r.grup}</td>
                  <td className="num">{fmt(r.skor, 4)}</td>
                  <td>{r.dipakai ? "ya" : "tidak"}</td>
                  <td className="small">{r.keterangan}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">Grup dipertahankan hanya bila skor validasi silang turun ≥ 1% (fitur tanpa bukti manfaat tidak dipakai).</p>
        </details>
      )}

      <div className="row gap wrap" style={{ marginTop: 16 }}>
        <label className="inline">
          Operasi
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
              ["by_section_type", "Section × tipe"],
              ["by_section", "Section"],
              ["by_type", "Tipe"],
              ["by_depth", "Kedalaman"],
              ["per_well", "Per sumur"],
              ["worst", "Titik terburuk"],
              ["candidates", "Algoritma"],
              ["strategy", "Tunggal vs kombinasi"],
              ["learning", "Kurva belajar"],
              ["explain", "SHAP"],
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
                  <th className="num">Dari (m)</th>
                  <th className="num">Sampai (m)</th>
                  <th className="num">Titik</th>
                  <th className="num">RMSE WellPlan</th>
                  <th className="num">RMSE ML</th>
                  <th className="num">ML lebih dekat</th>
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
                  <th>Sumur</th>
                  <th>Section</th>
                  <th>Tipe</th>
                  <th className="num">Titik</th>
                  <th className="num">RMSE WellPlan</th>
                  <th className="num">RMSE ML</th>
                  <th>ML vs WellPlan</th>
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
                  <th>Sumur</th>
                  <th>Section</th>
                  <th className="num">Kedalaman (m)</th>
                  <th className="num">Aktual</th>
                  <th className="num">WellPlan</th>
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
              <p className="small muted">RMSE validasi silang terbaik tiap algoritma (dari beberapa setelan × target langsung/selisih).</p>
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
                      text: "WellPlan",
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
                    <th>Kandidat</th>
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
                        <td>{k === om.chosen ? "dipilih" : ""}</td>
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
                  <th>Section | tipe</th>
                  <th className="num">Sumur</th>
                  <th className="num">RMSE model tunggal</th>
                  <th className="num">RMSE model kombinasi</th>
                  <th>Dipakai</th>
                </tr>
              </thead>
              <tbody>
                {(om.strategy ?? []).map((s) => (
                  <tr key={s.combo}>
                    <td>{s.combo.replace("|", '" · ')}</td>
                    <td className="num">{s.n_wells}</td>
                    <td className="num">{fmt(s.rmse_single)}</td>
                    <td className="num">{fmt(s.rmse_combo)}</td>
                    <td>{s.dipakai}</td>
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
                    name: "WellPlan",
                    line: { color: COLOR.wellplan, dash: "dash", width: 2 },
                  },
                ]}
                layout={{
                  xaxis: { title: { text: "Jumlah sumur latih" }, type: "category", gridcolor: COLOR.grid },
                  yaxis: { title: { text: `RMSE (${UNIT[op]})` }, gridcolor: COLOR.grid },
                }}
              />
              <p className="small muted">
                Kurva yang masih turun di ujung kanan berarti menambah sumur masih membantu; bila mendatar, keterbatasan ada di data
                atau fitur.
              </p>
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
          <summary>Catatan dataset ({m.notes.length})</summary>
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
        <h2>Dataset (versi beku)</h2>
        <button className="btn" onClick={() => freeze.mutate()} disabled={freeze.isPending}>
          {freeze.isPending ? "Membekukan…" : "Bekukan dataset baru"}
        </button>
      </div>
      <p className="muted small">
        Membekukan = menyimpan salinan dataset dari semua sumur berstatus kualitas A/B beserta hash isinya. Setiap model mencatat versi
        dataset yang dipakai sehingga hasilnya bisa diulang. Dataset pertama juga mengunci ~20% sumur sebagai blind test (proporsional
        per tipe).
      </p>
      {blind.data && (
        <p className="small">
          <b>Blind test terkunci</b> ({blind.data.note}): {blind.data.wells.join(", ")}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Versi</th>
              <th>Dibuat</th>
              <th className="num">Sumur-section</th>
              <th className="num">Blind</th>
              <th className="num">Dikecualikan</th>
              <th className="num">Baris</th>
              <th>Hash</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.id}>
                <td>v{d.version}</td>
                <td className="small">{new Date(d.created_at).toLocaleString("id-ID")}</td>
                <td className="num">{d.n_wells}</td>
                <td className="num">{d.n_blind}</td>
                <td className="num">{d.n_excluded}</td>
                <td className="num">{d.n_rows.toLocaleString("id-ID")}</td>
                <td className="small mono">{d.hash.slice(0, 12)}</td>
                <td>
                  <a className="btn small ghost" href={`/api/datasets/${d.id}/download.csv.gz`}>
                    Unduh
                  </a>
                </td>
              </tr>
            ))}
            {!list.length && (
              <tr>
                <td colSpan={8} className="muted">
                  Belum ada. Dataset dibekukan otomatis saat pelatihan pertama.
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
  const [algo, setAlgo] = useState("semua");
  const [mlp, setMlp] = useState(false);
  const [datasetId, setDatasetId] = useState("");
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => api.get<DatasetItem[]>("/api/datasets") });
  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => api.get<ModelItem[]>("/api/models"),
    refetchInterval: (q) => ((q.state.data ?? []).some((m) => m.status === "antri" || m.status === "berjalan") ? 3000 : false),
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
  const running = list.some((m) => m.status === "antri" || m.status === "berjalan");
  const [selected, setSelected] = useState<number | null>(null);
  const shown = selected ?? list.find((m) => m.active)?.id ?? list.find((m) => m.status === "selesai")?.id ?? null;

  return (
    <div className="page">
      <section className="card">
        <h2>Latih model</h2>
        <p className="muted small">
          Satu model per operasi dari dataset beku (sumur blind test disisihkan). Kandidat: Ridge, XGBoost, Random Forest, SVR (+ MLP
          opsional), target langsung atau selisih terhadap WellPlan, dinilai dengan validasi silang per kelompok sumur. Model baru
          dibandingkan dengan model aktif: bila lebih buruk, model <b>ditahan</b> (tidak diaktifkan otomatis). Proses ±3–5 menit.
        </p>
        <div className="row gap wrap">
          <label className="inline">
            Dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">terbaru (dibekukan otomatis bila belum ada)</option>
              {(datasets.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  v{d.version} · {d.n_wells} sumur-section
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Algoritma
            <select value={algo} onChange={(e) => setAlgo(e.target.value)}>
              <option value="semua">Bandingkan semua (terbaik per operasi)</option>
              <option value="xgboost">XGBoost saja</option>
              <option value="random_forest">Random Forest saja</option>
              <option value="ridge">Ridge saja</option>
              <option value="svr">SVR saja</option>
              <option value="mlp">MLP saja</option>
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={mlp} onChange={(e) => setMlp(e.target.checked)} disabled={algo !== "semua"} />
            Sertakan MLP (lebih lama)
          </label>
          <button className="btn primary" onClick={() => train.mutate()} disabled={running || train.isPending}>
            {running ? "Sedang melatih…" : "Latih model"}
          </button>
          <a className="btn ghost" href="/api/models/dataset.csv">
            Unduh dataset live (CSV)
          </a>
        </div>
      </section>

      <DatasetPanel />

      <section className="card">
        <h2>Riwayat model</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Dataset</th>
                <th>Algoritma</th>
                <th>Status</th>
                <th className="num">Rasio ML/WP</th>
                <th>Blind test</th>
                <th>Dibuat</th>
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
                    <span className={`badge ${STATUS_CLS[m.status] ?? ""}`}>{m.status}</span> {m.active && <span className="badge ok">aktif</span>}
                    {m.message && <div className="small bad-text">{m.message}</div>}
                    {m.status === "ditahan" && <div className="small">{m.comparison?.decision}</div>}
                  </td>
                  <td className="num">{fmt(m.skill, 3)}</td>
                  <td>{m.blind_done ? "sudah" : "–"}</td>
                  <td className="small">{new Date(m.created_at).toLocaleString("id-ID")}</td>
                  <td className="nowrap">
                    {(m.status === "selesai" || m.status === "ditahan") && (
                      <>
                        <button className="btn small" onClick={() => setSelected(m.id)}>
                          Laporan
                        </button>{" "}
                        {!m.active && (
                          <button
                            className="btn small ghost"
                            onClick={() =>
                              (m.status !== "ditahan" || confirm("Model ini lebih buruk dari model aktif. Tetap aktifkan?")) &&
                              activate.mutate(m.id)
                            }
                          >
                            Aktifkan
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
                    Belum ada model.
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
