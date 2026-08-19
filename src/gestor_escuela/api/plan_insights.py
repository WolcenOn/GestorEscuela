from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from gestor_escuela.api.auth import SessionDep, ViewerDep
from gestor_escuela.persistence.models import DayPlanRow, DayPlanRunRow, SchoolTeacherRow

router = APIRouter()


@router.get("/schools/{school_id}/substitution-statistics")
def substitution_statistics(
    school_id: UUID,
    session: SessionDep,
    _actor: ViewerDep,
    plan_date: Annotated[date, Query()],
) -> dict[str, object]:
    """Return substitution load by teacher before the requested plan date.

    Only the latest run version of each historical day plan is counted so recalculating
    the same day does not artificially inflate recent substitution statistics.
    """

    teachers = session.scalars(
        select(SchoolTeacherRow).where(SchoolTeacherRow.school_id == school_id)
    ).all()

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
        "school_id": school_id,
        "plan_date": plan_date,
        "teachers": [
            {
                "teacher_id": teacher.external_id,
                "historical_total": teacher.substitution_count,
                "last_30_days": counts_30[teacher.external_id],
                "last_7_days": counts_7[teacher.external_id],
            }
            for teacher in teachers
        ],
    }
