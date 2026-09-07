from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gestor_escuela.api.auth import AdminDep, SessionDep, ViewerDep
from gestor_escuela.persistence.models import SchoolGroupRow, SchoolRow
from gestor_escuela.persistence.roster_models import SchoolStudentRow, SchoolStudentSupportRow

router = APIRouter(tags=["roster"])


class StudentSupportInput(BaseModel):
    service: Literal["PT", "AL"]
    target_minutes: int = Field(default=0, ge=0, le=3000)
    notes: str | None = Field(default=None, max_length=2000)


class StudentInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=180)
    group_id: str | None = Field(default=None, max_length=64)
    active: bool = True
    notes: str | None = Field(default=None, max_length=4000)
    supports: list[StudentSupportInput] = Field(default_factory=list)


class RosterPut(BaseModel):
    students: list[StudentInput] = Field(default_factory=list)


def _require_school(school_id: UUID, session: Session) -> None:
    if session.get(SchoolRow, school_id) is None:
        raise HTTPException(status_code=404, detail="School not found")


def _validate_roster(school_id: UUID, payload: RosterPut, session: Session) -> None:
    student_ids = [item.id for item in payload.students]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=422, detail="Student ids must be unique")

    known_groups = set(
        session.scalars(
            select(SchoolGroupRow.external_id).where(SchoolGroupRow.school_id == school_id)
        ).all()
    )
    for student in payload.students:
        if student.group_id and student.group_id not in known_groups:
            raise HTTPException(
                status_code=422,
                detail=f"{student.id} references unknown group: {student.group_id}",
            )
        services = [support.service for support in student.supports]
        if len(services) != len(set(services)):
            raise HTTPException(
                status_code=422,
                detail=f"{student.id} repeats the same support service",
            )


@router.put("/schools/{school_id}/students")
def put_roster(
    school_id: UUID,
    payload: RosterPut,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    _validate_roster(school_id, payload, session)

    session.execute(
        delete(SchoolStudentSupportRow).where(SchoolStudentSupportRow.school_id == school_id)
    )
    session.execute(delete(SchoolStudentRow).where(SchoolStudentRow.school_id == school_id))
    session.flush()

    support_count = 0
    for item in payload.students:
        student = SchoolStudentRow(
            school_id=school_id,
            external_id=item.id,
            first_name=item.first_name,
            last_name=item.last_name,
            group_external_id=item.group_id,
            active=item.active,
            notes=item.notes,
        )
        session.add(student)
        session.flush()
        for support in item.supports:
            session.add(
                SchoolStudentSupportRow(
                    school_id=school_id,
                    student_id=student.id,
                    service=support.service,
                    target_minutes=support.target_minutes,
                    notes=support.notes,
                )
            )
            support_count += 1

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Invalid roster configuration") from exc

    return {
        "school_id": school_id,
        "status": "configured",
        "students": len(payload.students),
        "supports": support_count,
    }


@router.get("/schools/{school_id}/students")
def get_roster(
    school_id: UUID,
    session: SessionDep,
    _: ViewerDep,
) -> dict[str, object]:
    _require_school(school_id, session)
    students = session.scalars(
        select(SchoolStudentRow)
        .where(SchoolStudentRow.school_id == school_id)
        .order_by(SchoolStudentRow.group_external_id, SchoolStudentRow.last_name, SchoolStudentRow.first_name)
    ).all()
    supports = session.scalars(
        select(SchoolStudentSupportRow)
        .where(SchoolStudentSupportRow.school_id == school_id)
        .order_by(SchoolStudentSupportRow.service)
    ).all()
    supports_by_student: dict[UUID, list[dict[str, object]]] = {}
    for support in supports:
        supports_by_student.setdefault(support.student_id, []).append(
            {
                "service": support.service,
                "target_minutes": support.target_minutes,
                "notes": support.notes,
            }
        )

    return {
        "school_id": school_id,
        "students": [
            {
                "id": student.external_id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "group_id": student.group_external_id,
                "active": student.active,
                "notes": student.notes,
                "supports": supports_by_student.get(student.id, []),
            }
            for student in students
        ],
    }
