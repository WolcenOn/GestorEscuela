from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from gestor_escuela.persistence.db import Base


class SchoolRecessShiftRow(Base):
    __tablename__ = "school_recess_shifts"
    __table_args__ = (
        UniqueConstraint("school_id", "external_id", name="uq_recess_shift_school_external"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(96), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    required_staff: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assigned_teacher_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class SchoolScheduledActivityRow(Base):
    __tablename__ = "school_scheduled_activities"
    __table_args__ = (
        UniqueConstraint(
            "school_id", "external_id", name="uq_scheduled_activity_school_external"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(96), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    weekday: Mapped[int | None] = mapped_column(Integer)
    activity_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    required_staff: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assigned_teacher_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    movable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cancelable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
