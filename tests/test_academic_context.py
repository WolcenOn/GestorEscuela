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


def _create_year_and_scenario(client: TestClient, school_id: str) -> tuple[str, str]:
    year = client.post(
        f"/schools/{school_id}/academic-years",
        json={"label": "2026/27"},
    )
    assert year.status_code == 201
    year_id = year.json()["id"]
    scenario = client.post(
        f"/schools/{school_id}/academic-years/{year_id}/scenarios",
        json={"name": "Planificación inicial"},
    )
    assert scenario.status_code == 201
    return year_id, scenario.json()["id"]


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


def test_scenario_snapshot_can_be_saved_read_and_updated(client: TestClient) -> None:
    school_id = _create_school(client, "CEIP Compartido")
    year_id, scenario_id = _create_year_and_scenario(client, school_id)
    snapshot_url = (
        f"/schools/{school_id}/academic-years/{year_id}/scenarios/{scenario_id}/snapshot"
    )

    missing = client.get(snapshot_url)
    assert missing.status_code == 404

    first_payload = {
        "source_hash": "abc123",
        "payload": {
            "format": "horario-pt-al",
            "schemaVersion": 5,
            "data": {"students": [], "professionals": []},
        },
    }
    first = client.put(snapshot_url, json=first_payload)
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert first.json()["source_hash"] == "abc123"
    assert first.json()["payload"] == first_payload["payload"]

    stored = client.get(snapshot_url)
    assert stored.status_code == 200
    assert stored.json()["version"] == 1
    assert stored.json()["scenario_id"] == scenario_id

    second_payload = {
        "source_hash": "def456",
        "payload": {
            "format": "horario-pt-al",
            "schemaVersion": 5,
            "data": {"students": [{"id": "student-1"}]},
        },
    }
    second = client.put(snapshot_url, json=second_payload)
    assert second.status_code == 200
    assert second.json()["version"] == 2
    assert second.json()["source_hash"] == "def456"
    assert second.json()["payload"] == second_payload["payload"]


def test_scenario_snapshot_is_scoped_to_school_and_year(client: TestClient) -> None:
    school_id = _create_school(client, "CEIP A")
    other_school_id = _create_school(client, "CEIP B")
    year_id, scenario_id = _create_year_and_scenario(client, school_id)

    wrong_school = client.put(
        f"/schools/{other_school_id}/academic-years/{year_id}/scenarios/{scenario_id}/snapshot",
        json={"payload": {"format": "horario-pt-al"}},
    )
    assert wrong_school.status_code == 404
