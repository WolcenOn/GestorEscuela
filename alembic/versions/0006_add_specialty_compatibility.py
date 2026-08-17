"""add specialty compatibility

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "school_teachers",
        sa.Column("specialties", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "school_activities",
        sa.Column("required_specialty", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("school_activities", "required_specialty")
    op.drop_column("school_teachers", "specialties")
