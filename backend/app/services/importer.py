"""Impor satu file Excel ke database: parse, validasi, klasifikasi, simpan.

Dipakai oleh unggah manual (api/files.py) dan impor massal folder (services/inbox.py).
Setelah impor: kualitas data sumur dihitung ulang, dan prediksi lama sumur itu
dievaluasi otomatis bila data aktualnya baru masuk.
"""

import hashlib
import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    ActualReading,
    PlanResult,
    Survey,
    UploadedFile,
    ValidationIssue,
    Well,
)
from app.parsers.common import ParsedWorkbook
from app.parsers.workbook import parse_workbook
from app.services import units
from app.services.classify import classify_section, classify_well_type

log = logging.getLogger(__name__)

ALLOWED_EXT = {".xlsx", ".xlsm"}
META_KEYS = (
    "field",
    "client",
    "rig",
    "run",
    "block_weight_klbf",
    "mud_weight_ppg",
    "bha_length_ft",
    "bha_weight_klbf",
    "bha_components",
    "bit_size_in",
    "hole_size_in",
    "dp_od_in",
    "dp_weight_ppf",
    "casing_shoe",
    "casing_shoe_unit",
    "calibration_drag_klbf",
    "calibration_torque_ftlbf",
    "ff_scenarios",
    "base_ff",
    "section_meta",
    "plan_depth_m",
    "actual_depth_m",
    "drilling_range_ft",
    "drilling_torque_unit_assumed",
    "well_name",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:200] or "file.xlsx"


def store_upload(src: Path, original_name: str) -> tuple[Path, str]:
    settings = get_settings()
    checksum = sha256(src)
    dest_dir = settings.upload_dir / checksum[:2]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{checksum[:16]}_{safe_filename(original_name)}"
    if not dest.exists():
        shutil.copyfile(src, dest)
    return dest, checksum


def find_by_checksum(db: Session, checksum: str) -> UploadedFile | None:
    return db.scalar(
        select(UploadedFile).where(
            UploadedFile.checksum == checksum,
            UploadedFile.status.in_(["ok", "peringatan"]),
        )
    )


def import_file(
    db: Session,
    path: Path,
    original_name: str,
    checksum: str,
    well_name: str | None = None,
    section_in: float | None = None,
    rel_path: str | None = None,
    source: str = "upload",
    well_type: str | None = None,
) -> UploadedFile:
    existing = find_by_checksum(db, checksum)
    if existing is not None:
        return existing

    uf = UploadedFile(
        filename=original_name,
        path=str(path),
        checksum=checksum,
        status="diproses",
        source=source,
        rel_path=rel_path,
    )
    db.add(uf)
    db.flush()

    pw = parse_workbook(path, original_name, rel_path)
    uf.kind = pw.fmt
    meta = pw.meta

    name = (
        well_name
        or meta.get("well_folder")
        or (meta.get("well_name") if meta.get("template") else None)
        or meta.get("well_name")
        or _name_from_filename(original_name)
    ).strip()
    if meta.get("template") and not (well_name or meta.get("well_name")):
        pw.warn("Nama sumur di sheet 'Info Sumur' kosong; dipakai nama file")
    section = classify_section(
        section_in
        or meta.get("section_template")
        or meta.get("section_from_filename")
        or meta.get("hole_size_in")
        or meta.get("bit_size_in")
        or meta.get("section_meta_in")
    )
    meta_sec = classify_section(meta.get("section_meta_in"))
    if section and meta_sec and meta_sec != section:
        pw.warn(
            f'Section di sheet aktual ({meta.get("section_meta")}) berbeda dengan nama file '
            f'({section:g}"); dipakai nilai dari nama file'
        )
    if not pw.has_errors and section is None:
        pw.error("Section (ukuran lubang) tidak ditemukan; isi kolom Section saat unggah")

    if pw.has_errors:
        uf.status = "gagal"
        _save_issues(db, uf, pw)
        uf.summary = _summary(pw)
        db.commit()
        return uf

    well = _get_or_create_well(db, name, section)
    uf.well_id = well.id
    uf.version = _replace_previous(db, well, uf)
    _save_data(db, well, uf, pw)
    _classify(well, pw, well_type)

    uf.status = "peringatan" if pw.issues else "ok"
    _save_issues(db, uf, pw)
    uf.summary = _summary(pw)
    has_actual = _has_actual(db, well)
    well.status = "siap" if has_actual else "tanpa aktual"
    db.commit()
    log.info("Impor %s -> sumur %s (%s): %s", original_name, well.name, section, uf.status)

    # setelah impor: kualitas data + evaluasi prediksi lama (impor lokal agar tidak siklik)
    from app.services.evaluation import evaluate_well_predictions
    from app.services.quality import evaluate_well

    evaluate_well(db, well)
    if pw.actual:
        evaluate_well_predictions(db, well)
    return uf


def _name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    m = re.match(r"(P_[A-Za-z]+\d+_\d+[A-Za-z]*)", stem)
    if m:
        return m.group(1)
    return re.split(r"[_\s]+", stem)[0] or stem


