"""english status codes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04

Kode status internal dipindah ke bahasa Inggris (aplikasi full English, feedback client #1).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAPS = {
    ("uploaded_files", "status"): {
        "peringatan": "warning",
        "gagal": "failed",
        "diganti": "replaced",
        "dihapus": "deleted",
        "diproses": "processing",
    },
    ("wells", "status"): {"siap": "ready", "tanpa aktual": "no_actual", "baru": "new"},
    ("wells", "type_source"): {"otomatis": "auto"},
    ("wells", "section_source"): {"otomatis": "auto"},
    ("models", "status"): {
        "antri": "queued",
        "berjalan": "running",
        "selesai": "done",
        "ditahan": "held",
        "gagal": "failed",
    },
    ("scan_runs", "status"): {"berjalan": "running", "selesai": "done", "gagal": "failed"},
    ("quality_reviews", "decision"): {
        "terima": "accept",
        "kecualikan": "exclude",
        "perbaiki": "fix",
    },
    ("models", "algorithm"): {"semua": "all", "terbaik": "best"},
}


def _apply(reverse: bool) -> None:
    for (table, col), mapping in MAPS.items():
        for old, new in mapping.items():
            a, b = (new, old) if reverse else (old, new)
            op.execute(f"UPDATE {table} SET {col} = '{b}' WHERE {col} = '{a}'")


def upgrade() -> None:
    _apply(False)
    # daftar pemeriksaan kualitas disimpan sebagai JSON; dihitung ulang aplikasi (Recompute)
    op.execute("DELETE FROM well_quality")


def downgrade() -> None:
    _apply(True)
