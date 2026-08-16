from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class SchoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class AbsenceInput(BaseModel):
    teacher_id: str = Field(min_length=1)
    slot_ids: set[str] = Field(min_length=1)


class LockedSubstitutionInput(BaseModel):
    activity_id: str = Field(min_length=1)
    substitute_teacher_id: str = Field(min_length=1)


class DayPlanSolveRequest(BaseModel):
    absences: list[AbsenceInput] = Field(min_length=1)
    locked_substitutions: list[LockedSubstitutionInput] = Field(default_factory=list)


class DayPlanCreate(BaseModel):
    school_id: UUID
    plan_date: date
    source_hash: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class DayPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    plan_date: date
    status: str
    source_hash: str | None
    notes: str | None
    payload: dict[str, object]
    created_at: datetime
    updated_at: datetime
