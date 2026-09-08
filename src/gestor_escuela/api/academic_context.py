from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gestor_escuela.api.academic_context_schemas import (
    AcademicYearCreate,
    AcademicYearRead,
    PlanningScenarioCreate,
    PlanningScenarioRead,
)
from gestor_escuela.api.auth import PlannerDep, SessionDep, ViewerDep
from gestor_escuela.persistence.academic_models import AcademicYearRow, PlanningScenarioRow
from gestor_escuela.persistence.models import SchoolRow

router = APIRouter()


def _require_school(school_id: UUID, session: SessionDep) -> SchoolRow:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _require_academic_year(
    school_id: UUID,
    academic_year_id: UUID,
    session: SessionDep,
) -> AcademicYearRow:
    academic_year = session.scalar(
        select(AcademicYearRow).where(
            AcademicYearRow.id == academic_year_id,
            AcademicYearRow.school_id == school_id,
        )
    )
    if academic_year is None:
        raise HTTPException(status_code=404, detail="Academic year not found for this school")
    return academic_year


@router.post(
    "/schools/{school_id}/academic-years",
    response_model=AcademicYearRead,
    status_code=status.HTTP_201_CREATED,
)
def create_academic_year(
    school_id: UUID,
    payload: AcademicYearCreate,
    session: SessionDep,
    _actor: PlannerDep,
) -> AcademicYearRow:
    _require_school(school_id, session)
    academic_year = AcademicYearRow(
        school_id=school_id,
        label=payload.label.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    session.add(academic_year)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An academic year with this label already exists for this school",
        ) from exc
    session.refresh(academic_year)
    return academic_year


@router.get(
    "/schools/{school_id}/academic-years",
    response_model=list[AcademicYearRead],
)
def list_academic_years(
    school_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> list[AcademicYearRow]:
    _require_school(school_id, session)
    return list(
        session.scalars(
            select(AcademicYearRow)
            .where(AcademicYearRow.school_id == school_id)
            .order_by(AcademicYearRow.created_at.desc(), AcademicYearRow.id.desc())
        ).all()
    )


@router.post(
    "/schools/{school_id}/academic-years/{academic_year_id}/scenarios",
    response_model=PlanningScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
def create_planning_scenario(
    school_id: UUID,
    academic_year_id: UUID,
    payload: PlanningScenarioCreate,
    session: SessionDep,
    actor: PlannerDep,
) -> PlanningScenarioRow:
    _require_school(school_id, session)
    _require_academic_year(school_id, academic_year_id, session)
    scenario = PlanningScenarioRow(
        school_id=school_id,
        academic_year_id=academic_year_id,
        name=payload.name.strip(),
        created_by_user_id=actor.user_id,
    )
    session.add(scenario)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A scenario with this name already exists for this academic year",
        ) from exc
    session.refresh(scenario)
    return scenario


@router.get(
    "/schools/{school_id}/academic-years/{academic_year_id}/scenarios",
    response_model=list[PlanningScenarioRead],
)
def list_planning_scenarios(
    school_id: UUID,
    academic_year_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
) -> list[PlanningScenarioRow]:
    _require_school(school_id, session)
    _require_academic_year(school_id, academic_year_id, session)
    return list(
        session.scalars(
            select(PlanningScenarioRow)
            .where(
                PlanningScenarioRow.school_id == school_id,
                PlanningScenarioRow.academic_year_id == academic_year_id,
            )
            .order_by(PlanningScenarioRow.created_at.desc(), PlanningScenarioRow.id.desc())
        ).all()
    )
