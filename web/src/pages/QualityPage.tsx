import { FormEvent, Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, fmt, Q_LABEL, QStatus, QualityRow, WellItem } from "../api";
import QualityBadge from "../components/QualityBadge";

const DECISIONS = [
  ["terima", "Terima (dengan catatan)"],
  ["kecualikan", "Kecualikan dari training"],
  ["perbaiki", "Perbaiki (minta file baru)"],
] as const;

function ReviewForm({ row, onDone }: { row: QualityRow; onDone: () => void }) {
  const [decision, setDecision] = useState("terima");
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
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Alasan (wajib, dicatat)" required minLength={5} />
      <button className="btn small primary">Simpan keputusan</button>
      {err && <span className="bad-text small">{err}</span>}
    </form>
  );
}

export default function QualityPage() {
  const qc = useQueryClient();
  const rows = useQuery({ queryKey: ["quality"], queryFn: () => api.get<QualityRow[]>("/api/quality") });
  const wells = useQuery({ queryKey: ["wells"], queryFn: () => api.get<WellItem[]>("/api/wells") });
  const [filter, setFilter] = useState<"" | QStatus>("");
  const [open, setOpen] = useState<number | null>(null);
  const recompute = useMutation({
    mutationFn: () => api.post("/api/quality/recompute"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quality"] }),
  });
  const list = (rows.data ?? []).filter((r) => !filter || r.status === filter);
  const counts = (rows.data ?? []).reduce<Record<string, number>>((a, r) => ({ ...a, [r.status]: (a[r.status] ?? 0) + 1 }), {});
  const wellByKey = new Map((wells.data ?? []).map((w) => [w.id, w]));

  return (
    <div className="page">
      <section className="card">
        <div className="row space wrap">
          <h2>Gerbang kualitas data</h2>
          <div className="row gap">
            <button className="btn" onClick={() => recompute.mutate()} disabled={recompute.isPending}>
              {recompute.isPending ? "Menghitung…" : "Hitung ulang"}
            </button>
            <a className="btn primary" href="/api/quality/report.xlsx">
              Unduh laporan kualitas (.xlsx)
            </a>
          </div>
        </div>
        <p className="muted small">
          Hanya sumur-section berstatus <b>A</b> dan <b>B</b> yang masuk training. <b>C</b> gagal pemeriksaan kritis (format, satuan,
          kedalaman, nilai fisik, urutan slack off ≤ rotating ≤ pick up, tumpang rentang WellPlan–aktual, minimal 8 titik aktual, section
          &amp; tipe, duplikat). <b>B</b> lolos tapi ada peringatan statistik. Keputusan tinjauan engineer (terima / kecualikan /
          perbaiki) dicatat beserta alasan, nama, dan waktu.
        </p>
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
                <th>Sumur</th>
                <th>Section</th>
                <th>Tipe</th>
                <th>Status</th>
                <th className="num">Skor</th>
                <th className="num">Titik aktual</th>
                <th className="num">Rasio PU akt/WP</th>
                <th>Alasan utama</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => {
                const issues = r.checks.filter((c) => c.level !== "lolos");
                return (
                  <Fragment key={r.well_id}>
                    <tr className="clickable" onClick={() => setOpen(open === r.well_id ? null : r.well_id)}>
                      <td>{r.well}</td>
                      <td>{r.section_in}"</td>
                      <td>{r.well_type ?? "?"}</td>
                      <td>
                        <QualityBadge s={r.status} long />
                        {r.auto_status && r.auto_status !== r.status && <span className="muted small"> (otomatis {r.auto_status})</span>}
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
                        <td colSpan={9}>
                          <ul className="issues">
                            {r.checks.map((c, i) => (
                              <li key={i} className={c.level === "kritis" ? "error" : c.level === "peringatan" ? "warning" : "pass"}>
                                <b>{c.code}</b> [{c.level}] {c.message}
                              </li>
                            ))}
                          </ul>
                          {r.reviews.length > 0 && (
                            <div className="small">
                              <b>Riwayat tinjauan:</b>
                              <ul>
                                {r.reviews.map((v, i) => (
                                  <li key={i}>
                                    {new Date(v.created_at).toLocaleString("id-ID")} · {v.reviewer} · <b>{v.decision}</b>: {v.reason}
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
