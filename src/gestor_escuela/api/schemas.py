from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from gestor_escuela.domain.models import ActivityType, Priority, TeacherProfile


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class SchoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class GroupConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)


class TimeSlotConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    order: int = Field(ge=1)


class TeacherConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    profile: TeacherProfile
    substitution_count: int = Field(default=0, ge=0)
    can_cover_groups: set[str] = Field(default_factory=set)
    emergency_only: bool = False


class ActivityConfig(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    slot_id: str = Field(min_length=1, max_length=64)
    activity_type: ActivityType
    teacher_id: str = Field(min_length=1, max_length=64)
    group_id: str | None = Field(default=None, max_length=64)
    priority: Priority = Priority.NORMAL
    movable: bool = False
    cancelable: bool = False


class SchoolConfigurationPut(BaseModel):
    groups: list[GroupConfig] = Field(min_length=1)
    time_slots: list[TimeSlotConfig] = Field(min_length=1)
    teachers: list[TeacherConfig] = Field(min_length=1)
    activities: list[ActivityConfig] = Field(min_length=1)


class SchoolConfigurationRead(SchoolConfigurationPut):
    school_id: UUID


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
