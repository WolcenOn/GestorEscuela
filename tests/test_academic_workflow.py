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


def configuration() -> dict[str, object]:
    return {
        "groups": [
            {"id": "G1", "label": "1º A", "stage": "Primaria", "tutor_teacher_id": "P01"}
        ],
        "subjects": [
            {"id": "MAT", "label": "Matemáticas"},
        ],
        "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
        "teachers": [
            {
                "id": "P01",
                "display_name": "Ana",
                "profile": "TUTOR",
                "can_cover_groups": ["G1"],
            },
            {
                "id": "P02",
                "display_name": "Luis",
                "profile": "SUPPORT",
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
            },
            {
                "id": "TUE-G1-S1",
                "weekday": 1,
                "slot_id": "S1",
                "activity_type": "CLASS",
                "teacher_id": "P02",
                "group_id": "G1",
                "subject_id": "MAT",
                "priority": 30,
            },
        ],
    }


def test_academic_configuration_round_trip(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Académico"})
    assert school.status_code == 201
    school_id = school.json()["id"]

    saved = client.put(
        f"/schools/{school_id}/academic-configuration",
        json=configuration(),
    )
    assert saved.status_code == 200

    read = client.get(f"/schools/{school_id}/academic-configuration")
    assert read.status_code == 200
    payload = read.json()
    assert payload["subjects"][0]["label"] == "Matemáticas"
    assert payload["groups"][0]["tutor_teacher_id"] == "P01"
    assert payload["teachers"][0]["display_name"] == "Ana"
    assert {item["weekday"] for item in payload["activities"]} == {0, 1}


def test_academic_solver_only_loads_selected_weekday(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Semana"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    assert client.put(
        f"/schools/{school_id}/academic-configuration",
        json=configuration(),
    ).status_code == 200

    plan = client.post(
        f"/schools/{school_id}/day-plans",
        json={"plan_date": "2026-08-17"},
    )
    assert plan.status_code == 201

    solved = client.post(
        f"/schools/{school_id}/day-plans/{plan.json()['id']}/solve-academic",
        json={"absences": [{"teacher_id": "P01", "slot_ids": ["S1"]}]},
    )
    assert solved.status_code == 200
    substitutions = solved.json()["payload"]["solution"]["substitutions"]
    assert len(substitutions) == 1
    assert substitutions[0]["substitute_teacher_id"] == "P02"
