from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class RecessShiftConfig(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    label: str = Field(min_length=1, max_length=160)
    weekday: int = Field(ge=0, le=4)
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    location: str | None = Field(default=None, max_length=160)
    required_staff: int = Field(default=1, ge=1, le=50)
    assigned_teacher_ids: set[str] = Field(default_factory=set)
    active: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def validate_times(self) -> RecessShiftConfig:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ScheduledActivityConfig(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    label: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=64)
    weekday: int | None = Field(default=None, ge=0, le=4)
    activity_date: date | None = None
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    location: str | None = Field(default=None, max_length=160)
    required_staff: int = Field(default=1, ge=1, le=50)
    assigned_teacher_ids: set[str] = Field(default_factory=set)
    movable: bool = True
    cancelable: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> ScheduledActivityConfig:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if (self.weekday is None) == (self.activity_date is None):
            raise ValueError("set exactly one of weekday or activity_date")
        return self


class OperationsConfigurationPut(BaseModel):
    recess_shifts: list[RecessShiftConfig] = Field(default_factory=list)
    scheduled_activities: list[ScheduledActivityConfig] = Field(default_factory=list)


class OperationsConfigurationRead(OperationsConfigurationPut):
    school_id: UUID
