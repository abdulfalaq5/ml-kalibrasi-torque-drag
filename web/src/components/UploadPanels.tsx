import { ReactNode, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  api,
  FILE_STATUS_LABEL,
  FileItem,
  fmt,
  OP_LABEL,
  OPS,
  Profile,
  Purpose,
  QStatus,
  SECTIONS,
  statusTone,
  TYPES,
} from "../api";
import QualityBadge from "./QualityBadge";

type Upload = FileItem & {
  quality: { status: QStatus; score: number | null; issues: string[] } | null;
};

function Steps({ children }: { children: ReactNode }) {
  return <ol className="steps">{children}</ol>;
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="step">
      <span className="step-n">{n}</span>
      <div className="step-body">
        <b>{title}</b>
        <div>{children}</div>
      </div>
    </li>
  );
}

function RawFileNote() {
  return (
    <div className="raw-note small">
      <b>Have the original WellPlan file?</b> No template is needed; upload it directly. The system recognises both formats
      automatically:
      <ul>
        <li>
          <b>WellPlan report (.xlsm)</b>: Summary, Tripping Load Analysis, Off Bottom Torque, Survey Outputs, Drilling Data.
        </li>
        <li>
          <b>T&amp;D roadmap (.xlsx, sheets Drag/Torque)</b>: including the DD <b>Calibrate</b> offsets at the top of the
          Drag and Torque sheets.
        </li>
      </ul>
    </div>
  );
}

export type WellChoice = { section_in: string; well_type: string; well_name: string };

/** Step 1: well section and well type are required before any file can be uploaded. */
function WellChoiceFields({ value, onChange }: { value: WellChoice; onChange: (v: WellChoice) => void }) {
  return (
    <div className="row gap wrap">
      <label className="inline">
        Well section <span className="req">*</span>
        <select value={value.section_in} onChange={(e) => onChange({ ...value, section_in: e.target.value })}>
          <option value="">Select…</option>
          {SECTIONS.map((s) => (
            <option key={s} value={s}>
              {s}"
            </option>
          ))}
        </select>
      </label>
      <label className="inline">
        Well type <span className="req">*</span>
        <select value={value.well_type} onChange={(e) => onChange({ ...value, well_type: e.target.value })}>
          <option value="">Select…</option>
          {TYPES.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label className="inline">
        Well name <span className="muted">(optional)</span>
        <input
          value={value.well_name}
          onChange={(e) => onChange({ ...value, well_name: e.target.value })}
          placeholder="read from the file"
        />
      </label>
    </div>
  );
}

function useDrop(multiple: boolean, disabled: boolean, onDrop: (f: File[]) => void) {
  return useDropzone({
    onDrop,
    multiple,
    disabled,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel.sheet.macroEnabled.12": [".xlsm"],
    },
  });
}

async function upload(f: File, purpose: Purpose, choice: WellChoice): Promise<Upload> {
  const fd = new FormData();
  fd.append("file", f);
  fd.append("purpose", purpose);
  fd.append("section_in", choice.section_in);
  fd.append("well_type", choice.well_type);
  if (choice.well_name.trim()) fd.append("well_name", choice.well_name.trim());
  return api.post<Upload>("/api/files", fd);
}

function FileIssues({ r }: { r: Upload }) {
  if (!r.issues.length) return null;
  return (
    <ul className="issues">
      {r.issues.map((i, k) => (
        <li key={k} className={i.level}>
          <b>{i.level === "error" ? "Error" : "Warning"}</b>
          {i.location && <span className="muted"> [{i.location}]</span>}: {i.message}
        </li>
      ))}
    </ul>
  );
}

function FileBadge({ s }: { s: string }) {
  return <span className={`badge ${statusTone(s)}`}>{FILE_STATUS_LABEL[s] ?? s}</span>;
}

const EMPTY: WellChoice = { section_in: "", well_type: "", well_name: "" };

/* ------------------------------------------------------------------ Training upload */

