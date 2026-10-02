"""Impor satu file Excel ke database: parse, validasi, klasifikasi, simpan."""

import hashlib
import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import delete, select
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


def import_file(
    db: Session,
    path: Path,
    original_name: str,
    checksum: str,
    well_name: str | None = None,
    section_in: float | None = None,
) -> UploadedFile:
    existing = db.scalar(
        select(UploadedFile).where(
            UploadedFile.checksum == checksum, UploadedFile.status != "gagal"
        )
    )
    if existing is not None:
        return existing

    uf = UploadedFile(filename=original_name, path=str(path), checksum=checksum, status="diproses")
    db.add(uf)
    db.flush()

    pw = parse_workbook(path, original_name)
    uf.kind = "+".join(sorted(pw.kinds)) or None

    name = (well_name or pw.meta.get("well_name") or _name_from_filename(original_name)).strip()
    hole = section_in or pw.meta.get("hole_size") or pw.meta.get("bit_size")
    if hole is None:
        hole = _section_from_filename(original_name)
    section = classify_section(hole)

    if not pw.has_errors and section is None and pw.plan:
        pw.warn("Ukuran lubang/section tidak ditemukan; isi manual di daftar sumur")

    if pw.has_errors:
        uf.status = "gagal"
        _save_issues(db, uf, pw)
        uf.summary = _summary(pw)
        db.commit()
        return uf

    well = _get_or_create_well(db, name, section)
    uf.well_id = well.id
    _replace_previous(db, well, uf, pw)
    _save_data(db, well, uf, pw)
    _classify(db, well, pw)

    uf.status = "peringatan" if pw.issues else "ok"
    _save_issues(db, uf, pw)
    uf.summary = _summary(pw)
    well.status = "siap" if _has_actual(db, well) else "tanpa aktual"
    db.commit()
    log.info("Impor %s -> sumur %s (%s): %s", original_name, well.name, section, uf.status)
    return uf


def _name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    return re.split(r"[_\s]+", stem)[0] or stem


def _section_from_filename(filename: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:in|inch|\")", filename.lower())
    return float(m.group(1).replace(",", ".")) if m else None


def _get_or_create_well(db: Session, name: str, section: float | None) -> Well:
    q = select(Well).where(Well.name == name)
    q = q.where(Well.section_in.is_(None) if section is None else Well.section_in == section)
    well = db.scalar(q)
    if well is None:
        well = Well(name=name, section_in=section, meta={})
        db.add(well)
        db.flush()
    return well


def _replace_previous(db: Session, well: Well, uf: UploadedFile, pw: ParsedWorkbook) -> None:
    """File baru dengan jenis yang sama untuk sumur yang sama menggantikan file lama."""
    olds = db.scalars(
        select(UploadedFile).where(
            UploadedFile.well_id == well.id,
            UploadedFile.id != uf.id,
            UploadedFile.kind == uf.kind,
            UploadedFile.status != "gagal",
        )
    ).all()
    for old in olds:
        for model in (Survey, PlanResult, ActualReading):
            db.execute(delete(model).where(model.file_id == old.id))
        old.status = "diganti"


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
    # kedalaman duplikat: nilai terakhir dipakai
    for rows, model in ((pw.plan, PlanResult), (pw.actual, ActualReading)):
        dedup: dict[tuple, object] = {}
        for r in rows:
            dedup[(r.operation, r.ff, r.sheet, r.depth)] = r
        for r in dedup.values():
            kw = dict(
                well_id=well.id,
                file_id=uf.id,
                operation=r.operation,
                source_sheet=r.sheet,
                depth_m=units.to_si(r.depth, r.depth_unit),
                value=r.value,
                unit=r.unit,
                value_si=units.to_si(r.value, r.unit),
            )
            if model is PlanResult:
                kw["ff"] = r.ff
            db.add(model(**kw))
    meta = dict(well.meta or {})
    for k in ("field", "casing_shoe", "casing_shoe_unit", "bha_components", "hole_size"):
        if k in pw.meta:
            meta[k] = pw.meta[k]
    well.meta = meta
    db.flush()


def _classify(db: Session, well: Well, pw: ParsedWorkbook) -> None:
    if well.type_source == "manual":
        return
    if pw.meta.get("well_type"):
        t = _normalize_type(pw.meta["well_type"])
        if t:
            well.well_type = t
            well.type_source = "file"
            return
    if pw.survey:
        t, warn = classify_well_type([s.md for s in pw.survey], [s.inc for s in pw.survey])
        if t:
            well.well_type = t
            well.type_source = "otomatis"
        if warn:
            pw.warn(warn)
    elif well.well_type is None and "wellplan" in pw.kinds:
        pw.warn("Tidak ada survey; tipe sumur harus diisi manual")


def _normalize_type(raw: str) -> str | None:
    r = raw.strip().lower()
    if r.startswith("h"):
        return "Horizontal"
    if r.startswith("s"):
        return "S"
    if r.startswith("j"):
        return "J"
    return None


def _has_actual(db: Session, well: Well) -> bool:
    return (
        db.scalar(select(ActualReading.id).where(ActualReading.well_id == well.id).limit(1))
        is not None
    )


def _save_issues(db: Session, uf: UploadedFile, pw: ParsedWorkbook) -> None:
    for i in pw.issues:
        db.add(
            ValidationIssue(file_id=uf.id, level=i.level, message=i.message, location=i.location)
        )


def _summary(pw: ParsedWorkbook) -> dict:
    return {
        "kinds": sorted(pw.kinds),
        "meta": {k: v for k, v in pw.meta.items()},
        "survey_points": len(pw.survey),
        "plan_points": len(pw.plan),
        "actual_points": len(pw.actual),
        "sheets": [
            {"name": s.name, "role": s.role, "rows": s.rows, "units": s.units} for s in pw.sheets
        ],
    }
