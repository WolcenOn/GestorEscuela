from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gestor_escuela.api.auth import PlannerDep, SessionDep
from gestor_escuela.persistence.models import SchoolRow
from gestor_escuela.solver.staffing import (
    StaffingActivity,
    StaffingOptimizer,
    StaffingRequirement,
    StaffingTeacher,
)

router = APIRouter()


class StaffingTeacherInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    role: Literal["generalista", "especialista", "mixto"] = "generalista"
    available_minutes: int = Field(ge=0, le=10_000)
    allowed_subjects: set[str] = Field(default_factory=set)
    specialty_subjects: set[str] = Field(default_factory=set)
    tutor_preference: Literal["preferente", "disponible", "evitar", "no"] = "disponible"
    fixed_tutor_group: str | None = Field(default=None, max_length=120)
    minimum_tutor_minutes: int = Field(default=0, ge=0, le=3_000)


class StaffingRequirementInput(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    group_id: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=160)
    minutes: int = Field(gt=0, le=3_000)
    fixed_teacher_id: str | None = Field(default=None, max_length=64)


class StaffingActivityInput(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=180)
    minutes: int = Field(gt=0, le=3_000)
    required_staff: int = Field(default=1, ge=1, le=30)
    fixed_teacher_ids: set[str] = Field(default_factory=set)
    eligible_teacher_ids: set[str] = Field(default_factory=set)
    group_ids: set[str] = Field(default_factory=set)


class StaffingSolveRequest(BaseModel):
    group_ids: list[str] = Field(min_length=1)
    teachers: list[StaffingTeacherInput] = Field(min_length=1)
    requirements: list[StaffingRequirementInput] = Field(default_factory=list)
    activities: list[StaffingActivityInput] = Field(default_factory=list)


class StaffingAssignmentRead(BaseModel):
    requirement_id: str
    group_id: str
    subject: str
    minutes: int
    teacher_id: str


class StaffingActivityAssignmentRead(BaseModel):
    activity_id: str
    activity_name: str
    minutes: int
    teacher_id: str


class TutorAssignmentRead(BaseModel):
    group_id: str
    teacher_id: str


class StaffingTeacherLoadRead(BaseModel):
    teacher_id: str
    assigned_minutes: int
    teaching_minutes: int
    activity_minutes: int
    available_minutes: int
    remaining_minutes: int
    groups_taught: int
    tutor_group: str | None


class StaffingSolveResponse(BaseModel):
    complete: bool
    assignments: list[StaffingAssignmentRead]
    activity_assignments: list[StaffingActivityAssignmentRead]
    tutors: list[TutorAssignmentRead]
    uncovered_requirement_ids: list[str]
    uncovered_activity_ids: list[str]
    uncovered_tutor_groups: list[str]
    teacher_loads: list[StaffingTeacherLoadRead]
    objective_value: float
    wall_time_seconds: float


@router.post(
    "/schools/{school_id}/staffing/solve",
    response_model=StaffingSolveResponse,
)
def solve_staffing(
    school_id: UUID,
    request: StaffingSolveRequest,
    session: SessionDep,
    _actor: PlannerDep,
) -> StaffingSolveResponse:
    if session.get(SchoolRow, school_id) is None:
        raise HTTPException(status_code=404, detail="School not found")

    teachers = tuple(
        StaffingTeacher(
            id=item.id,
            name=item.name,
            role=item.role,
            available_minutes=item.available_minutes,
            allowed_subjects=frozenset(item.allowed_subjects),
            specialty_subjects=frozenset(item.specialty_subjects),
            tutor_preference=item.tutor_preference,
            fixed_tutor_group=item.fixed_tutor_group,
            minimum_tutor_minutes=item.minimum_tutor_minutes,
        )
        for item in request.teachers
    )
    requirements = tuple(
        StaffingRequirement(
            id=item.id,
            group_id=item.group_id,
            subject=item.subject,
            minutes=item.minutes,
            fixed_teacher_id=item.fixed_teacher_id,
        )
        for item in request.requirements
    )
    activities = tuple(
        StaffingActivity(
            id=item.id,
            name=item.name,
            minutes=item.minutes,
            required_staff=item.required_staff,
            fixed_teacher_ids=frozenset(item.fixed_teacher_ids),
            eligible_teacher_ids=frozenset(item.eligible_teacher_ids),
            group_ids=frozenset(item.group_ids),
        )
        for item in request.activities
    )
    try:
        solution = StaffingOptimizer().solve(
            teachers=teachers,
            requirements=requirements,
            group_ids=tuple(request.group_ids),
            activities=activities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return StaffingSolveResponse(
        complete=solution.complete,
        assignments=[
            StaffingAssignmentRead(
                requirement_id=item.requirement_id,
                group_id=item.group_id,
                subject=item.subject,
                minutes=item.minutes,
                teacher_id=item.teacher_id,
            )
            for item in solution.assignments
        ],
        activity_assignments=[
            StaffingActivityAssignmentRead(
                activity_id=item.activity_id,
                activity_name=item.activity_name,
                minutes=item.minutes,
                teacher_id=item.teacher_id,
            )
            for item in solution.activity_assignments
        ],
        tutors=[
            TutorAssignmentRead(group_id=item.group_id, teacher_id=item.teacher_id)
            for item in solution.tutors
        ],
        uncovered_requirement_ids=list(solution.uncovered_requirement_ids),
        uncovered_activity_ids=list(solution.uncovered_activity_ids),
        uncovered_tutor_groups=list(solution.uncovered_tutor_groups),
        teacher_loads=[
            StaffingTeacherLoadRead(
                teacher_id=item.teacher_id,
                assigned_minutes=item.assigned_minutes,
                teaching_minutes=item.teaching_minutes,
                activity_minutes=item.activity_minutes,
                available_minutes=item.available_minutes,
                remaining_minutes=item.remaining_minutes,
                groups_taught=item.groups_taught,
                tutor_group=item.tutor_group,
            )
            for item in solution.teacher_loads
        ],
        objective_value=solution.objective_value,
        wall_time_seconds=solution.wall_time_seconds,
    )
