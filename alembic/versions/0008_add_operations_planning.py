from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "school_recess_shifts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("school_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=96), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("required_staff", sa.Integer(), nullable=False),
        sa.Column(
            "assigned_teacher_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "school_id", "external_id", name="uq_recess_shift_school_external"
        ),
    )
    op.create_table(
        "school_scheduled_activities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("school_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=96), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("activity_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("required_staff", sa.Integer(), nullable=False),
        sa.Column(
            "assigned_teacher_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("movable", sa.Boolean(), nullable=False),
        sa.Column("cancelable", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "school_id", "external_id", name="uq_scheduled_activity_school_external"
        ),
    )


def downgrade() -> None:
    op.drop_table("school_scheduled_activities")
    op.drop_table("school_recess_shifts")
