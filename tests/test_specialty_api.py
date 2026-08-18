from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api.app import app
from gestor_escuela.persistence.db import Base, get_session


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


def test_specialty_configuration_round_trip_and_solver_enforcement(
    client: TestClient,
) -> None:
    school = client.post("/schools", json={"name": "CEIP Especialidades"})
    assert school.status_code == 201
    school_id = school.json()["id"]

    configuration = {
        "groups": [{"id": "G1", "label": "Grupo 1"}],
        "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
        "teachers": [
            {
                "id": "ABSENT",
                "profile": "SPECIALIST",
                "can_cover_groups": ["G1"],
                "specialties": ["ENGLISH"],
            },
            {
                "id": "GENERAL",
                "profile": "TUTOR",
                "can_cover_groups": ["G1"],
                "specialties": [],
            },
            {
                "id": "ENGLISH",
                "profile": "SPECIALIST",
                "substitution_count": 100,
                "can_cover_groups": ["G1"],
                "specialties": ["ENGLISH"],
            },
        ],
        "activities": [
            {
                "id": "A-ENGLISH",
                "slot_id": "S1",
                "activity_type": "CLASS",
                "teacher_id": "ABSENT",
                "group_id": "G1",
                "required_specialty": "ENGLISH",
                "priority": 30,
            }
        ],
    }
    saved = client.put(f"/schools/{school_id}/configuration", json=configuration)
    assert saved.status_code == 200

    read = client.get(f"/schools/{school_id}/configuration")
    assert read.status_code == 200
    payload = read.json()
    english_teacher = next(item for item in payload["teachers"] if item["id"] == "ENGLISH")
    assert english_teacher["specialties"] == ["ENGLISH"]
    assert payload["activities"][0]["required_specialty"] == "ENGLISH"

    plan = client.post(
        f"/schools/{school_id}/day-plans",
        json={"plan_date": "2026-09-15"},
    )
    assert plan.status_code == 201

    solved = client.post(
        f"/schools/{school_id}/day-plans/{plan.json()['id']}/solve",
        json={"absences": [{"teacher_id": "ABSENT", "slot_ids": ["S1"]}]},
    )
    assert solved.status_code == 200
    solution = solved.json()["payload"]["solution"]
    assert solution["substitutions"][0]["substitute_teacher_id"] == "ENGLISH"

    general = next(
        item
        for item in solution["candidate_assessments"]
        if item["teacher_id"] == "GENERAL"
    )
    assert general["status"] == "REJECTED"
    assert general["rejection_reason"] == "MISSING_SPECIALTY"
