"""add optional explicit time intervals to academic timetable slots

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Preserve existing slots: both new columns are nullable, never inferred
    # from label or slot order without an explicit school configuration.
    op.add_column("school_time_slots", sa.Column("start_time", sa.String(length=5)))
    op.add_column("school_time_slots", sa.Column("end_time", sa.String(length=5)))


def downgrade() -> None:
    op.drop_column("school_time_slots", "end_time")
    op.drop_column("school_time_slots", "start_time")
