"""create operational school configuration

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "school_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "external_id", name="uq_group_school_external"),
    )
    op.create_table(
        "school_time_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "external_id", name="uq_slot_school_external"),
        sa.UniqueConstraint("school_id", "slot_order", name="uq_slot_school_order"),
    )
    op.create_table(
        "school_teachers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=32), nullable=False),
        sa.Column("substitution_count", sa.Integer(), nullable=False),
        sa.Column("can_cover_groups", postgresql.JSONB(), nullable=False),
        sa.Column("emergency_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "external_id", name="uq_teacher_school_external"),
    )
    op.create_table(
        "school_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=96), nullable=False),
        sa.Column("slot_external_id", sa.String(length=64), nullable=False),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("teacher_external_id", sa.String(length=64), nullable=False),
        sa.Column("group_external_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("movable", sa.Boolean(), nullable=False),
        sa.Column("cancelable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "external_id", name="uq_activity_school_external"),
    )


def downgrade() -> None:
    op.drop_table("school_activities")
    op.drop_table("school_teachers")
    op.drop_table("school_time_slots")
    op.drop_table("school_groups")
