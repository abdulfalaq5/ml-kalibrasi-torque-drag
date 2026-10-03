import { Fragment, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, InboxStatus, ScanRun } from "../api";
import QualityBadge from "./QualityBadge";

const FILE_CLS: Record<string, string> = {
  diterima: "ok",
  "diterima dengan peringatan": "warn",
  duplikat: "",
  dilewati: "",
  ditolak: "bad",
};

export default function InboxPanel() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["inbox"], queryFn: () => api.get<InboxStatus>("/api/inbox/status") });
  const runs = useQuery({
    queryKey: ["scanruns"],
    queryFn: () => api.get<ScanRun[]>("/api/inbox/runs"),
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => r.status === "berjalan") ? 2000 : false),
  });
  const latest = runs.data?.[0];
  const detail = useQuery({
    queryKey: ["scanrun", latest?.id, latest?.status],
    queryFn: () => api.get<ScanRun>(`/api/inbox/runs/${latest!.id}`),
    enabled: !!latest && latest.status !== "berjalan",
  });
  const [show, setShow] = useState<"sumur" | "file">("sumur");
  const scan = useMutation({
    mutationFn: () => api.post<ScanRun>("/api/inbox/scan"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scanruns"] }),
    onError: (e) => alert((e as Error).message),
  });
  const running = latest?.status === "berjalan";
  const doneKey = latest && !running ? `${latest.id}-${latest.status}` : null;
  useEffect(() => {
    // setelah pemindaian selesai, segarkan daftar lain (sekali per pemindaian)
    if (!doneKey) return;
    qc.invalidateQueries({ queryKey: ["wells"] });
    qc.invalidateQueries({ queryKey: ["quality"] });
    qc.invalidateQueries({ queryKey: ["inbox"] });
    qc.invalidateQueries({ queryKey: ["files"] });
  }, [doneKey, qc]);
  const s = status.data;
  const d = detail.data;

  return (
    <section className="card">
      <div className="row space wrap">
        <h2>Impor massal dari folder</h2>
        <button className="btn primary" disabled={running || scan.isPending || !s?.pending} onClick={() => scan.mutate()}>
          {running ? "Memindai…" : "Pindai folder"}
        </button>
      </div>
      <p className="muted small">
        Taruh file di <code>data/inbox/&lt;sumur&gt;/</code> atau <code>data/inbox/&lt;J|S|Horizontal&gt;/&lt;sumur&gt;/</code> (nama
        folder = kode sumur, folder induk = tipe sumur). File yang baru diubah &lt; 1 menit dilewati. Setelah diimpor file dipindah
        ke <code>data/processed/</code> atau <code>data/rejected/</code> (beserta alasan).
      </p>
      {s && (
        <p className="small">
          Inbox: <b>{s.pending}</b> file dari <b>{s.wells}</b> folder sumur menunggu
          {s.too_new > 0 && <> · {s.too_new} baru diubah (dilewati)</>}
          {!s.exists && <span className="bad-text"> · folder inbox belum ada</span>}
        </p>
      )}
      {latest && (
        <div className="small">
          Pemindaian terakhir #{latest.id}: <b>{latest.status}</b>
          {latest.counts &&
            Object.entries(latest.counts).map(([k, v]) => (
              <span key={k} className={`badge ${FILE_CLS[k] ?? ""}`} style={{ marginLeft: 6 }}>
                {v} {k}
              </span>
            ))}
          {latest.quality && (
            <span style={{ marginLeft: 10 }}>
              Kualitas: A {latest.quality.A ?? 0} · B {latest.quality.B ?? 0} · C {latest.quality.C ?? 0}
            </span>
          )}
          {latest.error && <div className="bad-text">{latest.error}</div>}
        </div>
      )}
      {d?.files && (
        <>
          <div className="seg" style={{ marginTop: 10 }}>
            <button className={show === "sumur" ? "on" : ""} onClick={() => setShow("sumur")}>
              Per sumur-section ({d.wells?.length ?? 0})
            </button>
            <button className={show === "file" ? "on" : ""} onClick={() => setShow("file")}>
              Per file ({d.files.length})
            </button>
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflow: "auto", marginTop: 8 }}>
            {show === "sumur" ? (
              <table>
                <thead>
                  <tr>
                    <th>Sumur</th>
                    <th>Section</th>
                    <th>Tipe</th>
                    <th>Status</th>
                    <th>Alasan</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.wells ?? []).map((w, i) => (
                    <tr key={i}>
                      <td>{w.well}</td>
                      <td>{w.section}"</td>
                      <td>{w.type}</td>
                      <td>
                        <QualityBadge s={w.quality} long />
                      </td>
                      <td className="small">{w.reasons.join("; ") || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Hasil</th>
                    <th>Sumur</th>
                    <th>Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {d.files.map((f, i) => (
                    <Fragment key={i}>
                      <tr>
                        <td className="small">{f.file}</td>
                        <td>
                          <span className={`badge ${FILE_CLS[f.status] ?? ""}`}>{f.status}</span>
                        </td>
                        <td className="small">
                          {f.well ?? "–"} {f.section ? `${f.section}"` : ""} {f.version && f.version > 1 ? `(versi ${f.version})` : ""}
                        </td>
                        <td className="small">{f.message || "–"}</td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </section>
  );
}
