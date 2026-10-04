import { Fragment, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  api,
  FILE_STATUS_LABEL,
  FileItem,
  fmtDate,
  Purpose,
  Q_LABEL,
  QStatus,
  SECTIONS,
  statusTone,
  TYPES,
  WELL_STATUS_LABEL,
  WellItem,
} from "../api";
import InboxPanel from "../components/InboxPanel";
import { MonitoringUploadPanel, TrainingUploadPanel } from "../components/UploadPanels";
import QualityBadge from "../components/QualityBadge";

type GroupBy = "none" | "section" | "type" | "section_type" | "quality";
const GROUP_LABEL: Record<GroupBy, string> = {
  none: "No grouping",
  section: "Well section",
  type: "Well type",
  section_type: "Section × type",
  quality: "Data quality",
};

function Badge({ s, labels }: { s: string; labels: Record<string, string> }) {
  return <span className={`badge ${statusTone(s)}`}>{labels[s] ?? s}</span>;
}

function IssueList({ issues }: { issues: FileItem["issues"] }) {
  if (!issues.length) return null;
  return (
    <ul className="issues">
      {issues.map((i, k) => (
        <li key={k} className={i.level}>
          <b>{i.level === "error" ? "Error" : "Warning"}</b>
          {i.location && <span className="muted"> [{i.location}]</span>}: {i.message}
        </li>
      ))}
    </ul>
  );
}

function groupKey(w: WellItem, g: GroupBy): string {
  const sec = w.section_in === null ? "?" : `${w.section_in}"`;
  const typ = w.well_type ?? "?";
  if (g === "section") return `Section ${sec}`;
  if (g === "type") return `Type ${typ}`;
  if (g === "section_type") return `Section ${sec} · Type ${typ}`;
  if (g === "quality") return `${w.quality ?? "–"} · ${w.quality ? Q_LABEL[w.quality] : "not checked"}`;
  return "";
}

