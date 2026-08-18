"""add academic timetable fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("school_groups", sa.Column("stage", sa.String(length=80), nullable=True))
    op.add_column(
        "school_groups",
        sa.Column("tutor_teacher_external_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "school_teachers", sa.Column("display_name", sa.String(length=160), nullable=True)
    )
    op.create_table(
        "school_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("required_specialty", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id", "external_id", name="uq_subject_school_external"),
    )
    op.add_column("school_activities", sa.Column("weekday", sa.Integer(), nullable=True))
    op.add_column(
        "school_activities",
        sa.Column("subject_external_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("school_activities", "subject_external_id")
    op.drop_column("school_activities", "weekday")
    op.drop_table("school_subjects")
    op.drop_column("school_teachers", "display_name")
    op.drop_column("school_groups", "tutor_teacher_external_id")
    op.drop_column("school_groups", "stage")
