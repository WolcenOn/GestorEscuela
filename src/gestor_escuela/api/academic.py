from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from gestor_escuela.api.auth import AdminDep, PlannerDep, SessionDep, ViewerDep
from gestor_escuela.api.schemas import DayPlanSolveRequest, SchoolConfigurationPut
from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    LockedSubstitution,
    Priority,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.persistence.models import (
    DayPlanRow,
    DayPlanRunRow,
    DayPlanStatus,
    SchoolActivityRow,
    SchoolGroupRow,
    SchoolRow,
    SchoolSubjectRow,
    SchoolTeacherRow,
    SchoolTimeSlotRow,
)
from gestor_escuela.solver.flexible_specialty import FlexibleSpecialtySchoolDayOptimizer

router = APIRouter()


def _require_school(school_id: UUID, session: Session) -> SchoolRow:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _validate_configuration(payload: SchoolConfigurationPut) -> None:
    group_ids = {item.id for item in payload.groups}
    subject_ids = {item.id for item in payload.subjects}
    slot_ids = {item.id for item in payload.time_slots}
    teacher_ids = {item.id for item in payload.teachers}
    activity_ids = {item.id for item in payload.activities}

    if len(group_ids) != len(payload.groups):
        raise HTTPException(status_code=422, detail="Group ids must be unique")
    if len(subject_ids) != len(payload.subjects):
        raise HTTPException(status_code=422, detail="Subject ids must be unique")
    if len(slot_ids) != len(payload.time_slots):
        raise HTTPException(status_code=422, detail="Time slot ids must be unique")
    if len(teacher_ids) != len(payload.teachers):
        raise HTTPException(status_code=422, detail="Teacher ids must be unique")
    if len(activity_ids) != len(payload.activities):
        raise HTTPException(status_code=422, detail="Activity ids must be unique")

    for group in payload.groups:
        if group.tutor_teacher_id is not None and group.tutor_teacher_id not in teacher_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Group {group.id} references unknown tutor {group.tutor_teacher_id}",
            )

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
        if activity.subject_id is not None and activity.subject_id not in subject_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Activity {activity.id} references unknown subject {activity.subject_id}",
            )


