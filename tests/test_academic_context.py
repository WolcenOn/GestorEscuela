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
    try:
        with TestClient(app, headers={"X-Actor-Role": "ADMIN"}) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _create_school(client: TestClient, name: str) -> str:
    response = client.post("/schools", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_academic_year_and_scenario_lifecycle(client: TestClient) -> None:
    school_id = _create_school(client, "CEIP Planificación")

    year_response = client.post(
        f"/schools/{school_id}/academic-years",
        json={
            "label": "2026/27",
            "start_date": "2026-09-01",
            "end_date": "2027-06-30",
        },
    )
    assert year_response.status_code == 201
    year = year_response.json()
    assert year["school_id"] == school_id
    assert year["label"] == "2026/27"
    assert year["version"] == 1

    listed_years = client.get(f"/schools/{school_id}/academic-years")
    assert listed_years.status_code == 200
    assert [item["id"] for item in listed_years.json()] == [year["id"]]

    scenario_response = client.post(
        f"/schools/{school_id}/academic-years/{year['id']}/scenarios",
        json={"name": "Planificación inicial"},
    )
    assert scenario_response.status_code == 201
    scenario = scenario_response.json()
    assert scenario["school_id"] == school_id
    assert scenario["academic_year_id"] == year["id"]
    assert scenario["status"] == "DRAFT"
    assert scenario["version"] == 1

    listed_scenarios = client.get(
        f"/schools/{school_id}/academic-years/{year['id']}/scenarios"
    )
    assert listed_scenarios.status_code == 200
    assert [item["id"] for item in listed_scenarios.json()] == [scenario["id"]]


def test_academic_context_validates_duplicates_dates_and_school_scope(
    client: TestClient,
) -> None:
    school_id = _create_school(client, "CEIP A")
    other_school_id = _create_school(client, "CEIP B")

    invalid = client.post(
        f"/schools/{school_id}/academic-years",
        json={
            "label": "2026/27",
            "start_date": "2027-06-30",
            "end_date": "2026-09-01",
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        f"/schools/{school_id}/academic-years",
        json={"label": "2026/27"},
    )
    assert created.status_code == 201
    year_id = created.json()["id"]

    duplicate = client.post(
        f"/schools/{school_id}/academic-years",
        json={"label": "2026/27"},
    )
    assert duplicate.status_code == 409

    wrong_school = client.post(
        f"/schools/{other_school_id}/academic-years/{year_id}/scenarios",
        json={"name": "No debe crearse"},
    )
    assert wrong_school.status_code == 404

    first_scenario = client.post(
        f"/schools/{school_id}/academic-years/{year_id}/scenarios",
        json={"name": "Borrador"},
    )
    assert first_scenario.status_code == 201

    duplicate_scenario = client.post(
        f"/schools/{school_id}/academic-years/{year_id}/scenarios",
        json={"name": "Borrador"},
    )
    assert duplicate_scenario.status_code == 409
