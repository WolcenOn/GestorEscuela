from __future__ import annotations

from datetime import date, datetime
from typing import Literal
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


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    created_at: datetime


class SchoolMembershipPut(BaseModel):
    user_id: UUID
    role: Literal["ADMIN", "PLANNER", "VIEWER"]


class SchoolMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    user_id: UUID
    role: str
    created_at: datetime


class GroupConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    stage: str | None = Field(default=None, max_length=80)
    tutor_teacher_id: str | None = Field(default=None, max_length=64)


class SubjectConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    required_specialty: str | None = Field(default=None, max_length=64)


class TimeSlotConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    order: int = Field(ge=1)


class TeacherConfig(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=160)
    profile: TeacherProfile
    substitution_count: int = Field(default=0, ge=0)
    can_cover_groups: set[str] = Field(default_factory=set)
    specialties: set[str] = Field(default_factory=set)
    emergency_only: bool = False


class ActivityConfig(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    weekday: int | None = Field(default=None, ge=0, le=4)
    slot_id: str = Field(min_length=1, max_length=64)
    activity_type: ActivityType
    teacher_id: str = Field(min_length=1, max_length=64)
    group_id: str | None = Field(default=None, max_length=64)
    subject_id: str | None = Field(default=None, max_length=64)
    required_specialty: str | None = Field(default=None, max_length=64)
    priority: Priority = Priority.NORMAL
    movable: bool = False
    cancelable: bool = False


class SchoolConfigurationPut(BaseModel):
    groups: list[GroupConfig] = Field(min_length=1)
    subjects: list[SubjectConfig] = Field(default_factory=list)
    time_slots: list[TimeSlotConfig] = Field(min_length=1)
    teachers: list[TeacherConfig] = Field(min_length=1)
    activities: list[ActivityConfig] = Field(default_factory=list)


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
    expected_version: int | None = Field(default=None, ge=1)


class DayPlanLifecycleRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class DayPlanCreateScoped(BaseModel):
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
    version: int
    source_hash: str | None
    notes: str | None
    payload: dict[str, object]
    created_at: datetime
    updated_at: datetime


class DayPlanRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_plan_id: UUID
    school_id: UUID
    actor_user_id: UUID | None
    version: int
    input_payload: dict[str, object]
    output_payload: dict[str, object]
    coverage_ratio: float
    score: int
    total_penalty: int
    wall_time_seconds: float
    created_at: datetime


class DayPlanEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_plan_id: UUID
    school_id: UUID
    actor_user_id: UUID | None
    version: int
    event_type: str
    from_status: str
    to_status: str
    reason: str | None
    created_at: datetime