@router.put("/schools/{school_id}/academic-configuration")
def put_academic_configuration(
    school_id: UUID,
    payload: SchoolConfigurationPut,
    session: SessionDep,
    _actor: AdminDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    _validate_configuration(payload)

    session.execute(delete(SchoolActivityRow).where(SchoolActivityRow.school_id == school_id))
    session.execute(delete(SchoolSubjectRow).where(SchoolSubjectRow.school_id == school_id))
    session.execute(delete(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id))
    session.execute(delete(SchoolTimeSlotRow).where(SchoolTimeSlotRow.school_id == school_id))
    session.execute(delete(SchoolGroupRow).where(SchoolGroupRow.school_id == school_id))

    session.add_all(
        [
            SchoolGroupRow(
                school_id=school_id,
                external_id=item.id,
                label=item.label,
                stage=item.stage,
                tutor_teacher_external_id=item.tutor_teacher_id,
            )
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
            SchoolSubjectRow(
                school_id=school_id,
                external_id=item.id,
                label=item.label,
                required_specialty=item.required_specialty,
            )
            for item in payload.subjects
        ]
    )
    session.add_all(
        [
            SchoolTeacherRow(
                school_id=school_id,
                external_id=item.id,
                display_name=item.display_name,
                profile=item.profile.value,
                substitution_count=item.substitution_count,
                can_cover_groups=sorted(item.can_cover_groups),
                specialties=sorted(item.specialties),
                emergency_only=item.emergency_only,
            )
            for item in payload.teachers
        ]
    )
    subject_specialties = {item.id: item.required_specialty for item in payload.subjects}
    session.add_all(
        [
            SchoolActivityRow(
                school_id=school_id,
                external_id=item.id,
                slot_external_id=item.slot_id,
                activity_type=item.activity_type.value,
                teacher_external_id=item.teacher_id,
                group_external_id=item.group_id,
                weekday=item.weekday,
                subject_external_id=item.subject_id,
                required_specialty=(
                    item.required_specialty
                    or (subject_specialties.get(item.subject_id) if item.subject_id else None)
                ),
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


@router.get("/schools/{school_id}/academic-configuration")
def get_academic_configuration(
    school_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    groups = session.scalars(
        select(SchoolGroupRow).where(SchoolGroupRow.school_id == school_id)
    ).all()
    subjects = session.scalars(
        select(SchoolSubjectRow).where(SchoolSubjectRow.school_id == school_id)
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
        "groups": [
            {
                "id": item.external_id,
                "label": item.label,
                "stage": item.stage,
                "tutor_teacher_id": item.tutor_teacher_external_id,
            }
            for item in groups
        ],
        "subjects": [
            {
                "id": item.external_id,
                "label": item.label,
                "required_specialty": item.required_specialty,
            }
            for item in subjects
        ],
        "time_slots": [
            {"id": item.external_id, "label": item.label, "order": item.slot_order}
            for item in slots
        ],
        "teachers": [
            {
                "id": item.external_id,
                "display_name": item.display_name,
                "profile": item.profile,
                "substitution_count": item.substitution_count,
                "can_cover_groups": item.can_cover_groups,
                "specialties": item.specialties,
                "emergency_only": item.emergency_only,
            }
            for item in teachers
        ],
        "activities": [
            {
                "id": item.external_id,
                "weekday": item.weekday,
                "slot_id": item.slot_external_id,
                "activity_type": item.activity_type,
                "teacher_id": item.teacher_external_id,
                "group_id": item.group_external_id,
                "subject_id": item.subject_external_id,
                "required_specialty": item.required_specialty,
                "priority": item.priority,
                "movable": item.movable,
                "cancelable": item.cancelable,
            }
            for item in activities
        ],
    }


def _recent_substitution_counts(
    school_id: UUID, plan_date: date, session: Session
) -> dict[str, tuple[int, int]]:
    cutoff_30 = plan_date - timedelta(days=30)
    cutoff_7 = plan_date - timedelta(days=7)
    rows = session.execute(
        select(DayPlanRunRow, DayPlanRow.plan_date)
        .join(DayPlanRow, DayPlanRow.id == DayPlanRunRow.day_plan_id)
        .where(
            DayPlanRunRow.school_id == school_id,
            DayPlanRow.plan_date >= cutoff_30,
            DayPlanRow.plan_date < plan_date,
        )
    ).all()
    latest_by_plan: dict[UUID, tuple[DayPlanRunRow, date]] = {}
    for run, historical_date in rows:
        current = latest_by_plan.get(run.day_plan_id)
        if current is None or run.version > current[0].version:
            latest_by_plan[run.day_plan_id] = (run, historical_date)

    counts_7: defaultdict[str, int] = defaultdict(int)
    counts_30: defaultdict[str, int] = defaultdict(int)
    for run, historical_date in latest_by_plan.values():
        substitutions = run.output_payload.get("substitutions", [])
        if not isinstance(substitutions, list):
            continue
        for item in substitutions:
            if not isinstance(item, dict):
                continue
            teacher_id = item.get("substitute_teacher_id")
            if not isinstance(teacher_id, str):
                continue
            counts_30[teacher_id] += 1
            if historical_date >= cutoff_7:
                counts_7[teacher_id] += 1
    return {
        teacher_id: (counts_7[teacher_id], counts_30[teacher_id])
        for teacher_id in set(counts_7) | set(counts_30)
    }


def _solver_inputs(
    school_id: UUID, plan_date: date, session: Session
) -> tuple[tuple[Teacher, ...], tuple[Activity, ...]]:
    teacher_rows = session.scalars(
        select(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id)
    ).all()
    activity_rows = session.scalars(
        select(SchoolActivityRow).where(
            SchoolActivityRow.school_id == school_id,
            or_(
                SchoolActivityRow.weekday.is_(None),
                SchoolActivityRow.weekday == plan_date.weekday(),
            ),
        )
    ).all()
    if not teacher_rows or not activity_rows:
        raise HTTPException(
            status_code=409,
            detail=(
                "School timetable is incomplete for this day; "
                "teachers and activities are required"
            ),
        )

    recent_counts = _recent_substitution_counts(school_id, plan_date, session)
    teachers = tuple(
        Teacher(
            id=item.external_id,
            profile=TeacherProfile(item.profile),
            substitution_count=item.substitution_count,
            can_cover_groups=frozenset(item.can_cover_groups),
            emergency_only=item.emergency_only,
            substitutions_last_7_days=recent_counts.get(item.external_id, (0, 0))[0],
            substitutions_last_30_days=recent_counts.get(item.external_id, (0, 0))[1],
            specialties=frozenset(item.specialties),
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
            required_specialty=item.required_specialty,
        )
        for item in activity_rows
    )
    return teachers, activities


@router.post("/schools/{school_id}/day-plans/{plan_id}/solve-academic")
def solve_academic_day_plan(
    school_id: UUID,
    plan_id: UUID,
    request: DayPlanSolveRequest,
    session: SessionDep,
    _actor: PlannerDep,
) -> dict[str, object]:
    plan = session.scalar(
        select(DayPlanRow).where(DayPlanRow.id == plan_id, DayPlanRow.school_id == school_id)
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found for this school")
    if plan.status == DayPlanStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=409,
            detail="Confirmed day plans must be reopened before recalculation",
        )
    if request.expected_version is not None and request.expected_version != plan.version:
        raise HTTPException(
            status_code=409,
            detail=(
                "Day plan version conflict: "
                f"expected {request.expected_version}, current {plan.version}"
            ),
        )

    absences = tuple(
        Absence(item.teacher_id, frozenset(item.slot_ids)) for item in request.absences
    )
    locked = tuple(
        LockedSubstitution(item.activity_id, item.substitute_teacher_id)
        for item in request.locked_substitutions
    )
    teachers, activities = _solver_inputs(school_id, plan.plan_date, session)
    try:
        solution = FlexibleSpecialtySchoolDayOptimizer().solve(
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
        "candidate_assessments": [
            {
                "activity_id": item.activity_id,
                "slot_id": item.slot_id,
                "group_id": item.group_id,
                "teacher_id": item.teacher_id,
                "status": item.status.value,
                "penalty": item.penalty,
                "rejection_reason": (
                    item.rejection_reason.value if item.rejection_reason is not None else None
                ),
                "detail": item.detail,
            }
            for item in solution.candidate_assessments
        ],
    }

    next_version = plan.version + 1
    plan.version = next_version
    plan.status = DayPlanStatus.SOLVED.value
    plan.payload = {**plan.payload, **input_payload, "solution": output_payload}
    session.add(
        DayPlanRunRow(
            day_plan_id=plan.id,
            school_id=school_id,
            actor_user_id=_actor.user_id,
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
    return {
        "id": plan.id,
        "school_id": plan.school_id,
        "plan_date": plan.plan_date,
        "status": plan.status,
        "version": plan.version,
        "payload": plan.payload,
    }
