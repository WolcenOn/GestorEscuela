from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

import gestor_escuela.api.app as api_app_module
from gestor_escuela.api.app import app
from gestor_escuela.persistence.db import get_session
from gestor_escuela.persistence.models import (
    DayPlanEventRow,
    DayPlanRow,
    DayPlanStatus,
    SchoolRow,
)


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


@pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="requires TEST_DATABASE_URL pointing to PostgreSQL",
)
def test_concurrent_http_confirm_returns_one_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    school_id = uuid4()
    plan_id = uuid4()

    with Session(engine, expire_on_commit=False) as setup:
        setup.add(SchoolRow(id=school_id, name="HTTP Concurrency School"))
        setup.add(
            DayPlanRow(
                id=plan_id,
                school_id=school_id,
                plan_date=date(2026, 9, 17),
                status=DayPlanStatus.SOLVED.value,
                version=2,
                payload={"solution": {"score": 100}},
            )
        )
        setup.commit()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    original_require = api_app_module._require_school_day_plan
    barrier = Barrier(2)

    def synchronized_require(
        requested_school_id: UUID,
        requested_plan_id: UUID,
        session: Session,
    ) -> DayPlanRow:
        plan = original_require(requested_school_id, requested_plan_id, session)
        barrier.wait(timeout=5)
        return plan

    monkeypatch.setattr(api_app_module, "_require_school_day_plan", synchronized_require)
    app.dependency_overrides[get_session] = override_session

    try:
        with TestClient(app, headers={"X-Actor-Role": "PLANNER"}) as client:

            def confirm(_: int) -> int:
                response = client.post(
                    f"/schools/{school_id}/day-plans/{plan_id}/confirm",
                    json={"expected_version": 2, "reason": "Concurrent approval"},
                )
                return response.status_code

            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(confirm, range(2)))

        assert sorted(statuses) == [200, 409]

        with Session(engine) as verify:
            plan = verify.get(DayPlanRow, plan_id)
            assert plan is not None
            assert plan.status == DayPlanStatus.CONFIRMED.value
            assert plan.version == 3
            events = verify.query(DayPlanEventRow).filter_by(day_plan_id=plan_id).all()
            assert len(events) == 1
            assert events[0].version == 3
    finally:
        app.dependency_overrides.clear()
        with Session(engine) as cleanup:
            cleanup.execute(delete(DayPlanEventRow).where(DayPlanEventRow.day_plan_id == plan_id))
            cleanup.execute(delete(DayPlanRow).where(DayPlanRow.id == plan_id))
            cleanup.execute(delete(SchoolRow).where(SchoolRow.id == school_id))
            cleanup.commit()
        engine.dispose()
