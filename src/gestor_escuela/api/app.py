from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from gestor_escuela.api.auth import AdminDep, PlannerDep, ViewerDep
from gestor_escuela.api.schemas import (
    DayPlanCreate,
    DayPlanEventRead,
    DayPlanLifecycleRequest,
    DayPlanRead,
    DayPlanRunRead,
    DayPlanSolveRequest,
    SchoolConfigurationPut,
    SchoolCreate,
    SchoolRead,
)
from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    LockedSubstitution,
    Priority,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.persistence.db import get_session
from gestor_escuela.persistence.models import (
    DayPlanEventRow,
    DayPlanRow,
    DayPlanRunRow,
    DayPlanStatus,
    SchoolActivityRow,
    SchoolGroupRow,
    SchoolRow,
    SchoolTeacherRow,
    SchoolTimeSlotRow,
)
from gestor_escuela.solver.optimizer import SchoolDayOptimizer

app = FastAPI(title="GestorEscuela API", version="0.3.0")
SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/schools", response_model=SchoolRead, status_code=status.HTTP_201_CREATED)
def create_school(payload: SchoolCreate, session: SessionDep, _actor: AdminDep) -> SchoolRow:
    school = SchoolRow(name=payload.name)
    session.add(school)
    session.commit()
    session.refresh(school)
    return school


def _require_school(school_id: UUID, session: Session) -> SchoolRow:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _require_school_day_plan(
    school_id: UUID,
    plan_id: UUID,
    session: Session,
) -> DayPlanRow:
    plan = session.scalar(
        select(DayPlanRow).where(
            DayPlanRow.id == plan_id,
            DayPlanRow.school_id == school_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found for this school")
    return plan


def _validate_expected_version(plan: DayPlanRow, expected_version: int) -> None:
    if expected_version != plan.version:
        raise HTTPException(
            status_code=409,
            detail=(
                "Day plan version conflict: "
                f"expected {expected_version}, current {plan.version}"
            ),
        )


def _validate_configuration(payload: SchoolConfigurationPut) -> None:
    group_ids = {item.id for item in payload.groups}
    slot_ids = {item.id for item in payload.time_slots}
    teacher_ids = {item.id for item in payload.teachers}

    if len(group_ids) != len(payload.groups):
        raise HTTPException(status_code=422, detail="Group ids must be unique")
    if len(slot_ids) != len(payload.time_slots):
        raise HTTPException(status_code=422, detail="Time slot ids must be unique")
    if len(teacher_ids) != len(payload.teachers):
        raise HTTPException(status_code=422, detail="Teacher ids must be unique")

    activity_ids = {item.id for item in payload.activities}
    if len(activity_ids) != len(payload.activities):
        raise HTTPException(status_code=422, detail="Activity ids must be unique")

    for teacher in payload.teachers:
        unknown_groups = teacher.can_cover_groups - group_ids
        if unknown_groups:
            raise HTTPException(
                status_code=422,
                detail=f"Teacher {teacher.id} references unknown groups: {sorted(unknown_groups)}",
            )

    for activity in payload.activities:
        if activity.slot_id not in slot_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Activity {activity.id} references unknown slot {activity.slot_id}",
            )
        if activity.teacher_id not in teacher_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Activity {activity.id} references unknown teacher {activity.teacher_id}",
            )
        if activity.group_id is not None and activity.group_id not in group_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Activity {activity.id} references unknown group {activity.group_id}",
            )


