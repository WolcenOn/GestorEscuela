from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gestor_escuela.api.app import _recent_substitution_counts
from gestor_escuela.persistence.db import Base
from gestor_escuela.persistence.models import DayPlanRow, DayPlanRunRow, SchoolRow


def _run(
    *,
    school_id,
    day_plan_id,
    version: int,
    substitute_teacher_id: str,
) -> DayPlanRunRow:
    return DayPlanRunRow(
        school_id=school_id,
        day_plan_id=day_plan_id,
        actor_user_id=None,
        version=version,
        input_payload={},
        output_payload={
            "substitutions": [
                {"substitute_teacher_id": substitute_teacher_id},
            ]
        },
        coverage_ratio=1.0,
        score=100,
        total_penalty=0,
        wall_time_seconds=0.01,
    )


def test_recent_history_uses_latest_run_per_plan_and_rolling_windows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    school_id = uuid4()
    recent_plan_id = uuid4()
    older_plan_id = uuid4()

    with Session(engine) as session:
        session.add(SchoolRow(id=school_id, name="CEIP Fairness"))
        session.add_all(
            [
                DayPlanRow(
                    id=recent_plan_id,
                    school_id=school_id,
                    plan_date=date(2026, 9, 18),
                    version=3,
                    payload={},
                ),
                DayPlanRow(
                    id=older_plan_id,
                    school_id=school_id,
                    plan_date=date(2026, 9, 10),
                    version=2,
                    payload={},
                ),
            ]
        )
        session.add_all(
            [
                _run(
                    school_id=school_id,
                    day_plan_id=recent_plan_id,
                    version=2,
                    substitute_teacher_id="P10",
                ),
                _run(
                    school_id=school_id,
                    day_plan_id=recent_plan_id,
                    version=3,
                    substitute_teacher_id="P11",
                ),
                _run(
                    school_id=school_id,
                    day_plan_id=older_plan_id,
                    version=2,
                    substitute_teacher_id="P12",
                ),
            ]
        )
        session.commit()

        counts = _recent_substitution_counts(
            school_id,
            date(2026, 9, 20),
            session,
        )

    assert "P10" not in counts
    assert counts["P11"] == (1, 1)
    assert counts["P12"] == (0, 1)

    Base.metadata.drop_all(engine)
    engine.dispose()
