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


def create_school(client: TestClient, name: str = "CEIP Piloto") -> str:
    response = client.post("/schools", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create_plan(client: TestClient, school_id: str, plan_date: str = "2026-09-15") -> dict[str, object]:
    response = client.post(
        "/day-plans",
        json={"school_id": school_id, "plan_date": plan_date},
    )
    assert response.status_code == 201
    return response.json()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_read_day_plan(client: TestClient) -> None:
    school_id = create_school(client)

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
    school_id = create_school(client)
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


def test_solve_day_plan_persists_absences_and_solution(client: TestClient) -> None:
    school_id = create_school(client)
    plan = create_plan(client, school_id)

    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/solve",
        json={
            "absences": [
                {"teacher_id": "P02", "slot_ids": ["S1", "S2"]},
                {"teacher_id": "P04", "slot_ids": ["S1", "S2"]},
            ]
        },
    )
    assert response.status_code == 200
    solved = response.json()
    assert solved["status"] == "SOLVED"
    assert len(solved["payload"]["absences"]) == 2
    assert solved["payload"]["solution"]["coverage_ratio"] == 1.0
    assert len(solved["payload"]["solution"]["substitutions"]) == 4

    read_response = client.get(f"/schools/{school_id}/day-plans/{plan['id']}")
    assert read_response.status_code == 200
    assert read_response.json()["payload"]["solution"]["score"] > 0


def test_recalculation_respects_locked_manual_decision(client: TestClient) -> None:
    school_id = create_school(client)
    plan = create_plan(client, school_id)

    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/solve",
        json={
            "absences": [{"teacher_id": "P02", "slot_ids": ["S1"]}],
            "locked_substitutions": [
                {"activity_id": "A-S1-G2", "substitute_teacher_id": "P11"}
            ],
        },
    )
    assert response.status_code == 200
    substitutions = response.json()["payload"]["solution"]["substitutions"]
    assert substitutions[0]["substitute_teacher_id"] == "P11"


def test_invalid_locked_decision_returns_domain_error(client: TestClient) -> None:
    school_id = create_school(client)
    plan = create_plan(client, school_id)

    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/solve",
        json={
            "absences": [{"teacher_id": "P02", "slot_ids": ["S1"]}],
            "locked_substitutions": [
                {"activity_id": "A-S1-G2", "substitute_teacher_id": "P07"}
            ],
        },
    )
    assert response.status_code == 422
    assert "no está disponible o no es compatible" in response.json()["detail"]


def test_school_scoped_plan_access_is_isolated(client: TestClient) -> None:
    school_a = create_school(client, "CEIP A")
    school_b = create_school(client, "CEIP B")
    plan = create_plan(client, school_a)

    read_response = client.get(f"/schools/{school_b}/day-plans/{plan['id']}")
    assert read_response.status_code == 404

    solve_response = client.post(
        f"/schools/{school_b}/day-plans/{plan['id']}/solve",
        json={"absences": [{"teacher_id": "P02", "slot_ids": ["S1"]}]},
    )
    assert solve_response.status_code == 404
