from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AcademicYearCreate(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> AcademicYearCreate:
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        return self


class AcademicYearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    label: str
    start_date: date | None
    end_date: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class PlanningScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class PlanningScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    academic_year_id: UUID
    name: str
    status: str
    version: int
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
