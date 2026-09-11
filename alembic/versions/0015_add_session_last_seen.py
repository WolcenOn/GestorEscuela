from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE auth_sessions SET last_seen_at = NOW() WHERE last_seen_at IS NULL")
    op.alter_column("auth_sessions", "last_seen_at", nullable=False)


def downgrade() -> None:
    op.drop_column("auth_sessions", "last_seen_at")
