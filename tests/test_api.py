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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_read_day_plan(client: TestClient) -> None:
    school_response = client.post("/schools", json={"name": "CEIP Piloto"})
    assert school_response.status_code == 201
    school_id = school_response.json()["id"]

    create_response = client.post(
        "/day-plans",
        json={
            "school_id": school_id,
            "plan_date": "2026-09-15",
            "source_hash": "abc123",
            "payload": {"absences": ["P02", "P04"]},
        },
    )
    assert create_response.status_code == 201
    plan = create_response.json()
    assert plan["status"] == "DRAFT"
    assert plan["payload"]["absences"] == ["P02", "P04"]

    read_response = client.get(f"/day-plans/{plan['id']}")
    assert read_response.status_code == 200
    assert read_response.json()["school_id"] == school_id


def test_day_plan_is_unique_per_school_and_date(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Piloto"}).json()["id"]
    payload = {"school_id": school_id, "plan_date": "2026-09-15"}

    assert client.post("/day-plans", json=payload).status_code == 201
    duplicate = client.post("/day-plans", json=payload)
    assert duplicate.status_code == 409


def test_unknown_school_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/day-plans",
        json={
            "school_id": "00000000-0000-0000-0000-000000000001",
            "plan_date": "2026-09-15",
        },
    )
    assert response.status_code == 404
