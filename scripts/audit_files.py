"""Audit file Excel client (Hari 2): sheet, jenis file, jumlah baris, satuan, matriks
sumur x section x tipe, dan penyimpangan format per file.

Jalankan di LAPTOP (bukan di server sebelum login + HTTPS aktif). Hasil ditulis ke
folder --out; isi data tidak dicetak ke layar (aturan data client, Pasal 11).

    python scripts/audit_files.py data/raw --out docs/audit
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.parsers import column_map as cm  # noqa: E402
from app.parsers.workbook import parse_workbook  # noqa: E402
from app.services.classify import classify_section, classify_well_type  # noqa: E402

EXPECTED = {
    "wellplan": ["summary", "tripping", "off_bottom_torque", "survey", "bha"],
    "actual": ["actual_td", "actual_drilling", "actual_tripping"],
    "roadmap": ["roadmap_drag", "roadmap_torque"],
}


def audit_file(path: Path) -> dict:
    pw = parse_workbook(path)
    roles = {s.role for s in pw.sheets if s.role}
    missing = []
    for kind in sorted(pw.kinds):
        missing += [r for r in EXPECTED[kind] if r not in roles]
    ignored = [s.name for s in pw.sheets if s.role is None]
    hole = pw.meta.get("hole_size") or pw.meta.get("bit_size")
    wtype, type_warn = (None, None)
    if pw.survey:
        wtype, type_warn = classify_well_type([s.md for s in pw.survey], [s.inc for s in pw.survey])
    ffs = sorted({r.ff for r in pw.plan if r.ff is not None})
    act_ops = Counter(r.operation for r in pw.actual)
    units = sorted({u for s in pw.sheets for u in s.units})
    return {
        "file": path.name,
        "kinds": "+".join(sorted(pw.kinds)) or "-",
        "well": pw.meta.get("well_name") or "-",
        "section": classify_section(hole),
        "type": wtype or "-",
        "type_note": type_warn or "",
        "survey_points": len(pw.survey),
        "plan_points": len(pw.plan),
        "actual_points": len(pw.actual),
        "actual_by_op": dict(act_ops),
        "ff_scenarios": ffs,
        "units": units,
        "sheets": [(s.name, s.role or "diabaikan", s.rows) for s in pw.sheets],
        "missing_roles": missing,
        "ignored_sheets": ignored,
        "errors": [f"{i.location or '-'}: {i.message}" for i in pw.issues if i.level == "error"],
        "warnings": [
            f"{i.location or '-'}: {i.message}" for i in pw.issues if i.level == "warning"
        ],
    }


def write_report(rows: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "audit_files.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "jenis",
                "sumur",
                "section_in",
                "tipe",
                "titik_survey",
                "titik_wellplan",
                "titik_aktual",
                "skenario_ff",
                "satuan",
                "sheet_hilang",
                "jumlah_error",
                "jumlah_peringatan",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r["file"],
                    r["kinds"],
                    r["well"],
                    r["section"],
                    r["type"],
                    r["survey_points"],
                    r["plan_points"],
                    r["actual_points"],
                    " ".join(map(str, r["ff_scenarios"])),
                    " ".join(r["units"]),
                    " ".join(r["missing_roles"]),
                    len(r["errors"]),
                    len(r["warnings"]),
                ]
            )

    matrix: dict[tuple, set] = defaultdict(set)
    for r in rows:
        if r["actual_points"]:
            matrix[(r["section"], r["type"])].add(r["well"])
    sections = sorted({k[0] for k in matrix if k[0] is not None}, reverse=True)
    types = ["J", "S", "Horizontal"]

    L = [f"# Laporan audit data ({date.today().isoformat()})", ""]
    ok = [r for r in rows if not r["errors"]]
    L += [
        "## Ringkasan",
        "",
        f"- File diperiksa: **{len(rows)}**; terbaca tanpa error: **{len(ok)}**; "
        f"bermasalah: **{len(rows) - len(ok)}**",
        f"- Sumur dengan data aktual: **{len({r['well'] for r in rows if r['actual_points']})}**",
        f"- Satuan yang ditemukan: {', '.join(sorted({u for r in rows for u in r['units']})) or '-'}",
        f"- Skenario FF: {', '.join(sorted({str(f) for r in rows for f in r['ff_scenarios']})) or '-'}",
        "",
        "## Matriks sumur x section x tipe (sumur dengan data aktual)",
        "",
        "| Section | " + " | ".join(types) + " |",
        "|---|" + "---|" * len(types),
    ]
    for s in sections:
        cells = []
        for t in types:
            n = len(matrix.get((s, t), ()))
            cells.append(f"{n} ⚠" if 0 < n < 3 else str(n))
        L.append(f'| {s}" | ' + " | ".join(cells) + " |")
    L += ["", "⚠ = kurang dari 3 sumur: hasil model untuk kombinasi ini kurang andal.", ""]

    L += [
        "## Tabel per file",
        "",
        "| File | Jenis | Sumur | Section | Tipe | Survey | WellPlan | Aktual | FF | Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        status = (
            "GAGAL"
            if r["errors"]
            else ("peringatan" if r["warnings"] or r["missing_roles"] else "ok")
        )
        L.append(
            f"| {r['file']} | {r['kinds']} | {r['well']} | {r['section'] or '-'} | {r['type']} | "
            f"{r['survey_points']} | {r['plan_points']} | {r['actual_points']} | "
            f"{'/'.join(map(str, r['ff_scenarios'])) or '-'} | {status} |"
        )

    L += ["", "## Penyimpangan format per file", ""]
    any_issue = False
    for r in rows:
        items = [f"Error: {e}" for e in r["errors"]]
        items += [f"Sheet yang diharapkan tidak ada: {m}" for m in r["missing_roles"]]
        items += [f"Peringatan: {w}" for w in r["warnings"]]
        if r["type_note"]:
            items.append(f"Catatan tipe: {r['type_note']}")
        if r["ignored_sheets"]:
            items.append(f"Sheet diabaikan: {', '.join(r['ignored_sheets'])}")
        if items:
            any_issue = True
            L += [f"### {r['file']}", ""] + [f"- {i}" for i in items] + [""]
    if not any_issue:
        L.append("Tidak ada penyimpangan.")

    L += [
        "",
        "## Pertanyaan untuk narasumber",
        "",
        "- Arti dan satuan kolom yang ditandai peringatan di atas.",
        "- Definisi tipe sumur J / S / Horizontal (aturan otomatis: lihat docs/keputusan.md K-04).",
        "- Ambang selisih untuk penandaan interval di dashboard.",
        "- Skenario FF mana yang dipakai sebagai desain (baseline WellPlan, K-06).",
        "",
    ]
    (out / "laporan_audit.md").write_text("\n".join(L))

    # detail sheet per file (untuk lampiran)
    with (out / "audit_sheets.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sheet", "peran", "baris"])
        for r in rows:
            for name, role, n in r["sheets"]:
                w.writerow([r["file"], name, role, n])


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit file Excel client")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("docs/audit"))
    args = ap.parse_args()
    files = sorted(p for p in args.folder.rglob("*") if p.suffix.lower() in (".xlsx", ".xlsm"))
    if not files:
        print(f"Tidak ada file .xlsx/.xlsm di {args.folder}", file=sys.stderr)
        return 1
    rows = [audit_file(p) for p in files]
    write_report(rows, args.out)
    bad = sum(1 for r in rows if r["errors"])
    print(f"{len(rows)} file diaudit, {bad} bermasalah. Laporan: {args.out / 'laporan_audit.md'}")
    print(f"Peran sheet yang dikenali: {', '.join(cm.SHEET_ROLES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
