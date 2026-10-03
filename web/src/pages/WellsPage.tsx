import { Fragment, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, FileItem, WellItem } from "../api";
import InboxPanel from "../components/InboxPanel";
import QualityBadge from "../components/QualityBadge";

const TYPES = ["J", "S", "Horizontal"];
const SECTIONS = [26, 22, 17.5, 12.25, 8.5, 6.125];

type UploadResult = { name: string; result?: FileItem; error?: string };

function StatusBadge({ s }: { s: string }) {
  const cls =
    s === "ok" || s === "siap" ? "ok" : s === "gagal" ? "bad" : s === "peringatan" || s === "tanpa aktual" ? "warn" : "";
  return <span className={`badge ${cls}`}>{s}</span>;
}

function Uploader({ predictAfter }: { predictAfter?: boolean }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [wellName, setWellName] = useState("");
  const [section, setSection] = useState("");
  const [results, setResults] = useState<UploadResult[]>([]);
  const [busy, setBusy] = useState(false);

  const onDrop = async (files: File[]) => {
    setBusy(true);
    const out: UploadResult[] = [];
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      if (wellName) fd.append("well_name", wellName);
      if (section) fd.append("section_in", section);
      try {
        const r = await api.post<FileItem>("/api/files", fd);
        out.push({ name: f.name, result: r });
        if (predictAfter && r.well_id && r.status !== "gagal") {
          try {
            await api.post(`/api/wells/${r.well_id}/predict`);
            nav(`/dashboard/${r.well_id}`);
          } catch (e) {
            out.push({ name: f.name, error: `Prediksi: ${(e as Error).message}` });
          }
        }
      } catch (e) {
        out.push({ name: f.name, error: (e as Error).message });
      }
      setResults([...out]);
    }
    setBusy(false);
    qc.invalidateQueries({ queryKey: ["wells"] });
    qc.invalidateQueries({ queryKey: ["files"] });
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: !predictAfter,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel.sheet.macroEnabled.12": [".xlsm"],
    },
  });

  return (
    <div>
      <div className="row gap">
        <label className="inline">
          Nama sumur (opsional)
          <input value={wellName} onChange={(e) => setWellName(e.target.value)} placeholder="dari file" />
        </label>
        <label className="inline">
          Section (opsional)
          <select value={section} onChange={(e) => setSection(e.target.value)}>
            <option value="">dari file</option>
            {SECTIONS.map((s) => (
              <option key={s} value={s}>
                {s}"
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted small">
        Isi nama/section hanya bila file tidak memuatnya (mis. file roadmap). File .xlsm dibaca tanpa menjalankan macro.
      </p>
      <div {...getRootProps({ className: `dropzone ${isDragActive ? "active" : ""}` })}>
        <input {...getInputProps()} />
        {busy
          ? "Mengimpor…"
          : predictAfter
            ? "Tarik file WellPlan sumur baru ke sini, atau klik untuk memilih"
            : "Tarik file Excel (.xlsx / .xlsm) ke sini, atau klik untuk memilih. Bisa banyak sekaligus."}
      </div>
      {results.length > 0 && (
        <ul className="results">
          {results.map((r, i) => (
            <li key={i}>
              <b>{r.name}</b>{" "}
              {r.error ? (
                <span className="badge bad">{r.error}</span>
              ) : (
                <>
                  <StatusBadge s={r.result!.status} /> {r.result!.well_name && <>→ sumur {r.result!.well_name}</>}
                  <IssueList issues={r.result!.issues} />
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function IssueList({ issues }: { issues: FileItem["issues"] }) {
  if (!issues.length) return null;
  return (
    <ul className="issues">
      {issues.map((i, k) => (
        <li key={k} className={i.level}>
          <b>{i.level === "error" ? "Galat" : "Peringatan"}</b>
          {i.location && <span className="muted"> [{i.location}]</span>}: {i.message}
        </li>
      ))}
    </ul>
  );
}

export default function WellsPage() {
  const qc = useQueryClient();
  const wells = useQuery({ queryKey: ["wells"], queryFn: () => api.get<WellItem[]>("/api/wells") });
  const files = useQuery({ queryKey: ["files"], queryFn: () => api.get<FileItem[]>("/api/files") });
  const [openFile, setOpenFile] = useState<number | null>(null);

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/api/wells/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wells"] }),
    onError: (e) => alert((e as Error).message),
  });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/api/wells/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wells"] });
      qc.invalidateQueries({ queryKey: ["files"] });
    },
  });

  const list = wells.data ?? [];
  const matrix = new Map<string, number>();
  for (const w of list) {
    const k = `${w.section_in ?? "?"}|${w.well_type ?? "?"}`;
    matrix.set(k, (matrix.get(k) ?? 0) + (w.actual_points > 0 && (w.quality === "A" || w.quality === "B") ? 1 : 0));
  }
  const sections = [...new Set(list.map((w) => w.section_in ?? "?"))].sort((a, b) => Number(b) - Number(a));

  return (
    <div className="page">
      <InboxPanel />

      <section className="card">
        <h2>Unggah file Excel</h2>
        <Uploader />
      </section>

      <section className="card">
        <h2>Prediksi sumur baru</h2>
        <p className="muted small">
          Unggah satu laporan WellPlan sumur baru. Setelah impor, prediksi dibuat dengan model aktif lalu dashboard dibuka.
        </p>
        <Uploader predictAfter />
      </section>

      <section className="card">
        <h2>Daftar sumur ({list.length})</h2>
        {wells.isError && <div className="alert error">{(wells.error as Error).message}</div>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sumur</th>
                <th>Section</th>
                <th>Tipe</th>
                <th>Kualitas</th>
                <th>Format</th>
                <th className="num">Survey</th>
                <th className="num">Titik WellPlan</th>
                <th className="num">Titik aktual</th>
                <th>FF</th>
                <th>Status</th>
                <th>Prediksi</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((w) => (
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
                    <StatusBadge s={w.status} />
                  </td>
                  <td className="small">{w.prediction === "oof" ? "out-of-fold" : w.prediction === "full" ? "model penuh" : "–"}</td>
                  <td className="nowrap">
                    <Link className="btn small" to={`/dashboard/${w.id}`}>
                      Dashboard
                    </Link>{" "}
                    <button
                      className="btn small ghost"
                      onClick={() => confirm(`Hapus sumur ${w.name} beserta datanya?`) && del.mutate(w.id)}
                    >
                      Hapus
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Matriks sumur layak training (section × tipe)</h2>
        <p className="muted small">
          Jumlah sumur-section berstatus kualitas A/B dengan data aktual. Sel dengan kurang dari 3 sumur ditandai: hasil model untuk
          kombinasi itu kurang andal.
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

      <section className="card">
        <h2>Riwayat impor</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Jenis</th>
                <th>Sumur</th>
                <th>Status</th>
                <th className="num">Masalah</th>
                <th>Waktu</th>
              </tr>
            </thead>
            <tbody>
              {(files.data ?? []).map((f) => (
                <Fragment key={f.id}>
                  <tr className="clickable" onClick={() => setOpenFile(openFile === f.id ? null : f.id)}>
                    <td>{f.filename}</td>
                    <td className="small">{f.kind ?? "–"}</td>
                    <td>{f.well_name ?? "–"}</td>
                    <td>
                      <StatusBadge s={f.status} />
                    </td>
                    <td className="num">{f.issues.length}</td>
                    <td className="small">{new Date(f.created_at).toLocaleString("id-ID")}</td>
                  </tr>
                  {openFile === f.id && (
                    <tr>
                      <td colSpan={6}>
                        {f.issues.length ? <IssueList issues={f.issues} /> : <span className="muted">Tidak ada masalah.</span>}
                        <div className="small muted">
                          Titik survey {f.summary.survey_points ?? 0} · WellPlan {f.summary.plan_points ?? 0} · aktual{" "}
                          {f.summary.actual_points ?? 0} ·{" "}
                          <a href={`/api/files/${f.id}/download`}>unduh file asli</a>
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
