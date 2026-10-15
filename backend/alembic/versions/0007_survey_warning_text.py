"""teks peringatan tanpa survey untuk orang awam

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15

Peringatan disimpan bersama prediksi (predictions.warnings), jadi teks lama diganti di data
(dua varian lama: "... better prediction)" dan "... better forecast)").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_PREFIX = "No survey: inclination/dogleg features use the training median"
OLD = OLD_PREFIX + " (fill in the Survey sheet for a better prediction)"
NEW = (
    "No well path (survey) data in this file: the prediction assumes an average well path, "
    "so it may be less accurate where the hole bends or is steeply inclined. "
    "Upload the file again with the Survey sheet filled in for a more accurate prediction."
)


def _replace(match, new: str) -> None:
    t = sa.table("predictions", sa.column("id", sa.Integer), sa.column("warnings", sa.JSON))
    conn = op.get_bind()
    for pid, warns in conn.execute(sa.select(t.c.id, t.c.warnings)).all():
        if warns and any(isinstance(w, str) and match(w) for w in warns):
            fixed = [new if isinstance(w, str) and match(w) else w for w in warns]
            conn.execute(t.update().where(t.c.id == pid).values(warnings=fixed))


def upgrade() -> None:
    _replace(lambda w: w.startswith(OLD_PREFIX), NEW)


def downgrade() -> None:
    _replace(lambda w: w == NEW, OLD)
