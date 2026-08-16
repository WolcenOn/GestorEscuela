from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from gestor_escuela.persistence.db import Base


class DayPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    SOLVED = "SOLVED"
    CONFIRMED = "CONFIRMED"


class SchoolRow(Base):
    __tablename__ = "schools"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    day_plans: Mapped[list[DayPlanRow]] = relationship(back_populates="school")


class SchoolGroupRow(Base):
    __tablename__ = "school_groups"
    __table_args__ = (
        UniqueConstraint("school_id", "external_id", name="uq_group_school_external"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)


class SchoolTimeSlotRow(Base):
    __tablename__ = "school_time_slots"
    __table_args__ = (
        UniqueConstraint("school_id", "external_id", name="uq_slot_school_external"),
        UniqueConstraint("school_id", "slot_order", name="uq_slot_school_order"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    slot_order: Mapped[int] = mapped_column(Integer, nullable=False)


class SchoolTeacherRow(Base):
    __tablename__ = "school_teachers"
    __table_args__ = (
        UniqueConstraint("school_id", "external_id", name="uq_teacher_school_external"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[str] = mapped_column(String(32), nullable=False)
    substitution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    can_cover_groups: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    emergency_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SchoolActivityRow(Base):
    __tablename__ = "school_activities"
    __table_args__ = (
        UniqueConstraint("school_id", "external_id", name="uq_activity_school_external"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(96), nullable=False)
    slot_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    teacher_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_external_id: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    movable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancelable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DayPlanRow(Base):
    __tablename__ = "day_plans"
    __table_args__ = (UniqueConstraint("school_id", "plan_date", name="uq_day_plan_school_date"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DayPlanStatus.DRAFT.value
    )
    source_hash: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    school: Mapped[SchoolRow] = relationship(back_populates="day_plans")
