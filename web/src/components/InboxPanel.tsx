import { Fragment, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, InboxStatus, SCAN_STATUS_LABEL, ScanRun, statusTone } from "../api";
import QualityBadge from "./QualityBadge";


export default function InboxPanel() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["inbox"], queryFn: () => api.get<InboxStatus>("/api/inbox/status") });
  const runs = useQuery({
    queryKey: ["scanruns"],
    queryFn: () => api.get<ScanRun[]>("/api/inbox/runs"),
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => r.status === "running") ? 2000 : false),
  });
  const latest = runs.data?.[0];
  const detail = useQuery({
    queryKey: ["scanrun", latest?.id, latest?.status],
    queryFn: () => api.get<ScanRun>(`/api/inbox/runs/${latest!.id}`),
    enabled: !!latest && latest.status !== "running",
  });
  const [show, setShow] = useState<"well" | "file">("well");
  const scan = useMutation({
    mutationFn: () => api.post<ScanRun>("/api/inbox/scan"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scanruns"] }),
    onError: (e) => alert((e as Error).message),
  });
  const running = latest?.status === "running";
  const doneKey = latest && !running ? `${latest.id}-${latest.status}` : null;
  useEffect(() => {
    // after a scan finishes, refresh the other lists (once per scan)
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
        <h2>Bulk import from folder (training data)</h2>
        <button className="btn primary" disabled={running || scan.isPending || !s?.pending} onClick={() => scan.mutate()}>
          {running ? "Scanning…" : "Scan folder"}
        </button>
      </div>
      <p className="muted small">
        For many historical wells at once (administrator). Put files in{" "}
        <code>data/inbox/&lt;J|S|Horizontal&gt;/&lt;well&gt;/</code> (folder name = well code, parent folder = well type; the
        well section is read from the file name). Files are always imported as <b>Training Data</b>. Files modified less than
        1 minute ago are skipped. After import, files move to <code>data/processed/</code> or <code>data/rejected/</code>{" "}
        (with the reason).
      </p>
      {s && (
        <p className="small">
          Inbox: <b>{s.pending}</b> files from <b>{s.wells}</b> well folders waiting
          {s.too_new > 0 && <> · {s.too_new} recently modified (skipped)</>}
          {!s.exists && <span className="bad-text"> · the inbox folder does not exist yet</span>}
        </p>
      )}
      {latest && (
        <div className="small">
          Last scan #{latest.id}: <b>{SCAN_STATUS_LABEL[latest.status] ?? latest.status}</b>
          {latest.counts &&
            Object.entries(latest.counts).map(([k, v]) => (
              <span key={k} className={`badge ${statusTone(k)}`} style={{ marginLeft: 6 }}>
                {v} {SCAN_STATUS_LABEL[k] ?? k}
              </span>
            ))}
          {latest.quality && (
            <span style={{ marginLeft: 10 }}>
              Quality: A {latest.quality.A ?? 0} · B {latest.quality.B ?? 0} · C {latest.quality.C ?? 0}
            </span>
          )}
          {latest.error && <div className="bad-text">{latest.error}</div>}
        </div>
      )}
      {d?.files && (
        <>
          <div className="seg" style={{ marginTop: 10 }}>
            <button className={show === "well" ? "on" : ""} onClick={() => setShow("well")}>
              By well section ({d.wells?.length ?? 0})
            </button>
            <button className={show === "file" ? "on" : ""} onClick={() => setShow("file")}>
              By file ({d.files.length})
            </button>
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflow: "auto", marginTop: 8 }}>
            {show === "well" ? (
              <table>
                <thead>
                  <tr>
                    <th>Well</th>
                    <th>Section</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Reasons</th>
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
                    <th>Result</th>
                    <th>Well</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {d.files.map((f, i) => (
                    <Fragment key={i}>
                      <tr>
                        <td className="small">{f.file}</td>
                        <td>
                          <span className={`badge ${statusTone(f.status)}`}>{SCAN_STATUS_LABEL[f.status] ?? f.status}</span>
                        </td>
                        <td className="small">
                          {f.well ?? "–"} {f.section ? `${f.section}"` : ""} {f.version && f.version > 1 ? `(version ${f.version})` : ""}
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
