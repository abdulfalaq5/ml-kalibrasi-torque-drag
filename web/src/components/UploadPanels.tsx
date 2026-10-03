import { ReactNode, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, FileItem, fmt, OP_LABEL, OPS, Profile, QStatus } from "../api";
import QualityBadge from "./QualityBadge";

const TYPES = ["J", "S", "Horizontal"];
const SECTIONS = [26, 22, 17.5, 12.25, 8.5, 6.125];
type Upload = FileItem & {
  quality: { status: QStatus; score: number | null; issues: string[] } | null;
  section_in: number | null;
  well_type: string | null;
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
      <b>Punya file asli dari WellPlan?</b> Tidak perlu template, langsung unggah di langkah 3. Sistem mengenali formatnya
      otomatis:
      <ul>
        <li>
          <b>Laporan WellPlan (.xlsm)</b>: nama sumur, section, dan tipe sumur terbaca dari isi file dan nama file.
        </li>
        <li>
          <b>Roadmap (.xlsx, sheet Drag/Torque)</b>: file ini tidak memuat survey, jadi <b>pilih Tipe sumur</b> di "Isian
          manual". Pastikan section ada di nama file (mis. <code>_8.5in</code>, <code>12.25 HS</code>); bila tidak, pilih juga
          Section.
        </li>
      </ul>
    </div>
  );
}

