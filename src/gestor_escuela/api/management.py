from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gestor_escuela.api.auth import AdminDep, PlannerDep, SessionDep
from gestor_escuela.api.schemas import (
    DayPlanCreateScoped,
    DayPlanRead,
    SchoolMembershipPut,
    SchoolMembershipRead,
    UserCreate,
    UserRead,
)
from gestor_escuela.persistence.models import (
    DayPlanRow,
    SchoolMembershipRow,
    SchoolRow,
    UserRow,
)

router = APIRouter()


def _require_school(school_id: UUID, session: SessionDep) -> SchoolRow:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: SessionDep, _actor: AdminDep) -> UserRow:
    user = UserRow(email=payload.email.strip().lower(), display_name=payload.display_name.strip())
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc
    session.refresh(user)
    return user


@router.put(
    "/schools/{school_id}/memberships",
    response_model=SchoolMembershipRead,
)
def put_school_membership(
    school_id: UUID,
    payload: SchoolMembershipPut,
    session: SessionDep,
    _actor: AdminDep,
) -> SchoolMembershipRow:
    _require_school(school_id, session)
    if session.get(UserRow, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    membership = session.scalar(
        select(SchoolMembershipRow).where(
            SchoolMembershipRow.school_id == school_id,
            SchoolMembershipRow.user_id == payload.user_id,
        )
    )
    if membership is None:
        membership = SchoolMembershipRow(
            school_id=school_id,
            user_id=payload.user_id,
            role=payload.role,
        )
        session.add(membership)
    else:
        membership.role = payload.role

    session.commit()
    session.refresh(membership)
    return membership


@router.get(
    "/schools/{school_id}/memberships",
    response_model=list[SchoolMembershipRead],
)
def list_school_memberships(
    school_id: UUID,
    session: SessionDep,
    _actor: AdminDep,
) -> list[SchoolMembershipRow]:
    _require_school(school_id, session)
    statement = (
        select(SchoolMembershipRow)
        .where(SchoolMembershipRow.school_id == school_id)
        .order_by(SchoolMembershipRow.created_at, SchoolMembershipRow.id)
    )
    return list(session.scalars(statement).all())


@router.post(
    "/schools/{school_id}/day-plans",
    response_model=DayPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_school_day_plan(
    school_id: UUID,
    payload: DayPlanCreateScoped,
    session: SessionDep,
    _actor: PlannerDep,
) -> DayPlanRow:
    _require_school(school_id, session)
    plan = DayPlanRow(
        school_id=school_id,
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