@app.put("/schools/{school_id}/configuration")
def put_school_configuration(
    school_id: UUID,
    payload: SchoolConfigurationPut,
    session: SessionDep,
    _actor: AdminDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    _validate_configuration(payload)

    session.execute(delete(SchoolActivityRow).where(SchoolActivityRow.school_id == school_id))
    session.execute(delete(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id))
    session.execute(delete(SchoolTimeSlotRow).where(SchoolTimeSlotRow.school_id == school_id))
    session.execute(delete(SchoolGroupRow).where(SchoolGroupRow.school_id == school_id))

    session.add_all(
        [
            SchoolGroupRow(school_id=school_id, external_id=item.id, label=item.label)
            for item in payload.groups
        ]
    )
    session.add_all(
        [
            SchoolTimeSlotRow(
                school_id=school_id,
                external_id=item.id,
                label=item.label,
                slot_order=item.order,
            )
            for item in payload.time_slots
        ]
    )
    session.add_all(
        [
            SchoolTeacherRow(
                school_id=school_id,
                external_id=item.id,
                profile=item.profile.value,
                substitution_count=item.substitution_count,
                can_cover_groups=sorted(item.can_cover_groups),
                emergency_only=item.emergency_only,
            )
            for item in payload.teachers
        ]
    )
    session.add_all(
        [
            SchoolActivityRow(
                school_id=school_id,
                external_id=item.id,
                slot_external_id=item.slot_id,
                activity_type=item.activity_type.value,
                teacher_external_id=item.teacher_id,
                group_external_id=item.group_id,
                priority=int(item.priority),
                movable=item.movable,
                cancelable=item.cancelable,
            )
            for item in payload.activities
        ]
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Invalid or duplicate school configuration",
        ) from exc
    return {"school_id": school_id, "status": "configured"}


@app.get("/schools/{school_id}/configuration")
def get_school_configuration(
    school_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    groups = session.scalars(
        select(SchoolGroupRow).where(SchoolGroupRow.school_id == school_id)
    ).all()
    slots = session.scalars(
        select(SchoolTimeSlotRow)
        .where(SchoolTimeSlotRow.school_id == school_id)
        .order_by(SchoolTimeSlotRow.slot_order)
    ).all()
    teachers = session.scalars(
        select(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id)
    ).all()
    activities = session.scalars(
        select(SchoolActivityRow).where(SchoolActivityRow.school_id == school_id)
    ).all()
    return {
        "school_id": school_id,
        "groups": [{"id": item.external_id, "label": item.label} for item in groups],
        "time_slots": [
            {"id": item.external_id, "label": item.label, "order": item.slot_order}
            for item in slots
        ],
        "teachers": [
            {
                "id": item.external_id,
                "profile": item.profile,
                "substitution_count": item.substitution_count,
                "can_cover_groups": item.can_cover_groups,
                "emergency_only": item.emergency_only,
            }
            for item in teachers
        ],
        "activities": [
            {
                "id": item.external_id,
                "slot_id": item.slot_external_id,
                "activity_type": item.activity_type,
                "teacher_id": item.teacher_external_id,
                "group_id": item.group_external_id,
                "priority": item.priority,
                "movable": item.movable,
                "cancelable": item.cancelable,
            }
            for item in activities
        ],
    }


@app.post("/day-plans", response_model=DayPlanRead, status_code=status.HTTP_201_CREATED)
def create_day_plan(payload: DayPlanCreate, session: SessionDep, _actor: PlannerDep) -> DayPlanRow:
    _require_school(payload.school_id, session)
    plan = DayPlanRow(
        school_id=payload.school_id,
        plan_date=payload.plan_date,
        source_hash=payload.source_hash,
        notes=payload.notes,
        payload=payload.payload,
    )
    session.add(plan)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A day plan already exists for this school and date",
        ) from exc
    session.refresh(plan)
    return plan


@app.get("/day-plans/{plan_id}", response_model=DayPlanRead)
def get_day_plan(plan_id: UUID, session: SessionDep, _actor: ViewerDep) -> DayPlanRow:
    plan = session.get(DayPlanRow, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found")
    return plan


@app.get("/schools/{school_id}/day-plans/{plan_id}", response_model=DayPlanRead)
def get_school_day_plan(
    school_id: UUID,
    plan_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> DayPlanRow:
    return _require_school_day_plan(school_id, plan_id, session)


@app.get("/schools/{school_id}/day-plans", response_model=list[DayPlanRead])
def list_day_plans(
    school_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
    plan_date: date | None = None,
) -> list[DayPlanRow]:
    statement = select(DayPlanRow).where(DayPlanRow.school_id == school_id)
    if plan_date is not None:
        statement = statement.where(DayPlanRow.plan_date == plan_date)
    return list(session.scalars(statement.order_by(DayPlanRow.plan_date)).all())


@app.get(
    "/schools/{school_id}/day-plans/{plan_id}/runs",
    response_model=list[DayPlanRunRead],
)
def list_day_plan_runs(
    school_id: UUID,
    plan_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> list[DayPlanRunRow]:
    _require_school_day_plan(school_id, plan_id, session)
    statement = (
        select(DayPlanRunRow)
        .where(
            DayPlanRunRow.day_plan_id == plan_id,
            DayPlanRunRow.school_id == school_id,
        )
        .order_by(DayPlanRunRow.version)
    )
    return list(session.scalars(statement).all())


@app.get(
    "/schools/{school_id}/day-plans/{plan_id}/events",
    response_model=list[DayPlanEventRead],
)
def list_day_plan_events(
    school_id: UUID,
    plan_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> list[DayPlanEventRow]:
    _require_school_day_plan(school_id, plan_id, session)
    statement = (
        select(DayPlanEventRow)
        .where(
            DayPlanEventRow.day_plan_id == plan_id,
            DayPlanEventRow.school_id == school_id,
        )
        .order_by(DayPlanEventRow.version)
    )
    return list(session.scalars(statement).all())


def _change_plan_status(
    *,
    plan: DayPlanRow,
    school_id: UUID,
    request: DayPlanLifecycleRequest,
    from_status: DayPlanStatus,
    to_status: DayPlanStatus,
    event_type: str,
    session: Session,
) -> DayPlanRow:
    _validate_expected_version(plan, request.expected_version)
    if plan.status != from_status.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Day plan must be {from_status.value} to {event_type.lower()}; "
                f"current status is {plan.status}"
            ),
        )

    next_version = plan.version + 1
    plan.version = next_version
    plan.status = to_status.value
    session.add(
        DayPlanEventRow(
            day_plan_id=plan.id,
            school_id=school_id,
            version=next_version,
            event_type=event_type,
            from_status=from_status.value,
            to_status=to_status.value,
            reason=request.reason,
        )
    )
    try:
        session.commit()
    except (IntegrityError, StaleDataError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Concurrent day plan update detected") from exc
    session.refresh(plan)
    return plan


@app.post("/schools/{school_id}/day-plans/{plan_id}/confirm", response_model=DayPlanRead)
def confirm_day_plan(
    school_id: UUID,
    plan_id: UUID,
    request: DayPlanLifecycleRequest,
    session: SessionDep,
    _actor: PlannerDep,
) -> DayPlanRow:
    plan = _require_school_day_plan(school_id, plan_id, session)
    return _change_plan_status(
        plan=plan,
        school_id=school_id,
        request=request,
        from_status=DayPlanStatus.SOLVED,
        to_status=DayPlanStatus.CONFIRMED,
        event_type="CONFIRMED",
        session=session,
    )


@app.post("/schools/{school_id}/day-plans/{plan_id}/reopen", response_model=DayPlanRead)
def reopen_day_plan(
    school_id: UUID,
    plan_id: UUID,
    request: DayPlanLifecycleRequest,
    session: SessionDep,
    _actor: AdminDep,
) -> DayPlanRow:
    plan = _require_school_day_plan(school_id, plan_id, session)
    return _change_plan_status(
        plan=plan,
        school_id=school_id,
        request=request,
        from_status=DayPlanStatus.CONFIRMED,
        to_status=DayPlanStatus.SOLVED,
        event_type="REOPENED",
        session=session,
    )


def _load_solver_inputs(
    school_id: UUID,
    session: Session,
) -> tuple[tuple[Teacher, ...], tuple[Activity, ...]]:
    teacher_rows = session.scalars(
        select(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id)
    ).all()
    activity_rows = session.scalars(
        select(SchoolActivityRow).where(SchoolActivityRow.school_id == school_id)
    ).all()
    if not teacher_rows or not activity_rows:
        raise HTTPException(
            status_code=409,
            detail="School configuration is incomplete; teachers and activities are required",
        )

    teachers = tuple(
        Teacher(
            id=item.external_id,
            profile=TeacherProfile(item.profile),
            substitution_count=item.substitution_count,
            can_cover_groups=frozenset(item.can_cover_groups),
            emergency_only=item.emergency_only,
        )
        for item in teacher_rows
    )
    activities = tuple(
        Activity(
            id=item.external_id,
            slot_id=item.slot_external_id,
            activity_type=ActivityType(item.activity_type),
            teacher_id=item.teacher_external_id,
            group_id=item.group_external_id,
            priority=Priority(item.priority),
            movable=item.movable,
            cancelable=item.cancelable,
        )
        for item in activity_rows
    )
    return teachers, activities


@app.post("/schools/{school_id}/day-plans/{plan_id}/solve", response_model=DayPlanRead)
def solve_day_plan(
    school_id: UUID,
    plan_id: UUID,
    request: DayPlanSolveRequest,
    session: SessionDep,
    _actor: PlannerDep,
) -> DayPlanRow:
    plan = _require_school_day_plan(school_id, plan_id, session)
    if plan.status == DayPlanStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=409,
            detail="Confirmed day plans must be reopened before recalculation",
        )
    if request.expected_version is not None:
        _validate_expected_version(plan, request.expected_version)

    absences = tuple(
        Absence(item.teacher_id, frozenset(item.slot_ids)) for item in request.absences
    )
    locked = tuple(
        LockedSubstitution(item.activity_id, item.substitute_teacher_id)
        for item in request.locked_substitutions
    )
    teachers, activities = _load_solver_inputs(school_id, session)
    try:
        solution = SchoolDayOptimizer().solve(
            teachers=teachers,
            activities=activities,
            absences=absences,
            locked_substitutions=locked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    input_payload: dict[str, object] = {
        "absences": [
            {"teacher_id": item.teacher_id, "slot_ids": sorted(item.slot_ids)}
            for item in absences
        ],
        "locked_substitutions": [
            {
                "activity_id": item.activity_id,
                "substitute_teacher_id": item.substitute_teacher_id,
            }
            for item in locked
        ],
    }
    output_payload: dict[str, object] = {
        "coverage_ratio": solution.coverage_ratio,
        "score": solution.score,
        "total_penalty": solution.total_penalty,
        "wall_time_seconds": solution.wall_time_seconds,
        "substitutions": [
            {
                "activity_id": item.activity_id,
                "slot_id": item.slot_id,
                "group_id": item.group_id,
                "absent_teacher_id": item.absent_teacher_id,
                "substitute_teacher_id": item.substitute_teacher_id,
                "displaced_activity_id": item.displaced_activity_id,
                "penalty": item.penalty,
            }
            for item in solution.substitutions
        ],
        "uncovered": [
            {
                "activity_id": item.activity_id,
                "slot_id": item.slot_id,
                "group_id": item.group_id,
                "absent_teacher_id": item.absent_teacher_id,
                "reason": item.reason,
            }
            for item in solution.uncovered
        ],
    }

    next_version = plan.version + 1
    plan.version = next_version
    plan.status = DayPlanStatus.SOLVED.value
    plan.payload = {
        **plan.payload,
        **input_payload,
        "solution": output_payload,
    }
    session.add(
        DayPlanRunRow(
            day_plan_id=plan.id,
            school_id=school_id,
            version=next_version,
            input_payload=input_payload,
            output_payload=output_payload,
            coverage_ratio=solution.coverage_ratio,
            score=solution.score,
            total_penalty=solution.total_penalty,
            wall_time_seconds=solution.wall_time_seconds,
        )
    )
    try:
        session.commit()
    except (IntegrityError, StaleDataError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Concurrent day plan update detected") from exc
    session.refresh(plan)
    return plan
