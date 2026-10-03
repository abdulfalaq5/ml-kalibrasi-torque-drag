import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, EvaluationItem, fmt, Op, OP_LABEL, OPS } from "../api";

export default function EvaluationsPage() {
  const q = useQuery({ queryKey: ["evaluations"], queryFn: () => api.get<EvaluationItem[]>("/api/evaluations") });
  const list = q.data ?? [];
  return (
    <div className="page">
      <section className="card">
        <h2>Evaluasi prediksi vs aktual</h2>
        <p className="muted small">
          Untuk sumur baru: prediksi dibuat dari file WellPlan sebelum data aktual ada. Saat file berisi data aktual sumur itu
          diimpor kemudian, sistem otomatis membandingkan prediksi yang tersimpan dengan aktual dan dengan WellPlan. "ML lebih dekat"
          = persen titik ketika prediksi ML lebih dekat ke aktual daripada WellPlan.
        </p>
        {!list.length && <p className="muted">Belum ada evaluasi. Alurnya: Prediksi sumur baru → impor data aktualnya → hasil muncul di sini.</p>}
        {list.map((e) => (
          <div key={e.id} className="eval-card">
            <div className="row space wrap">
              <b>
                <Link to={`/dashboard/${e.well_id}`}>
                  {e.well} · {e.section_in}"
                </Link>
              </b>
              <span className="muted small">
                model #{e.model_id} · diprediksi {new Date(e.predicted_at).toLocaleString("id-ID")} · dievaluasi{" "}
                {new Date(e.evaluated_at).toLocaleString("id-ID")}
              </span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Operasi</th>
                  <th className="num">Titik</th>
                  <th className="num">RMSE WellPlan (SI)</th>
                  <th className="num">RMSE ML (SI)</th>
                  <th className="num">MAPE WellPlan</th>
                  <th className="num">MAPE ML</th>
                  <th className="num">ML lebih dekat</th>
                </tr>
              </thead>
              <tbody>
                {OPS.filter((o) => e.metrics.operations[o]).map((o: Op) => {
                  const m = e.metrics.operations[o];
                  return (
                    <tr key={o}>
                      <td>{OP_LABEL[o]}</td>
                      <td className="num">{m.ml.n}</td>
                      <td className="num">{fmt(m.wellplan?.rmse)}</td>
                      <td className="num">{fmt(m.ml.rmse)}</td>
                      <td className="num">{fmt(m.wellplan?.mape, 1)}%</td>
                      <td className="num">{fmt(m.ml.mape, 1)}%</td>
                      <td className="num">{m.ml_better_frac == null ? "–" : `${Math.round(m.ml_better_frac * 100)}%`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </div>
  );
}
