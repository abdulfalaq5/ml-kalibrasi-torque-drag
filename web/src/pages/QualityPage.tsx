import { FormEvent, Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, fmt, fmtDate, PURPOSE_LABEL, Q_LABEL, QStatus, QualityRow, WellItem } from "../api";
import QualityBadge from "../components/QualityBadge";

const DECISIONS = [
  ["accept", "Accept (with a note)"],
  ["exclude", "Exclude from training"],
  ["fix", "Fix (request a new file)"],
] as const;

function ReviewForm({ row, onDone }: { row: QualityRow; onDone: () => void }) {
  const [decision, setDecision] = useState("accept");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/api/quality/${row.well_id}/review`, { decision, reason });
      onDone();
    } catch (x) {
      setErr((x as Error).message);
    }
  };
  return (
    <form className="review-form" onSubmit={submit}>
      <select value={decision} onChange={(e) => setDecision(e.target.value)}>
        {DECISIONS.map(([k, l]) => (
          <option key={k} value={k}>
            {l}
          </option>
        ))}
      </select>
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required, recorded)" required minLength={5} />
      <button className="btn small primary">Save decision</button>
      {err && <span className="bad-text small">{err}</span>}
    </form>
  );
}

export default function QualityPage() {
  const qc = useQueryClient();
  const rows = useQuery({ queryKey: ["quality"], queryFn: () => api.get<QualityRow[]>("/api/quality") });
  const wells = useQuery({ queryKey: ["wells"], queryFn: () => api.get<WellItem[]>("/api/wells") });
  const [filter, setFilter] = useState<"" | QStatus>("");
  const [purpose, setPurpose] = useState<"" | "training" | "monitoring">("training");
  const [open, setOpen] = useState<number | null>(null);
  const recompute = useMutation({
    mutationFn: () => api.post("/api/quality/recompute"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quality"] }),
  });
  const scoped = (rows.data ?? []).filter((r) => !purpose || r.purpose === purpose);
  const list = scoped.filter((r) => !filter || r.status === filter);
  const counts = scoped.reduce<Record<string, number>>((a, r) => ({ ...a, [r.status]: (a[r.status] ?? 0) + 1 }), {});
  const wellByKey = new Map((wells.data ?? []).map((w) => [w.id, w]));

  return (
    <div className="page">
      <section className="card">
        <div className="row space wrap">
          <h2>Data quality gate</h2>
          <div className="row gap">
            <button className="btn" onClick={() => recompute.mutate()} disabled={recompute.isPending}>
              {recompute.isPending ? "Recomputing…" : "Recompute"}
            </button>
            <a className="btn primary" href="/api/quality/report.xlsx">
              Download quality report (.xlsx)
            </a>
          </div>
        </div>
        <p className="muted small">
          Only <b>Training Data</b> well sections with status <b>A</b> or <b>B</b> are used for training. <b>C</b> failed a
          critical check (format, units, depth, physical values, order slack off ≤ rotating ≤ pick up, WellPlan–actual depth
          overlap, at least 8 actual points, section &amp; type, duplicate). <b>B</b> passed with statistical warnings. The
          engineer's review decision (accept / exclude / fix) is recorded with the reason, name and time. Monitoring wells are
          checked too, for information only.
        </p>
        <div className="row gap wrap small" style={{ marginBottom: 8 }}>
          <label className="inline">
            Data group
            <select value={purpose} onChange={(e) => setPurpose(e.target.value as typeof purpose)}>
              <option value="training">{PURPOSE_LABEL.training}</option>
              <option value="monitoring">{PURPOSE_LABEL.monitoring}</option>
              <option value="">All</option>
            </select>
          </label>
        </div>
        <div className="row gap wrap">
          {(["A", "B", "C", "X"] as QStatus[]).map((s) => (
            <button key={s} className={`stat-tile ${filter === s ? "on" : ""}`} onClick={() => setFilter(filter === s ? "" : s)}>
              <QualityBadge s={s} />
              <span className="stat-num">{counts[s] ?? 0}</span>
              <span className="muted small">{Q_LABEL[s]}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Well</th>
                <th>Group</th>
                <th>Section</th>
                <th>Type</th>
                <th>Status</th>
                <th className="num">Score</th>
                <th className="num">Actual points</th>
                <th className="num">PU actual/WP ratio</th>
                <th>Main reason</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => {
                const issues = r.checks.filter((c) => c.level !== "pass");
                return (
                  <Fragment key={r.well_id}>
                    <tr className="clickable" onClick={() => setOpen(open === r.well_id ? null : r.well_id)}>
                      <td>{r.well}</td>
                      <td className="small">{PURPOSE_LABEL[r.purpose]}</td>
                      <td>{r.section_in}"</td>
                      <td>{r.well_type ?? "?"}</td>
                      <td>
                        <QualityBadge s={r.status} long />
                        {r.auto_status && r.auto_status !== r.status && <span className="muted small"> (automatic {r.auto_status})</span>}
                      </td>
                      <td className="num">{r.score}</td>
                      <td className="num">{r.stats.n_actual_depths ?? 0}</td>
                      <td className="num">{fmt(r.stats.ratio_pick_up)}</td>
                      <td className="small">{issues[0]?.message ?? "–"}</td>
                      <td>
                        {wellByKey.get(r.well_id) && (
                          <Link className="btn small" to={`/dashboard/${r.well_id}`} onClick={(e) => e.stopPropagation()}>
                            Dashboard
                          </Link>
                        )}
                      </td>
                    </tr>
                    {open === r.well_id && (
                      <tr>
                        <td colSpan={10}>
                          <ul className="issues">
                            {r.checks.map((c, i) => (
                              <li key={i} className={c.level === "critical" ? "error" : c.level === "warning" ? "warning" : "pass"}>
                                <b>{c.code}</b> [{c.level}] {c.message}
                              </li>
                            ))}
                          </ul>
                          {r.reviews.length > 0 && (
                            <div className="small">
                              <b>Review history:</b>
                              <ul>
                                {r.reviews.map((v, i) => (
                                  <li key={i}>
                                    {fmtDate(v.created_at)} · {v.reviewer} · <b>{v.decision}</b>: {v.reason}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          <ReviewForm
                            row={r}
                            onDone={() => {
                              qc.invalidateQueries({ queryKey: ["quality"] });
                              qc.invalidateQueries({ queryKey: ["wells"] });
                            }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