export function TrainingUploadPanel() {
  const qc = useQueryClient();
  const [choice, setChoice] = useState<WellChoice>(EMPTY);
  const ready = !!choice.section_in && !!choice.well_type;
  const [results, setResults] = useState<{ name: string; r?: Upload; error?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const { getRootProps, getInputProps, isDragActive } = useDrop(true, !ready || busy, async (files) => {
    setBusy(true);
    const out: typeof results = [];
    for (const f of files) {
      try {
        out.push({ name: f.name, r: await upload(f, "training", choice) });
      } catch (e) {
        out.push({ name: f.name, error: (e as Error).message });
      }
      setResults([...out]);
    }
    setBusy(false);
    for (const k of ["wells", "files", "quality"]) qc.invalidateQueries({ queryKey: [k] });
  });

  return (
    <section className="card">
      <h2>Upload training data (ML reference)</h2>
      <p className="muted small">
        Wells that have been drilled: WellPlan T&amp;D model + actual field readings. Only <b>Training Data</b> is used to train
        the ML model. Wells being drilled now belong in <Link to="/monitoring">Monitoring</Link>; the two groups are never
        mixed.
      </p>
      <Steps>
        <Step n={1} title="Select the well section and well type">
          <WellChoiceFields value={choice} onChange={setChoice} />
          <span className="muted small">All files in one upload must have the same section and type.</span>
        </Step>
        <Step n={2} title="Download the template (optional)">
          <a className="btn" href="/api/templates/training.xlsx">
            ⬇ Training data template (.xlsx)
          </a>{" "}
          <span className="muted small">
            Sheets: Instructions, Well Info, Drag, Torque, T&amp;D Actual Reading, Survey (optional), Example.
          </span>
          <RawFileNote />
        </Step>
        <Step n={3} title="Fill in the data">
          <span className="small">
            One file = one well section. Fill in <b>Drag</b> &amp; <b>Torque</b> (WellPlan results per OHFF, with optional DD
            Calibrate offsets) and <b>T&amp;D Actual Reading</b> (at least 8 depths). Follow the Example sheets.
          </span>
        </Step>
        <Step n={4} title="Upload">
          <div {...getRootProps({ className: `dropzone ${isDragActive ? "active" : ""} ${ready ? "" : "disabled"}` })}>
            <input {...getInputProps()} />
            {!ready
              ? "Select the well section and well type first (step 1)."
              : busy
                ? "Processing…"
                : "Drop files here or click to choose. Several files at once are fine."}
          </div>
        </Step>
        <Step n={5} title="Result">
          {!results.length ? (
            <span className="muted small">Import results and the data quality status appear here.</span>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Import</th>
                    <th>Well</th>
                    <th>Section</th>
                    <th>Type</th>
                    <th>Data quality</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((x, i) => (
                    <tr key={i}>
                      <td className="small">
                        {x.name}
                        {x.r && <FileIssues r={x.r} />}
                        {x.r?.quality?.issues.length ? (
                          <ul className="issues">
                            {x.r.quality.issues.map((m, k) => (
                              <li key={k} className="warning">
                                {m}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </td>
                      <td>{x.error ? <span className="badge bad">{x.error}</span> : <FileBadge s={x.r!.status} />}</td>
                      <td>{x.r?.well_name ?? "–"}</td>
                      <td>{x.r?.section_in ? `${x.r.section_in}"` : "–"}</td>
                      <td>{x.r?.well_type ?? "–"}</td>
                      <td>{x.r?.quality ? <QualityBadge s={x.r.quality.status} long /> : "–"}</td>
                      <td className="nowrap">
                        {x.r?.well_id && (
                          <Link className="btn small" to={`/dashboard/${x.r.well_id}`}>
                            Dashboard
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted">
                Status A/B = used for the next training run. Status C = needs review in{" "}
                <Link to="/quality">Data Quality</Link>. After new data: Models → Freeze a new dataset → Train.
              </p>
            </div>
          )}
        </Step>
      </Steps>
    </section>
  );
}

/* ------------------------------------------------------------------ Monitoring upload */

type MonitorResult = { file: Upload; profile?: Profile; warnings?: string[]; error?: string };

function lastValue(depth: number[], value: (number | null)[]) {
  if (!depth.length) return { d: null as number | null, v: null as number | null };
  let k = 0;
  depth.forEach((d, i) => {
    if (d > depth[k]) k = i;
  });
  return { d: depth[k], v: value[k] ?? null };
}

export function MonitoringUploadPanel() {
  const qc = useQueryClient();
  const [choice, setChoice] = useState<WellChoice>(EMPTY);
  const ready = !!choice.section_in && !!choice.well_type;
  const [busy, setBusy] = useState<string | null>(null);
  const [res, setRes] = useState<MonitorResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { getRootProps, getInputProps, isDragActive } = useDrop(false, !ready || !!busy, async (files) => {
    const f = files[0];
    if (!f) return;
    setErr(null);
    setRes(null);
    try {
      setBusy("Importing and checking the file…");
      const up = await upload(f, "monitoring", choice);
      if (up.status === "failed" || !up.well_id) {
        setRes({ file: up, error: "The file could not be imported. Fix it as described below and upload again." });
        return;
      }
      setBusy("Forecasting with the active model…");
      let warnings: string[] = [];
      try {
        warnings = (await api.post<{ warnings: string[] }>(`/api/wells/${up.well_id}/predict`)).warnings;
      } catch (e) {
        setRes({ file: up, error: `Forecast failed: ${(e as Error).message}` });
        return;
      }
      setBusy("Preparing the result…");
      const profile = await api.get<Profile>(`/api/wells/${up.well_id}/profile`);
      setRes({ file: up, profile, warnings });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
      for (const k of ["wells", "files", "quality"]) qc.invalidateQueries({ queryKey: [k] });
    }
  });
  const p = res?.profile;
  const wid = res?.file.well_id;

  return (
    <section className="card">
      <h2>Upload a monitoring well (forecast only)</h2>
      <p className="muted small">
        A well that is about to be drilled or is being drilled: the WellPlan T&amp;D model, plus actual readings so far if
        available. The system forecasts hookload and torque with the active model.{" "}
        <b>Monitoring data is never used for training.</b>
      </p>
      <Steps>
        <Step n={1} title="Select the well section and well type">
          <WellChoiceFields value={choice} onChange={setChoice} />
        </Step>
        <Step n={2} title="Download the template (optional)">
          <a className="btn" href="/api/templates/monitoring.xlsx">
            ⬇ Monitoring well template (.xlsx)
          </a>{" "}
          <span className="muted small">Sheets: Instructions, Well Info, Drag, Torque, Survey (optional), Example.</span>
          <RawFileNote />
        </Step>
        <Step n={3} title="Fill in the data">
          <span className="small">
            Fill in the WellPlan results in <b>Drag</b> &amp; <b>Torque</b>, and <b>Survey</b> if available for a better
            forecast. Original roadmap / WellPlan report files are accepted too.
          </span>
        </Step>
        <Step n={4} title="Upload">
          <div {...getRootProps({ className: `dropzone ${isDragActive ? "active" : ""} ${ready ? "" : "disabled"}` })}>
            <input {...getInputProps()} />
            {!ready ? "Select the well section and well type first (step 1)." : (busy ?? "Drop one file here or click to choose")}
          </div>
        </Step>
        <Step n={5} title="Forecast result">
          {err && <div className="alert error">{err}</div>}
          {!res && !err && <span className="muted small">A forecast summary and download links appear here.</span>}
          {res?.error && (
            <div>
              <div className="alert error">{res.error}</div>
              <FileIssues r={res.file} />
            </div>
          )}
          {p && wid && (
            <div className="predict-result">
              <div className="row space wrap">
                <div>
                  <b>
                    {p.well.name} · {p.well.section_in}" · {p.well.well_type ?? "?"}
                  </b>{" "}
                  <span className="muted small">
                    model #{p.prediction?.model_id} · dataset v{p.model?.dataset_version ?? "?"}
                  </span>
                </div>
                <div className="row gap wrap">
                  <Link className="btn primary" to={`/dashboard/${wid}`}>
                    Open dashboard (forecast N ft ahead)
                  </Link>
                  <a className="btn" href={`/api/wells/${wid}/export.xlsx`}>
                    ⬇ Prediction Output (.xlsx)
                  </a>
                  <a className="btn" href={`/api/wells/${wid}/report.pdf`}>
                    ⬇ Summary (PDF)
                  </a>
                </div>
              </div>
              {(res.warnings ?? []).length > 0 && (
                <div className="alert warn" style={{ marginTop: 8 }}>
                  {res.warnings!.map((w, i) => (
                    <div key={i}>⚠ {w}</div>
                  ))}
                </div>
              )}
              <table style={{ marginTop: 8 }}>
                <thead>
                  <tr>
                    <th>Operation</th>
                    <th className="num">Final depth ({p.depth_unit})</th>
                    <th className="num">T&amp;D Model (OHFF 0.3)</th>
                    <th className="num">ML forecast</th>
                    <th className="num">Uncertainty band (P10–P90)</th>
                    <th className="num">ML − T&amp;D Model</th>
                  </tr>
                </thead>
                <tbody>
                  {OPS.map((op) => {
                    const o = p.operations[op];
                    const ml = lastValue(o.ml.depth, o.ml.value);
                    const lo = lastValue(o.ml.depth, o.ml.lo ?? []);
                    const hi = lastValue(o.ml.depth, o.ml.hi ?? []);
                    const d = o.diff.ml_minus_wp;
                    const dl = lastValue(d.depth, d.abs);
                    const wp = ml.v !== null && dl.v !== null ? ml.v - dl.v : null;
                    return (
                      <tr key={op}>
                        <td>
                          {OP_LABEL[op]} <span className="muted small">({o.unit})</span>
                        </td>
                        <td className="num">{fmt(ml.d, 0)}</td>
                        <td className="num">{fmt(wp, 1)}</td>
                        <td className="num">
                          <b>{fmt(ml.v, 1)}</b>
                        </td>
                        <td className="num">{lo.v !== null ? `${fmt(lo.v, 1)} – ${fmt(hi.v, 1)}` : "–"}</td>
                        <td className="num">{dl.v === null ? "–" : `${dl.v > 0 ? "+" : ""}${fmt(dl.v, 1)}`}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="small muted">
                The full forecast per depth is on the dashboard and in the Excel file. Upload the file again with new actual
                readings as drilling progresses: the system compares this forecast with the actual data (Evaluations).
              </p>
            </div>
          )}
        </Step>
      </Steps>
    </section>
  );
}
