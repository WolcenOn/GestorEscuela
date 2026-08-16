from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from gestor_escuela.persistence.models import DayPlanRow, DayPlanStatus, SchoolRow


@pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="requires TEST_DATABASE_URL pointing to PostgreSQL",
)
def test_postgres_rejects_stale_day_plan_update() -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    school_id = uuid4()
    plan_id = uuid4()

    with Session(engine, expire_on_commit=False) as setup:
        setup.add(SchoolRow(id=school_id, name="Concurrency School"))
        setup.add(
            DayPlanRow(
                id=plan_id,
                school_id=school_id,
                plan_date=date(2026, 9, 16),
                status=DayPlanStatus.DRAFT.value,
                version=1,
                payload={},
            )
        )
        setup.commit()

    first = Session(engine, expire_on_commit=False)
    second = Session(engine, expire_on_commit=False)
    try:
        plan_a = first.get(DayPlanRow, plan_id)
        plan_b = second.get(DayPlanRow, plan_id)
        assert plan_a is not None
        assert plan_b is not None
        assert plan_a.version == plan_b.version == 1

        plan_a.version = 2
        plan_a.status = DayPlanStatus.SOLVED.value
        first.commit()

        plan_b.version = 2
        plan_b.status = DayPlanStatus.SOLVED.value
        with pytest.raises(StaleDataError):
            second.commit()
        second.rollback()
    finally:
        first.close()
        second.close()
        with Session(engine) as cleanup:
            cleanup.execute(delete(DayPlanRow).where(DayPlanRow.id == plan_id))
            cleanup.execute(delete(SchoolRow).where(SchoolRow.id == school_id))
            cleanup.commit()
        engine.dispose()
