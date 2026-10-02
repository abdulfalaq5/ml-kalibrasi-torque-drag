"""Buat salinan anonim file Excel client untuk dipakai dengan alat AI / sebagai fixture.

Nama sumur, lapangan, perusahaan, rig, dan koordinat diganti kode (W01, FLD-A, ...).
Setiap sel teks yang memuat nama asli juga diganti. Tabel pemetaan disimpan di
--map (JANGAN dibagikan; tetap di laptop, di luar Git).

Salinan disimpan sebagai .xlsx tanpa macro dan tanpa gambar/grafik.
PERIKSA MANUAL hasilnya: nama asli di judul file roadmap (tanpa sheet Summary) atau di
nama sheet tidak terdeteksi otomatis.

    python scripts/anonymize_files.py data/raw --out data/anon --map data/peta_anonim.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import openpyxl

KEYS = {
    "well": [r"^well( name)?\s*:?$", r"^nama sumur", r"^wellbore( name)?\s*:?$"],
    "field": [r"^field\s*:?$", r"^lapangan"],
    "company": [r"^company\s*:?$", r"^operator\s*:?$", r"^perusahaan"],
    "rig": [r"^rig( name)?\s*:?$"],
    "coord": [r"latitude", r"longitude", r"easting", r"northing", r"koordinat", r"^location"],
}
PREFIX = {"well": "W", "field": "FLD-", "company": "CO-", "rig": "RIG-"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/anon"))
    ap.add_argument("--map", type=Path, default=Path("data/peta_anonim.csv"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    mapping: dict[tuple[str, str], str] = {}
    if args.map.exists():
        with args.map.open() as f:
            for row in csv.DictReader(f):
                mapping[(row["jenis"], row["asli"])] = row["kode"]

    def code(kind: str, original: str) -> str:
        key = (kind, original.strip())
        if key not in mapping:
            n = sum(1 for k in mapping if k[0] == kind) + 1
            mapping[key] = (
                f"{PREFIX[kind]}{n:02d}" if kind == "well" else f"{PREFIX[kind]}{chr(64 + n)}"
            )
        return mapping[key]

    files = sorted(p for p in args.folder.rglob("*") if p.suffix.lower() in (".xlsx", ".xlsm"))
    for path in files:
        wb = openpyxl.load_workbook(path, keep_vba=False)
        found: dict[str, str] = {}
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for j, c in enumerate(row):
                    label = str(c.value or "").strip().lower()
                    for kind, pats in KEYS.items():
                        if not any(re.search(p, label) for p in pats):
                            continue
                        val = next((x for x in row[j + 1 :] if x.value not in (None, "")), None)
                        if val is None:
                            continue
                        if kind == "coord":
                            val.value = "dihapus"
                        else:
                            found[str(val.value).strip()] = code(kind, str(val.value))
                            val.value = found[str(val.value).strip()]
        # ganti nama asli di sel teks lain (judul, catatan)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str):
                        for orig, new in found.items():
                            if orig and orig in c.value:
                                c.value = c.value.replace(orig, new)
        well_code = next((v for k, v in found.items() if v.startswith("W")), None)
        name = f"{well_code or 'XX'}_{len(list(args.out.iterdir())) + 1:03d}.xlsx"
        wb.save(args.out / name)
        print(f"{path.name} -> {name}")

    args.map.parent.mkdir(parents=True, exist_ok=True)
    with args.map.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["jenis", "asli", "kode"])
        for (kind, orig), c in sorted(mapping.items()):
            w.writerow([kind, orig, c])
    print(f"Peta anonim: {args.map} (jangan dibagikan)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