export default function WellsPage({ purpose }: { purpose: Purpose }) {
  const qc = useQueryClient();
  const training = purpose === "training";
  const wells = useQuery({
    queryKey: ["wells", purpose],
    queryFn: () => api.get<WellItem[]>(`/api/wells?purpose=${purpose}`),
  });
  const files = useQuery({
    queryKey: ["files", purpose],
    queryFn: () => api.get<FileItem[]>(`/api/files?purpose=${purpose}`),
  });
  const [openFile, setOpenFile] = useState<number | null>(null);
  const [fSection, setFSection] = useState("");
  const [fType, setFType] = useState("");
  const [fQuality, setFQuality] = useState("");
  const [search, setSearch] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("section_type");
  const [fileStatus, setFileStatus] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggle = (g: string) =>
    setCollapsed((s) => {
      const n = new Set(s);
      if (n.has(g)) n.delete(g);
      else n.add(g);
      return n;
    });

  const invalidate = () => {
    for (const k of ["wells", "files", "quality"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/api/wells/${id}`, body),
    onSuccess: invalidate,
    onError: (e) => alert((e as Error).message),
  });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/wells/${id}`), onSuccess: invalidate });
  const promote = useMutation({
    mutationFn: (id: number) => api.post<{ status: string }>(`/api/wells/${id}/promote`),
    onSuccess: (r) => {
      invalidate();
      alert(`Copied to Training Data (import status: ${FILE_STATUS_LABEL[r.status] ?? r.status}). Check it in Data Quality.`);
    },
    onError: (e) => alert((e as Error).message),
  });

  const all = wells.data ?? [];
  const list = useMemo(
    () =>
      all.filter(
        (w) =>
          (!fSection || String(w.section_in) === fSection) &&
          (!fType || w.well_type === fType) &&
          (!fQuality || w.quality === fQuality) &&
          (!search || w.name.toLowerCase().includes(search.toLowerCase())),
      ),
    [all, fSection, fType, fQuality, search],
  );
  const groups = useMemo(() => {
    const m = new Map<string, WellItem[]>();
    const sorted = [...list].sort(
      (a, b) =>
        (b.section_in ?? 0) - (a.section_in ?? 0) ||
        (a.well_type ?? "").localeCompare(b.well_type ?? "") ||
        a.name.localeCompare(b.name),
    );
    for (const w of sorted) {
      const k = groupKey(w, groupBy);
      m.set(k, [...(m.get(k) ?? []), w]);
    }
    return [...m.entries()];
  }, [list, groupBy]);

  const matrix = new Map<string, number>();
  for (const w of all) {
    const k = `${w.section_in ?? "?"}|${w.well_type ?? "?"}`;
    matrix.set(k, (matrix.get(k) ?? 0) + (w.actual_points > 0 && (w.quality === "A" || w.quality === "B") ? 1 : 0));
  }
  const sections = [...new Set(all.map((w) => w.section_in ?? "?"))].sort((a, b) => Number(b) - Number(a));
  const fileList = (files.data ?? []).filter((f) => !fileStatus || f.status === fileStatus);
  const COLS = 12;

  return (
    <div className="page">
      <p className="muted small tabs-note">
        {training ? (
          <>
            <b>Training Data</b> = historical wells, the only reference the ML model learns from. Wells being drilled now go to{" "}
            <Link to="/monitoring">Monitoring</Link>.
          </>
        ) : (
          <>
            <b>Monitoring</b> = wells to be drilled or being drilled. They are forecast and evaluated only and{" "}
            <b>never used for training</b>. After a well is finished, use <i>Promote to training</i> to copy it into{" "}
            <Link to="/training">Training Data</Link> (it then goes through the data quality gate).
          </>
        )}
      </p>

      {training && <InboxPanel />}
      {training ? <TrainingUploadPanel /> : <MonitoringUploadPanel />}

      <section className="card">
        <div className="row space wrap">
          <h2>
            {training ? "Training wells" : "Monitoring wells"} ({list.length}
            {list.length !== all.length ? ` of ${all.length}` : ""})
          </h2>
        </div>
        <div className="row gap wrap small" style={{ marginBottom: 8 }}>
          <label className="inline">
            Search
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="well name" />
          </label>
          <label className="inline">
            Well section
            <select value={fSection} onChange={(e) => setFSection(e.target.value)}>
              <option value="">All</option>
              {SECTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}"
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Well type
            <select value={fType} onChange={(e) => setFType(e.target.value)}>
              <option value="">All</option>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="inline">
            Data quality
            <select value={fQuality} onChange={(e) => setFQuality(e.target.value)}>
              <option value="">All</option>
              {(["A", "B", "C", "X"] as QStatus[]).map((q) => (
                <option key={q} value={q}>
                  {q} · {Q_LABEL[q]}
                </option>
              ))}
            </select>
          </label>
          <label className="inline">
            Group by
            <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
              {(Object.keys(GROUP_LABEL) as GroupBy[]).map((g) => (
                <option key={g} value={g}>
                  {GROUP_LABEL[g]}
                </option>
              ))}
            </select>
          </label>
        </div>
        {wells.isError && <div className="alert error">{(wells.error as Error).message}</div>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Well</th>
                <th>Section</th>
                <th>Type</th>
                <th>Quality</th>
                <th>Format</th>
                <th className="num">Survey</th>
                <th className="num">WellPlan points</th>
                <th className="num">Actual points</th>
                <th>OHFF</th>
                <th>Status</th>
                <th>Forecast</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {groups.map(([g, ws]) => (
                <Fragment key={g || "all"}>
                  {groupBy !== "none" && (
                    <tr className="group-row clickable" onClick={() => toggle(g)} aria-expanded={!collapsed.has(g)}>
                      <td colSpan={COLS}>
                        {collapsed.has(g) ? "▸" : "▾"} {g} <span className="muted">({ws.length})</span>
                      </td>
                    </tr>
                  )}
                  {(groupBy === "none" || !collapsed.has(g) ? ws : []).map((w) => (
                    <tr key={w.id}>
                      <td>
                        <b>{w.name}</b>
                      </td>
                      <td>
                        <select
                          value={w.section_in ?? ""}
                          onChange={(e) => patch.mutate({ id: w.id, body: { section_in: Number(e.target.value) } })}
                        >
                          {w.section_in === null && <option value="">?</option>}
                          {[...new Set([...SECTIONS, ...(w.section_in ? [w.section_in] : [])])].map((s) => (
                            <option key={s} value={s}>
                              {s}"
                            </option>
                          ))}
                        </select>{" "}
                        <span className="muted small">{w.section_source}</span>
                      </td>
                      <td>
                        <select
                          value={w.well_type ?? ""}
                          onChange={(e) => patch.mutate({ id: w.id, body: { well_type: e.target.value } })}
                        >
                          {w.well_type === null && <option value="">?</option>}
                          {TYPES.map((t) => (
                            <option key={t}>{t}</option>
                          ))}
                        </select>{" "}
                        <span className="muted small">{w.type_source}</span>
                      </td>
                      <td>
                        <QualityBadge s={w.quality} />
                      </td>
                      <td className="small">{w.plan_format ?? "–"}</td>
                      <td className="num">{w.survey_points}</td>
                      <td className="num">{w.plan_points}</td>
                      <td className="num">{w.actual_points}</td>
                      <td className="small">{w.ff_scenarios.join(" / ") || "–"}</td>
                      <td>
                        <Badge s={w.status} labels={WELL_STATUS_LABEL} />
                      </td>
                      <td className="small">
                        {w.prediction === "oof" ? "out-of-fold" : w.prediction === "full" ? "full model" : "–"}
                      </td>
                      <td className="nowrap">
                        <Link className="btn small" to={`/dashboard/${w.id}`}>
                          Dashboard
                        </Link>{" "}
                        {!training && (
                          <button
                            className="btn small"
                            disabled={promote.isPending}
                            title="Copy this well into Training Data (after it is drilled)"
                            onClick={() =>
                              confirm(
                                `Copy ${w.name} ${w.section_in}" into Training Data? It will be used for the next training run if it passes the data quality gate.`,
                              ) && promote.mutate(w.id)
                            }
                          >
                            Promote to training
                          </button>
                        )}{" "}
                        <button
                          className="btn small ghost"
                          onClick={() => confirm(`Delete well ${w.name} and its data?`) && del.mutate(w.id)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {training && (
        <section className="card">
          <h2>Wells usable for training (section × type)</h2>
          <p className="muted small">
            Number of well sections with data quality A/B and actual data. Cells with fewer than 3 wells are flagged: model
            results for that combination are less reliable.
          </p>
          <table className="matrix">
            <thead>
              <tr>
                <th>Section</th>
                {TYPES.map((t) => (
                  <th key={t} className="num">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sections.map((s) => (
                <tr key={String(s)}>
                  <td>{s}"</td>
                  {TYPES.map((t) => {
                    const n = matrix.get(`${s}|${t}`) ?? 0;
                    return (
                      <td key={t} className={`num ${n > 0 && n < 3 ? "cell-warn" : ""}`}>
                        {n}
                        {n > 0 && n < 3 && " ⚠"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="card">
        <div className="row space wrap">
          <h2>Import history</h2>
          <label className="inline small">
            Status
            <select value={fileStatus} onChange={(e) => setFileStatus(e.target.value)}>
              <option value="">All</option>
              {Object.entries(FILE_STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Format</th>
                <th>Well</th>
                <th>Section</th>
                <th>Type</th>
                <th>Status</th>
                <th className="num">Issues</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {fileList.map((f) => (
                <Fragment key={f.id}>
                  <tr className="clickable" onClick={() => setOpenFile(openFile === f.id ? null : f.id)}>
                    <td>{f.filename}</td>
                    <td className="small">{f.kind ?? "–"}</td>
                    <td>{f.well_name ?? "–"}</td>
                    <td>{f.section_in ? `${f.section_in}"` : "–"}</td>
                    <td>{f.well_type ?? "–"}</td>
                    <td>
                      <Badge s={f.status} labels={FILE_STATUS_LABEL} />
                    </td>
                    <td className="num">{f.issues.length}</td>
                    <td className="small">{fmtDate(f.created_at)}</td>
                  </tr>
                  {openFile === f.id && (
                    <tr>
                      <td colSpan={8}>
                        {f.issues.length ? <IssueList issues={f.issues} /> : <span className="muted">No issues.</span>}
                        <div className="small muted">
                          Survey points {f.summary.survey_points ?? 0} · WellPlan {f.summary.plan_points ?? 0} · actual{" "}
                          {f.summary.actual_points ?? 0} · <a href={`/api/files/${f.id}/download`}>download the original file</a>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
