"""add users and school memberships

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "school_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "user_id", name="uq_membership_school_user"),
    )
    op.add_column(
        "day_plan_runs",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_day_plan_runs_actor_user",
        "day_plan_runs",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "day_plan_events",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_day_plan_events_actor_user",
        "day_plan_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_day_plan_events_actor_user",
        "day_plan_events",
        type_="foreignkey",
    )
    op.drop_column("day_plan_events", "actor_user_id")
    op.drop_constraint(
        "fk_day_plan_runs_actor_user",
        "day_plan_runs",
        type_="foreignkey",
    )
    op.drop_column("day_plan_runs", "actor_user_id")
    op.drop_table("school_memberships")
    op.drop_table("users")
