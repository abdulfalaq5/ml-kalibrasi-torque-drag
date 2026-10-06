"""user role (admin / guest)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06

Akun guest: hanya Monitoring + Dashboard, grafik tanpa kurva WellPlan (K-45).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_user",
        sa.Column("role", sa.String(length=16), nullable=False, server_default="admin"),
    )


def downgrade() -> None:
    op.drop_column("admin_user", "role")
