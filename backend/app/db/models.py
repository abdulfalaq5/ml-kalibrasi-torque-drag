"""Model SQLAlchemy. Skema mengikuti TOOLS_dan_Arsitektur.md bagian 4.

Satuan: setiap nilai menyimpan nilai asli + satuan asli, dan nilai baku (SI) di
kolom `value_si`. Satuan baku internal: m (kedalaman), kN (beban), kN.m (torsi).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Well(Base):
    """Satu baris = satu sumur pada satu section (satu run WellPlan)."""

    __tablename__ = "wells"
    __table_args__ = (UniqueConstraint("name", "section_in", name="uq_well_name_section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    section_in: Mapped[float | None] = mapped_column(Float)
    well_type: Mapped[str | None] = mapped_column(String(16))  # J, S, Horizontal
    section_source: Mapped[str] = mapped_column(String(16), default="otomatis")
    type_source: Mapped[str] = mapped_column(String(16), default="otomatis")
    status: Mapped[str] = mapped_column(String(32), default="baru")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    files: Mapped[list["UploadedFile"]] = relationship(back_populates="well")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int | None] = mapped_column(ForeignKey("wells.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str | None] = mapped_column(String(32))  # wellplan, roadmap, actual
    path: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="diproses")  # ok, peringatan, gagal
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload | folder
    rel_path: Mapped[str | None] = mapped_column(String(512))  # jalur relatif di inbox
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    well: Mapped[Well | None] = relationship(back_populates="files")
    issues: Mapped[list["ValidationIssue"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(8))  # error, warning
    message: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(128))

    file: Mapped[UploadedFile] = relationship(back_populates="issues")


class Survey(Base):
    __tablename__ = "survey"
    __table_args__ = (Index("ix_survey_well_md", "well_id", "md_m"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    md_m: Mapped[float] = mapped_column(Float)
    inc_deg: Mapped[float] = mapped_column(Float)
    azi_deg: Mapped[float | None] = mapped_column(Float)
    tvd_m: Mapped[float | None] = mapped_column(Float)
    dls_deg_30m: Mapped[float | None] = mapped_column(Float)


class PlanResult(Base):
    __tablename__ = "plan_results"
    __table_args__ = (Index("ix_plan_well_op", "well_id", "operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(32))
    ff: Mapped[float | None] = mapped_column(Float)  # None = tidak bergantung FF
    source_sheet: Mapped[str] = mapped_column(String(64))
    depth_m: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    value_si: Mapped[float] = mapped_column(Float)


class ActualReading(Base):
    __tablename__ = "actual_readings"
    __table_args__ = (Index("ix_actual_well_op", "well_id", "operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(32))
    source_sheet: Mapped[str] = mapped_column(String(64))
    depth_m: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    value_si: Mapped[float] = mapped_column(Float)


class WellQuality(Base):
    """Hasil gerbang kualitas data per sumur-section (status A/B/C)."""

    __tablename__ = "well_quality"

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(1))  # A, B, C (otomatis)
    score: Mapped[int] = mapped_column(Integer)
    checks: Mapped[list] = mapped_column(JSON, default=list)  # [{code, level, message}]
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityReview(Base):
    """Keputusan tinjauan engineer: terima / kecualikan / perbaiki (riwayat, tidak dihapus)."""

    __tablename__ = "quality_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BlindSet(Base):
    """Sumur blind test: dikunci sebelum eksperimen, hanya dipakai sekali di akhir."""

    __tablename__ = "blind_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    wells: Mapped[list] = mapped_column(JSON, default=list)  # nama sumur
    seed: Mapped[int] = mapped_column(Integer, default=42)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Dataset(Base):
    """Versi dataset beku: daftar sumur + hash isi, snapshot CSV untuk diulang."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    blind_set_id: Mapped[int | None] = mapped_column(ForeignKey("blind_sets.id"))
    wells: Mapped[list] = mapped_column(JSON, default=list)
    excluded: Mapped[list] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    n_rows: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(512))
    notes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MLModel(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"))
    algorithm: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), default="antri"
    )  # antri, berjalan, selesai, gagal
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    path: Mapped[str | None] = mapped_column(String(512))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str | None] = mapped_column(Text)
    # hasil banding dengan model aktif saat selesai dilatih, dan hasil blind test (sekali)
    comparison: Mapped[dict] = mapped_column(JSON, default=dict)
    blind_result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    # "oof" = out-of-fold (sumur ikut training, model tidak pernah melihatnya)
    # "full" = model penuh untuk sumur baru
    kind: Mapped[str] = mapped_column(String(8), default="full")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    points: Mapped[list["PredictionPoint"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class PredictionPoint(Base):
    __tablename__ = "prediction_points"
    __table_args__ = (Index("ix_predpoint_pred_op", "prediction_id", "operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(32))
    depth_m: Mapped[float] = mapped_column(Float)
    wellplan_si: Mapped[float | None] = mapped_column(Float)
    ml_si: Mapped[float] = mapped_column(Float)

    prediction: Mapped[Prediction] = relationship(back_populates="points")


class PredictionEvaluation(Base):
    """Evaluasi otomatis prediksi sumur baru setelah data aktualnya diunggah."""

    __tablename__ = "prediction_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"))
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Limit(Base):
    """Batas aman dari client: per sumur atau per section (well_id kosong)."""

    __tablename__ = "limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int | None] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"))
    section_in: Mapped[float | None] = mapped_column(Float)
    operation: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(8))  # max | min
    value_si: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanRun(Base):
    """Riwayat pindai folder inbox (impor massal)."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="berjalan")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
