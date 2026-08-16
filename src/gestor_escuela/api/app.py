from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gestor_escuela.api.schemas import DayPlanCreate, DayPlanRead, SchoolCreate, SchoolRead
from gestor_escuela.persistence.db import get_session
from gestor_escuela.persistence.models import DayPlanRow, SchoolRow

app = FastAPI(title="GestorEscuela API", version="0.2.0")
SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/schools", response_model=SchoolRead, status_code=status.HTTP_201_CREATED)
def create_school(payload: SchoolCreate, session: SessionDep) -> SchoolRow:
    school = SchoolRow(name=payload.name)
    session.add(school)
    session.commit()
    session.refresh(school)
    return school


@app.post("/day-plans", response_model=DayPlanRead, status_code=status.HTTP_201_CREATED)
def create_day_plan(payload: DayPlanCreate, session: SessionDep) -> DayPlanRow:
    if session.get(SchoolRow, payload.school_id) is None:
        raise HTTPException(status_code=404, detail="School not found")

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
def get_day_plan(plan_id: UUID, session: SessionDep) -> DayPlanRow:
    plan = session.get(DayPlanRow, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found")
    return plan


@app.get("/schools/{school_id}/day-plans", response_model=list[DayPlanRead])
def list_day_plans(
    school_id: UUID,
    session: SessionDep,
    plan_date: date | None = None,
) -> list[DayPlanRow]:
    statement = select(DayPlanRow).where(DayPlanRow.school_id == school_id)
    if plan_date is not None:
        statement = statement.where(DayPlanRow.plan_date == plan_date)
    return list(session.scalars(statement.order_by(DayPlanRow.plan_date)).all())
