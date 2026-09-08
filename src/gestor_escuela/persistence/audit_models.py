from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gestor_escuela.persistence.db import Base


class AuditLogRow(Base):
    """Minimal append-only metadata about mutating API requests.

    Request/response bodies are deliberately not stored here so that the audit trail does not
    become a shadow copy of student, staff or timetable data.
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, index=True, default=uuid4
    )
    school_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
