from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.web import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app, headers={"X-Actor-Role": "ADMIN"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_substitution_statistics_include_recent_windows(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Estadísticas"})
    assert school.status_code == 201
    school_id = school.json()["id"]

    configuration = {
        "groups": [{"id": "G1", "label": "1º A"}],
        "subjects": [{"id": "MAT", "label": "Matemáticas"}],
        "time_slots": [{"id": "S1", "label": "09:00–10:00", "order": 1}],
        "teachers": [
            {
                "id": "P01",
                "display_name": "Ana",
                "profile": "TUTOR",
                "substitution_count": 0,
                "can_cover_groups": ["G1"],
            },
            {
                "id": "P02",
                "display_name": "Luis",
                "profile": "SUPPORT",
                "substitution_count": 4,
                "can_cover_groups": ["G1"],
            },
        ],
        "activities": [
            {
                "id": "MON-G1-S1",
                "weekday": 0,
                "slot_id": "S1",
                "activity_type": "CLASS",
                "teacher_id": "P01",
                "group_id": "G1",
                "subject_id": "MAT",
                "priority": 30,
            }
        ],
    }
    assert client.put(
        f"/schools/{school_id}/academic-configuration",
        json=configuration,
    ).status_code == 200

    plan = client.post(
        f"/schools/{school_id}/day-plans",
        json={"plan_date": "2026-08-17"},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]

    solved = client.post(
        f"/schools/{school_id}/day-plans/{plan_id}/solve-academic",
        json={"absences": [{"teacher_id": "P01", "slot_ids": ["S1"]}]},
    )
    assert solved.status_code == 200

    response = client.get(
        f"/schools/{school_id}/substitution-statistics?plan_date=2026-08-19"
    )
    assert response.status_code == 200
    stats = {item["teacher_id"]: item for item in response.json()["teachers"]}

    assert stats["P02"]["historical_total"] == 4
    assert stats["P02"]["last_30_days"] == 1
    assert stats["P02"]["last_7_days"] == 1
