import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, EvaluationItem, fmt, fmtDate, Op, OP_LABEL, OPS } from "../api";

export default function EvaluationsPage() {
  const q = useQuery({ queryKey: ["evaluations"], queryFn: () => api.get<EvaluationItem[]>("/api/evaluations") });
  const list = q.data ?? [];
  return (
    <div className="page">
      <section className="card">
        <h2>Prediction vs actual evaluation</h2>
        <p className="muted small">
          For monitoring wells: the prediction is made from the WellPlan file before actual data exists. When a file with that
          well's actual data is uploaded later, the system automatically compares the stored prediction with the actual data and
          with the T&amp;D Model. "ML closer" = share of points where the ML prediction is closer to actual than the T&amp;D Model.
        </p>
        {!list.length && <p className="muted">No evaluations yet. Flow: predict a monitoring well → upload its actual data later → the result appears here.</p>}
        {list.map((e) => (
          <div key={e.id} className="eval-card">
            <div className="row space wrap">
              <b>
                <Link to={`/dashboard/${e.well_id}`}>
                  {e.well} · {e.section_in}"
                </Link>
              </b>
              <span className="muted small">
                model #{e.model_id} · predicted {fmtDate(e.predicted_at)} · evaluated {fmtDate(e.evaluated_at)}
              </span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th className="num">Points</th>
                  <th className="num">RMSE T&amp;D Model (SI)</th>
                  <th className="num">RMSE ML (SI)</th>
                  <th className="num">MAPE T&amp;D Model</th>
                  <th className="num">MAPE ML</th>
                  <th className="num">ML closer</th>
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
