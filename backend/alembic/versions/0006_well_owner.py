"""well owner + user management (K-47)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12

Sumur monitoring punya pemilik; akun guest hanya melihat sumur miliknya, admin melihat semua.
Sumur lama tanpa pemilik hanya terlihat oleh admin sampai ditetapkan pemiliknya.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_user", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wells", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_wells_owner_id", "wells", "admin_user", ["owner_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_wells_owner_id", "wells", ["owner_id"])
    op.add_column("uploaded_files", sa.Column("uploaded_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_uploaded_files_uploaded_by",
        "uploaded_files",
        "admin_user",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_uploaded_files_uploaded_by", "uploaded_files", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_uploaded_by", table_name="uploaded_files")
    op.drop_constraint("fk_uploaded_files_uploaded_by", "uploaded_files", type_="foreignkey")
    op.drop_column("uploaded_files", "uploaded_by")
    op.drop_index("ix_wells_owner_id", table_name="wells")
    op.drop_constraint("fk_wells_owner_id", "wells", type_="foreignkey")
    op.drop_column("wells", "owner_id")
    op.drop_column("admin_user", "created_at")
