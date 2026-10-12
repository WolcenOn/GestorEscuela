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


def configure_school(client: TestClient) -> str:
    school = client.post("/schools", json={"name": "CEIP Matrícula"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    response = client.put(
        f"/schools/{school_id}/academic-configuration",
        json={
            "groups": [
                {"id": "4A", "label": "4ºA", "stage": "Primaria"},
                {"id": "5A", "label": "5ºA", "stage": "Primaria"},
            ],
            "subjects": [],
            "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
            "teachers": [{"id": "P01", "display_name": "Ana", "profile": "TUTOR"}],
            "activities": [],
        },
    )
    assert response.status_code == 200
    return school_id


def test_roster_round_trip_supports_pt_and_al_together(client: TestClient) -> None:
    school_id = configure_school(client)
    saved = client.put(
        f"/schools/{school_id}/students",
        json={
            "students": [
                {
                    "id": "alu-1",
                    "first_name": "Lucía",
                    "last_name": "García Pérez",
                    "group_id": "4A",
                    "supports": [
                        {"service": "PT", "target_minutes": 120},
                        {"service": "AL", "target_minutes": 60},
                    ],
                },
                {
                    "id": "alu-2",
                    "first_name": "Pablo",
                    "last_name": "Martín",
                    "group_id": "4A",
                    "supports": [],
                },
            ]
        },
    )
    assert saved.status_code == 200
    assert saved.json()["students"] == 2
    assert saved.json()["supports"] == 2

    read = client.get(f"/schools/{school_id}/students")
    assert read.status_code == 200
    students = {item["id"]: item for item in read.json()["students"]}
    assert students["alu-1"]["group_id"] == "4A"
    assert {item["service"] for item in students["alu-1"]["supports"]} == {"PT", "AL"}
    assert students["alu-2"]["supports"] == []


def test_roster_rejects_unknown_class_group(client: TestClient) -> None:
    school_id = configure_school(client)
    response = client.put(
        f"/schools/{school_id}/students",
        json={
            "students": [
                {
                    "id": "alu-x",
                    "first_name": "Alumno",
                    "last_name": "Fuera",
                    "group_id": "9Z",
                }
            ]
        },
    )
    assert response.status_code == 422
    assert "9Z" in response.json()["detail"]