function Overrides({ value, onChange }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
  return (
    <details className="small">
      <summary>Isian manual: nama sumur / section / tipe sumur (wajib pilih tipe untuk file roadmap .xlsx asli)</summary>
      <div className="row gap wrap" style={{ marginTop: 6 }}>
        <label className="inline">
          Nama sumur
          <input value={value.well_name ?? ""} onChange={(e) => onChange({ ...value, well_name: e.target.value })} placeholder="dari file" />
        </label>
        <label className="inline">
          Section
          <select value={value.section_in ?? ""} onChange={(e) => onChange({ ...value, section_in: e.target.value })}>
            <option value="">dari file</option>
            {SECTIONS.map((s) => (
              <option key={s} value={s}>
                {s}"
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          Tipe sumur
          <select value={value.well_type ?? ""} onChange={(e) => onChange({ ...value, well_type: e.target.value })}>
            <option value="">dari file</option>
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>
    </details>
  );
}

function useDrop(multiple: boolean, onDrop: (f: File[]) => void) {
  return useDropzone({
    onDrop,
    multiple,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel.sheet.macroEnabled.12": [".xlsm"],
    },
  });
}

async function upload(f: File, extra: Record<string, string>): Promise<Upload> {
  const fd = new FormData();
  fd.append("file", f);
  for (const [k, v] of Object.entries(extra)) if (v) fd.append(k, v);
  return api.post<Upload>("/api/files", fd);
}

function FileIssues({ r }: { r: Upload }) {
  if (!r.issues.length) return null;
  return (
    <ul className="issues">
      {r.issues.map((i, k) => (
        <li key={k} className={i.level}>
          <b>{i.level === "error" ? "Galat" : "Peringatan"}</b>
          {i.location && <span className="muted"> [{i.location}]</span>}: {i.message}
        </li>
      ))}
    </ul>
  );
}

const FILE_BADGE: Record<string, string> = { ok: "ok", peringatan: "warn", gagal: "bad" };

/* ------------------------------------------------------------------ Impor data latih */

export function ImportPanel() {
  const qc = useQueryClient();
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [results, setResults] = useState<{ name: string; r?: Upload; error?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const { getRootProps, getInputProps, isDragActive } = useDrop(true, async (files) => {
    setBusy(true);
    const out: typeof results = [];
    for (const f of files) {
      try {
        out.push({ name: f.name, r: await upload(f, extra) });
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
      <h2>Impor file Excel (data latih)</h2>
      <p className="muted small">
        Data sumur yang sudah dibor: rencana WellPlan + pembacaan aktual lapangan. Data ini dipakai untuk melatih model. Bisa
        memakai template di bawah, atau langsung file roadmap / laporan WellPlan asli (.xlsx / .xlsm).
      </p>
      <Steps>
        <Step n={1} title="Unduh template">
          <a className="btn" href="/api/templates/data-latih.xlsx">
            ⬇ Template data latih (.xlsx)
          </a>{" "}
          <span className="muted small">Sheet: Petunjuk, Info Sumur, Drag, Torque, T&amp;D Actual Reading, Survey (opsional), Contoh.</span>
          <RawFileNote />
        </Step>
        <Step n={2} title="Isi data sesuai template">
          <span className="small">
            Satu file = satu section. Isi <b>Info Sumur</b> (nama, section, tipe, block weight), <b>Drag</b> &amp; <b>Torque</b> (hasil
            WellPlan per friction factor), dan <b>T&amp;D Actual Reading</b> (minimal 8 kedalaman). Ikuti sheet Contoh.
          </span>
        </Step>
        <Step n={3} title="Unggah ke sistem">
          <div {...getRootProps({ className: `dropzone ${isDragActive ? "active" : ""}` })}>
            <input {...getInputProps()} />
            {busy ? "Memproses…" : "Tarik file ke sini atau klik untuk memilih. Bisa banyak file sekaligus."}
          </div>
          <Overrides value={extra} onChange={setExtra} />
        </Step>
        <Step n={4} title="Hasil">
          {!results.length ? (
            <span className="muted small">Hasil impor dan status kualitas data muncul di sini.</span>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Impor</th>
                    <th>Sumur</th>
                    <th>Section</th>
                    <th>Tipe</th>
                    <th>Kualitas data</th>
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
                      <td>
                        {x.error ? <span className="badge bad">{x.error}</span> : <span className={`badge ${FILE_BADGE[x.r!.status] ?? ""}`}>{x.r!.status}</span>}
                      </td>
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
                Status A/B = dipakai melatih model berikutnya. Status C = perlu tinjauan di menu <Link to="/kualitas">Kualitas data</Link>.
                Setelah data baru masuk: Model → Bekukan dataset baru → Latih model.
              </p>
            </div>
          )}
        </Step>
      </Steps>
    </section>
  );
}

/* ------------------------------------------------------------------ Prediksi sumur baru */

type PredictResult = { file: Upload; profile?: Profile; warnings?: string[]; error?: string };

function lastValue(depth: number[], value: number[]) {
  if (!depth.length) return { d: null as number | null, v: null as number | null };
  let k = 0;
  depth.forEach((d, i) => {
    if (d > depth[k]) k = i;
  });
  return { d: depth[k], v: value[k] };
}

export function PredictPanel() {
  const qc = useQueryClient();
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [res, setRes] = useState<PredictResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { getRootProps, getInputProps, isDragActive } = useDrop(false, async (files) => {
    const f = files[0];
    if (!f) return;
    setErr(null);
    setRes(null);
    try {
      setBusy("Mengimpor dan memeriksa file…");
      const up = await upload(f, extra);
      if (up.status === "gagal" || !up.well_id) {
        setRes({ file: up, error: "File tidak bisa diimpor. Perbaiki sesuai alasan di bawah lalu unggah lagi." });
        return;
      }
      setBusy("Memprediksi dengan model aktif…");
      let warnings: string[] = [];
      try {
        warnings = (await api.post<{ warnings: string[] }>(`/api/wells/${up.well_id}/predict`)).warnings;
      } catch (e) {
        setRes({ file: up, error: `Prediksi gagal: ${(e as Error).message}` });
        return;
      }
      setBusy("Menyiapkan hasil…");
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
      <h2>Prediksi sumur baru</h2>
      <p className="muted small">
        Sumur yang akan dibor: cukup rencana WellPlan (Drag &amp; Torque). Sistem memprediksi hookload dan torque sebenarnya per
        kedalaman memakai model aktif.
      </p>
      <Steps>
        <Step n={1} title="Unduh template">
          <a className="btn" href="/api/templates/sumur-baru.xlsx">
            ⬇ Template sumur baru (.xlsx)
          </a>{" "}
          <span className="muted small">Sheet: Petunjuk, Info Sumur, Drag, Torque, Survey (opsional), Contoh.</span>
          <RawFileNote />
        </Step>
        <Step n={2} title="Isi data sesuai template">
          <span className="small">
            Isi <b>Info Sumur</b> (nama, section, tipe, block weight) dan hasil WellPlan di <b>Drag</b> &amp; <b>Torque</b>. Isi
            <b> Survey</b> bila ada agar prediksi lebih baik. File roadmap / laporan WellPlan asli juga diterima.
          </span>
        </Step>
        <Step n={3} title="Unggah ke sistem">
          <div {...getRootProps({ className: `dropzone ${isDragActive ? "active" : ""}` })}>
            <input {...getInputProps()} />
            {busy ?? "Tarik satu file ke sini atau klik untuk memilih"}
          </div>
          <Overrides value={extra} onChange={setExtra} />
        </Step>
        <Step n={4} title="Hasil prediksi">
          {err && <div className="alert error">{err}</div>}
          {!res && !err && <span className="muted small">Ringkasan prediksi dan tautan unduhan muncul di sini.</span>}
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
                  <span className="muted small">model #{p.prediction?.model_id} · dataset v{p.model?.dataset_version ?? "?"}</span>
                </div>
                <div className="row gap wrap">
                  <Link className="btn primary" to={`/dashboard/${wid}`}>
                    Buka dashboard
                  </Link>
                  <a className="btn" href={`/api/wells/${wid}/export.xlsx`}>
                    ⬇ Hasil prediksi (.xlsx)
                  </a>
                  <a className="btn" href={`/api/wells/${wid}/report.pdf`}>
                    ⬇ Ringkasan (PDF)
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
                    <th>Operasi</th>
                    <th className="num">Kedalaman akhir ({p.depth_unit})</th>
                    <th className="num">WellPlan (FF 0,3)</th>
                    <th className="num">Prediksi ML</th>
                    <th className="num">Rentang ML 10–90%</th>
                    <th className="num">ML − WellPlan</th>
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
                        <td className="num">
                          {dl.v === null ? "–" : `${dl.v > 0 ? "+" : ""}${fmt(dl.v, 1)}`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="small muted">
                Prediksi per kedalaman lengkap ada di dashboard dan file Excel (sheet Drag, Torque). Setelah sumur dibor, unggah data
                aktualnya di "Impor file Excel": sistem otomatis membandingkan prediksi ini dengan aktual (menu Evaluasi).
              </p>
            </div>
          )}
        </Step>
      </Steps>
    </section>
  );
}
