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


def academic_configuration() -> dict[str, object]:
    return {
        "groups": [{"id": "G1", "label": "1º A"}],
        "subjects": [],
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
        "activities": [],
    }


def test_operations_configuration_round_trip(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Operaciones"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    assert client.put(
        f"/schools/{school_id}/academic-configuration",
        json=academic_configuration(),
    ).status_code == 200

    saved = client.put(
        f"/schools/{school_id}/operations",
        json={
            "recess_shifts": [
                {
                    "id": "PATIO-LUN",
                    "label": "Patio principal",
                    "weekday": 0,
                    "start_time": "11:00",
                    "end_time": "11:30",
                    "location": "Patio",
                    "required_staff": 2,
                    "assigned_teacher_ids": ["P01", "P02"],
                }
            ],
            "scheduled_activities": [
                {
                    "id": "BIBLIO-LUN",
                    "label": "Biblioteca",
                    "category": "BIBLIOTECA",
                    "weekday": 0,
                    "start_time": "12:30",
                    "end_time": "13:15",
                    "required_staff": 1,
                    "assigned_teacher_ids": ["P02"],
                },
                {
                    "id": "FIESTA-OTOÑO",
                    "label": "Fiesta de otoño",
                    "category": "EVENTO",
                    "activity_date": "2026-10-30",
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "required_staff": 2,
                    "assigned_teacher_ids": ["P01", "P02"],
                    "movable": False,
                    "cancelable": False,
                },
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["recess_shifts"] == 1
    assert saved.json()["scheduled_activities"] == 2

    read = client.get(f"/schools/{school_id}/operations")
    assert read.status_code == 200
    payload = read.json()
    assert payload["recess_shifts"][0]["required_staff"] == 2
    assert set(payload["recess_shifts"][0]["assigned_teacher_ids"]) == {"P01", "P02"}
    assert payload["scheduled_activities"][0]["category"] == "BIBLIOTECA"
    assert payload["scheduled_activities"][1]["activity_date"] == "2026-10-30"


def test_operations_reject_unknown_teacher(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Validación"})
    school_id = school.json()["id"]
    assert client.put(
        f"/schools/{school_id}/academic-configuration",
        json=academic_configuration(),
    ).status_code == 200

    response = client.put(
        f"/schools/{school_id}/operations",
        json={
            "recess_shifts": [
                {
                    "id": "PATIO",
                    "label": "Patio",
                    "weekday": 2,
                    "start_time": "11:00",
                    "end_time": "11:30",
                    "required_staff": 1,
                    "assigned_teacher_ids": ["P99"],
                }
            ]
        },
    )
    assert response.status_code == 422
    assert "P99" in response.json()["detail"]
