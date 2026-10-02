import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmt, GroupRow, ModelItem, Op, OP_LABEL, OPS } from "../api";

const UNIT: Record<Op, string> = {
  pick_up: "kN",
  slack_off: "kN",
  rotating_weight: "kN",
  torque_off_bottom: "kN·m",
  torque_on_bottom: "kN·m",
};

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
          <th className="num">R² WellPlan</th>
          <th className="num">R² ML</th>
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
            <td className="num">{fmt(g.wellplan.r2)}</td>
            <td className="num">{fmt(g.ml.r2)}</td>
            <td className="small">{g.warning ? "⚠ data sedikit (< 3 sumur)" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ModelDetail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["model", id], queryFn: () => api.get<ModelItem>(`/api/models/${id}`) });
  const [op, setOp] = useState<Op>("pick_up");
  const [view, setView] = useState<"by_section" | "by_type" | "by_section_type" | "per_well" | "candidates">(
    "by_section_type",
  );
  const m = q.data?.metrics;
  if (!m) return null;
  const om = m.operations[op];
  return (
    <section className="card">
      <div className="row space">
        <h2>Laporan evaluasi model #{id}</h2>
        <a className="btn" href={`/api/models/${id}/report.xlsx`}>
          Unduh laporan (.xlsx)
        </a>
      </div>
      <p className="muted small">
        Validasi leave-one-well-out: setiap sumur dinilai oleh model yang tidak pernah melihat sumur itu. RMSE dalam satuan SI
        (kN untuk hookload, kN·m untuk torsi). MAPE memakai penyebut minimal 5% dari median nilai aktual.
        {m.dataset && ` Dataset: ${m.dataset.rows} titik dari ${m.dataset.wells} sumur.`}
      </p>
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
              <th className="num">MAPE WellPlan</th>
              <th className="num">MAPE ML</th>
              <th className="num">R² ML</th>
            </tr>
          </thead>
          <tbody>
            {OPS.filter((o) => m.operations[o]).map((o) => {
              const d = m.operations[o];
              return (
                <tr key={o}>
                  <td>{OP_LABEL[o]}</td>
                  <td className="small">{d.chosen}</td>
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
                  <td className="num">{fmt(d.overall.wellplan.mape, 1)}%</td>
                  <td className="num">{fmt(d.overall.ml.mape, 1)}%</td>
                  <td className="num">{fmt(d.overall.ml.r2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

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
        <div className="seg">
          {(
            [
              ["by_section_type", "Section × tipe"],
              ["by_section", "Per section"],
              ["by_type", "Per tipe"],
              ["per_well", "Per sumur"],
              ["candidates", "Kandidat"],
            ] as const
          ).map(([k, l]) => (
            <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>
              {l}
            </button>
          ))}
        </div>
      </div>
      {om && (
        <div className="table-wrap">
          {view === "by_section_type" && <GroupTable rows={om.by_section_type} cols={["section", "well_type"]} />}
          {view === "by_section" && <GroupTable rows={om.by_section} cols={["section"]} />}
          {view === "by_type" && <GroupTable rows={om.by_type} cols={["well_type"]} />}
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
                {om.per_well.map((w) => (
                  <tr key={w.well_name}>
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
          {view === "candidates" && (
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
                {Object.entries(om.candidates).map(([k, s]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td className="num">{fmt(s.rmse)}</td>
                    <td className="num">{fmt(s.mape, 1)}%</td>
                    <td className="num">{fmt(s.r2)}</td>
                    <td>{k === om.chosen ? "dipilih" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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

export default function ModelsPage() {
  const qc = useQueryClient();
  const [algo, setAlgo] = useState("terbaik");
  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => api.get<ModelItem[]>("/api/models"),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((m) => m.status === "antri" || m.status === "berjalan") ? 2000 : false,
  });
  const train = useMutation({
    mutationFn: () => api.post<ModelItem>(`/api/models/train?algorithm=${algo}`),
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
  const shown = selected ?? list.find((m) => m.active)?.id ?? null;

  return (
    <div className="page">
      <section className="card">
        <h2>Latih model</h2>
        <p className="muted small">
          Melatih satu model per operasi dari semua sumur yang punya data aktual, memvalidasi per sumur, lalu menyimpan
          prediksi out-of-fold untuk dashboard. Model baru otomatis menjadi model aktif.
        </p>
        <div className="row gap wrap">
          <label className="inline">
            Algoritma
            <select value={algo} onChange={(e) => setAlgo(e.target.value)}>
              <option value="terbaik">Terbaik per operasi (Ridge / XGBoost)</option>
              <option value="xgboost">XGBoost saja</option>
              <option value="ridge">Ridge saja</option>
            </select>
          </label>
          <button className="btn primary" onClick={() => train.mutate()} disabled={running || train.isPending}>
            {running ? "Sedang melatih…" : "Latih model"}
          </button>
          <a className="btn ghost" href="/api/models/dataset.csv">
            Unduh dataset (CSV, SI)
          </a>
        </div>
      </section>

      <section className="card">
        <h2>Riwayat model</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Algoritma</th>
                <th>Status</th>
                <th>Dibuat</th>
                <th>Ringkasan RMSE (WellPlan → ML)</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((m) => (
                <tr key={m.id} className={m.id === shown ? "row-sel" : ""}>
                  <td>{m.id}</td>
                  <td>{m.algorithm}</td>
                  <td>
                    <span className={`badge ${m.status === "selesai" ? "ok" : m.status === "gagal" ? "bad" : "warn"}`}>
                      {m.status}
                    </span>{" "}
                    {m.active && <span className="badge ok">aktif</span>}
                    {m.message && <div className="small bad-text">{m.message}</div>}
                  </td>
                  <td className="small">{new Date(m.created_at).toLocaleString("id-ID")}</td>
                  <td className="small">
                    {m.summary &&
                      OPS.filter((o) => m.summary![o]).map((o) => (
                        <div key={o}>
                          {OP_LABEL[o]}: {fmt(m.summary![o].wellplan_rmse)} → {fmt(m.summary![o].ml_rmse)}
                        </div>
                      ))}
                  </td>
                  <td className="nowrap">
                    {m.status === "selesai" && (
                      <>
                        <button className="btn small" onClick={() => setSelected(m.id)}>
                          Laporan
                        </button>{" "}
                        {!m.active && (
                          <button className="btn small ghost" onClick={() => activate.mutate(m.id)}>
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
                  <td colSpan={6} className="muted">
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
