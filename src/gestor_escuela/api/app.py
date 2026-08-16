from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gestor_escuela.api.schemas import (
    DayPlanCreate,
    DayPlanRead,
    DayPlanSolveRequest,
    SchoolCreate,
    SchoolRead,
)
from gestor_escuela.domain.models import Absence, LockedSubstitution
from gestor_escuela.persistence.db import get_session
from gestor_escuela.persistence.models import DayPlanRow, DayPlanStatus, SchoolRow
from gestor_escuela.simulation.dataset import build_pilot_dataset
from gestor_escuela.solver.optimizer import SchoolDayOptimizer

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


@app.get("/schools/{school_id}/day-plans/{plan_id}", response_model=DayPlanRead)
def get_school_day_plan(school_id: UUID, plan_id: UUID, session: SessionDep) -> DayPlanRow:
    plan = session.scalar(
        select(DayPlanRow).where(
            DayPlanRow.id == plan_id,
            DayPlanRow.school_id == school_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found for this school")
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


@app.post("/schools/{school_id}/day-plans/{plan_id}/solve", response_model=DayPlanRead)
def solve_day_plan(
    school_id: UUID,
    plan_id: UUID,
    request: DayPlanSolveRequest,
    session: SessionDep,
) -> DayPlanRow:
    plan = session.scalar(
        select(DayPlanRow).where(
            DayPlanRow.id == plan_id,
            DayPlanRow.school_id == school_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Day plan not found for this school")

    absences = tuple(
        Absence(item.teacher_id, frozenset(item.slot_ids)) for item in request.absences
    )
    locked = tuple(
        LockedSubstitution(item.activity_id, item.substitute_teacher_id)
        for item in request.locked_substitutions
    )
    teachers, _, _, activities = build_pilot_dataset()
    try:
        solution = SchoolDayOptimizer().solve(
            teachers=teachers,
            activities=activities,
            absences=absences,
            locked_substitutions=locked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    plan.status = DayPlanStatus.SOLVED.value
    plan.payload = {
        **plan.payload,
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
        "solution": {
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
        },
    }
    session.commit()
    session.refresh(plan)
    return plan
