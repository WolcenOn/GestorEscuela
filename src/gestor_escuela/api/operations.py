from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gestor_escuela.api.auth import AdminDep, SessionDep, ViewerDep
from gestor_escuela.api.operations_schemas import OperationsConfigurationPut
from gestor_escuela.persistence.models import SchoolRow, SchoolTeacherRow
from gestor_escuela.persistence.operations_models import (
    SchoolRecessShiftRow,
    SchoolScheduledActivityRow,
)

router = APIRouter(tags=["operations-planning"])


def _require_school(school_id: UUID, session: Session) -> SchoolRow:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _teacher_ids(school_id: UUID, session: Session) -> set[str]:
    return set(
        session.scalars(
            select(SchoolTeacherRow.external_id).where(SchoolTeacherRow.school_id == school_id)
        ).all()
    )


def _validate_configuration(
    school_id: UUID,
    payload: OperationsConfigurationPut,
    session: Session,
) -> None:
    recess_ids = {item.id for item in payload.recess_shifts}
    activity_ids = {item.id for item in payload.scheduled_activities}
    if len(recess_ids) != len(payload.recess_shifts):
        raise HTTPException(status_code=422, detail="Recess shift ids must be unique")
    if len(activity_ids) != len(payload.scheduled_activities):
        raise HTTPException(status_code=422, detail="Scheduled activity ids must be unique")

    known_teachers = _teacher_ids(school_id, session)
    for recess_item in payload.recess_shifts:
        unknown = recess_item.assigned_teacher_ids - known_teachers
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{recess_item.id} references unknown teachers: "
                    f"{sorted(unknown)}"
                ),
            )

    for activity_item in payload.scheduled_activities:
        unknown = activity_item.assigned_teacher_ids - known_teachers
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{activity_item.id} references unknown teachers: "
                    f"{sorted(unknown)}"
                ),
            )


@router.put("/schools/{school_id}/operations")
def put_operations_configuration(
    school_id: UUID,
    payload: OperationsConfigurationPut,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    _validate_configuration(school_id, payload, session)

    session.execute(delete(SchoolRecessShiftRow).where(SchoolRecessShiftRow.school_id == school_id))
    session.execute(
        delete(SchoolScheduledActivityRow).where(
            SchoolScheduledActivityRow.school_id == school_id
        )
    )

    for recess_item in payload.recess_shifts:
        session.add(
            SchoolRecessShiftRow(
                school_id=school_id,
                external_id=recess_item.id,
                label=recess_item.label,
                weekday=recess_item.weekday,
                start_time=recess_item.start_time,
                end_time=recess_item.end_time,
                location=recess_item.location,
                required_staff=recess_item.required_staff,
                assigned_teacher_ids=sorted(recess_item.assigned_teacher_ids),
                active=recess_item.active,
                notes=recess_item.notes,
            )
        )

    for activity_item in payload.scheduled_activities:
        session.add(
            SchoolScheduledActivityRow(
                school_id=school_id,
                external_id=activity_item.id,
                label=activity_item.label,
                category=activity_item.category,
                weekday=activity_item.weekday,
                activity_date=activity_item.activity_date,
                start_time=activity_item.start_time,
                end_time=activity_item.end_time,
                location=activity_item.location,
                required_staff=activity_item.required_staff,
                assigned_teacher_ids=sorted(activity_item.assigned_teacher_ids),
                movable=activity_item.movable,
                cancelable=activity_item.cancelable,
                notes=activity_item.notes,
            )
        )

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Invalid operations configuration") from exc

    return {
        "school_id": school_id,
        "status": "configured",
        "recess_shifts": len(payload.recess_shifts),
        "scheduled_activities": len(payload.scheduled_activities),
    }


@router.get("/schools/{school_id}/operations")
def get_operations_configuration(
    school_id: UUID,
    session: SessionDep,
    _: ViewerDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    recess = session.scalars(
        select(SchoolRecessShiftRow)
        .where(SchoolRecessShiftRow.school_id == school_id)
        .order_by(
            SchoolRecessShiftRow.weekday,
            SchoolRecessShiftRow.start_time,
            SchoolRecessShiftRow.external_id,
        )
    ).all()
    activities = session.scalars(
        select(SchoolScheduledActivityRow)
        .where(SchoolScheduledActivityRow.school_id == school_id)
        .order_by(
            SchoolScheduledActivityRow.activity_date,
            SchoolScheduledActivityRow.weekday,
            SchoolScheduledActivityRow.start_time,
            SchoolScheduledActivityRow.external_id,
        )
    ).all()

    return {
        "school_id": school_id,
        "recess_shifts": [
            {
                "id": item.external_id,
                "label": item.label,
                "weekday": item.weekday,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "location": item.location,
                "required_staff": item.required_staff,
                "assigned_teacher_ids": item.assigned_teacher_ids,
                "active": item.active,
                "notes": item.notes,
            }
            for item in recess
        ],
        "scheduled_activities": [
            {
                "id": item.external_id,
                "label": item.label,
                "category": item.category,
                "weekday": item.weekday,
                "activity_date": item.activity_date,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "location": item.location,
                "required_staff": item.required_staff,
                "assigned_teacher_ids": item.assigned_teacher_ids,
                "movable": item.movable,
                "cancelable": item.cancelable,
                "notes": item.notes,
            }
            for item in activities
        ],
    }
