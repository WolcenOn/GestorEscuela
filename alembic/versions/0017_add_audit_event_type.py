from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("event_type", sa.String(length=80), nullable=True),
    )
    op.execute("UPDATE audit_logs SET event_type = 'http.mutation' WHERE event_type IS NULL")
    op.alter_column("audit_logs", "event_type", nullable=False)
    op.create_index(
        op.f("ix_audit_logs_event_type"),
        "audit_logs",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_event_type"), table_name="audit_logs")
    op.drop_column("audit_logs", "event_type")