def _get_or_create_well(db: Session, name: str, section: float | None) -> Well:
    q = select(Well).where(Well.name == name)
    q = q.where(Well.section_in.is_(None) if section is None else Well.section_in == section)
    well = db.scalar(q)
    if well is None:
        well = Well(name=name, section_in=section, meta={})
        db.add(well)
        db.flush()
    return well


def _replace_previous(db: Session, well: Well, uf: UploadedFile) -> int:
    """File baru untuk sumur-section yang sama menggantikan file lama (versi naik)."""
    olds = db.scalars(
        select(UploadedFile).where(
            UploadedFile.well_id == well.id,
            UploadedFile.id != uf.id,
            UploadedFile.status.in_(["ok", "peringatan"]),
        )
    ).all()
    version = 1
    for old in olds:
        for model in (Survey, PlanResult, ActualReading):
            db.execute(delete(model).where(model.file_id == old.id))
        old.status = "diganti"
        version = max(version, (old.version or 1) + 1)
    return version


def _save_data(db: Session, well: Well, uf: UploadedFile, pw: ParsedWorkbook) -> None:
    su = pw.survey_units
    for s in pw.survey:
        db.add(
            Survey(
                well_id=well.id,
                file_id=uf.id,
                md_m=units.to_si(s.md, su.get("md", "ft")),
                inc_deg=s.inc,
                azi_deg=s.azi,
                tvd_m=units.to_si(s.tvd, su.get("tvd", "ft")) if s.tvd is not None else None,
                dls_deg_30m=units.to_si(s.dls, su.get("dls", "deg/100ft"))
                if s.dls is not None
                else None,
            )
        )
    # kedalaman duplikat dalam satu seri: nilai terakhir dipakai (dicatat oleh gerbang kualitas)
    for rows, model in ((pw.plan, PlanResult), (pw.actual, ActualReading)):
        dedup: dict[tuple, object] = {}
        for r in rows:
            dedup[(r.operation, r.ff, r.sheet, r.depth)] = r
        db.add_all(
            model(
                well_id=well.id,
                file_id=uf.id,
                operation=r.operation,
                source_sheet=r.sheet,
                depth_m=units.to_si(r.depth, r.depth_unit),
                value=r.value,
                unit=r.unit,
                value_si=units.to_si(r.value, r.unit),
                **({"ff": r.ff} if model is PlanResult else {}),
            )
            for r in dedup.values()
        )
    meta = dict(well.meta or {})
    meta["plan_format"] = pw.fmt
    for k in META_KEYS:
        if k in pw.meta:
            meta[k] = pw.meta[k]
    if pw.fmt == "roadmap" and "casing_shoe" not in pw.meta and pw.meta.get("plan_depth_m"):
        # roadmap tidak memuat kedalaman shoe; puncak section ~ shoe section sebelumnya (K-18)
        top_m = pw.meta["plan_depth_m"][0]
        meta["casing_shoe"] = round(top_m / units.FT_TO_M, 1)
        meta["casing_shoe_unit"] = "ft"
        meta["casing_shoe_source"] = "puncak rencana section"
    elif "casing_shoe" in pw.meta:
        meta["casing_shoe_source"] = "wellbore WellPlan"
    well.meta = meta
    db.flush()


def _classify(well: Well, pw: ParsedWorkbook, override: str | None = None) -> None:
    if override:
        well.well_type, well.type_source = override, "manual"
        return
    if well.type_source == "manual":
        return
    if pw.meta.get("well_type_template"):
        well.well_type, well.type_source = pw.meta["well_type_template"], "template"
        return
    if pw.meta.get("well_type_folder"):
        well.well_type = pw.meta["well_type_folder"]
        well.type_source = "folder"
        if pw.survey:
            t, _ = classify_well_type([s.md for s in pw.survey], [s.inc for s in pw.survey])
            if t and t != well.well_type and well.well_type != "Horizontal":
                pw.warn(
                    f"Tipe dari folder ({well.well_type}) berbeda dengan survey ({t}); "
                    "dipakai tipe dari folder"
                )
        return
    if pw.survey:
        t, warn = classify_well_type([s.md for s in pw.survey], [s.inc for s in pw.survey])
        if t:
            well.well_type = t
            well.type_source = "otomatis"
        if warn:
            pw.warn(warn)
    elif well.well_type is None:
        pw.warn(
            "Tipe sumur tidak diketahui (roadmap tanpa survey, bukan dari folder tipe); isi manual"
        )


def _has_actual(db: Session, well: Well) -> bool:
    return (
        db.scalar(select(func.count(ActualReading.id)).where(ActualReading.well_id == well.id)) or 0
    ) > 0


def _save_issues(db: Session, uf: UploadedFile, pw: ParsedWorkbook) -> None:
    for i in pw.issues:
        db.add(
            ValidationIssue(file_id=uf.id, level=i.level, message=i.message, location=i.location)
        )


def _summary(pw: ParsedWorkbook) -> dict:
    return {
        "format": pw.fmt,
        "kinds": sorted(pw.kinds),
        "meta": {k: v for k, v in pw.meta.items() if k in META_KEYS or k.startswith("section")},
        "survey_points": len(pw.survey),
        "plan_points": len(pw.plan),
        "actual_points": len(pw.actual),
        "sheets": [{"name": s.name, "role": s.role, "rows": s.rows} for s in pw.sheets],
    }
