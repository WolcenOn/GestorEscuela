from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planning_scenario_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("academic_year_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["planning_scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scenario_id"),
    )
    op.create_index(
        "ix_planning_scenario_snapshots_academic_year_id",
        "planning_scenario_snapshots",
        ["academic_year_id"],
        unique=False,
    )
    op.create_index(
        "ix_planning_scenario_snapshots_school_id",
        "planning_scenario_snapshots",
        ["school_id"],
        unique=False,
    )
    op.create_index(
        "ix_planning_scenario_snapshots_scenario_id",
        "planning_scenario_snapshots",
        ["scenario_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_scenario_snapshots_scenario_id",
        table_name="planning_scenario_snapshots",
    )
    op.drop_index(
        "ix_planning_scenario_snapshots_school_id",
        table_name="planning_scenario_snapshots",
    )
    op.drop_index(
        "ix_planning_scenario_snapshots_academic_year_id",
        table_name="planning_scenario_snapshots",
    )
    op.drop_table("planning_scenario_snapshots")
