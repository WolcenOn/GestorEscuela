from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api.app import app
from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.simulation.dataset import build_pilot_dataset


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


def create_school(client: TestClient, name: str = "CEIP Piloto") -> str:
    response = client.post("/schools", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def configure_school(client: TestClient, school_id: str) -> None:
    teachers, groups, slots, activities = build_pilot_dataset()
    response = client.put(
        f"/schools/{school_id}/configuration",
        json={
            "groups": [{"id": item.id, "label": item.label} for item in groups],
            "time_slots": [
                {"id": item.id, "label": item.label, "order": item.order} for item in slots
            ],
            "teachers": [
                {
                    "id": item.id,
                    "profile": item.profile.value,
                    "substitution_count": item.substitution_count,
                    "can_cover_groups": sorted(item.can_cover_groups),
                    "emergency_only": item.emergency_only,
                }
                for item in teachers
            ],
            "activities": [
                {
                    "id": item.id,
                    "slot_id": item.slot_id,
                    "activity_type": item.activity_type.value,
                    "teacher_id": item.teacher_id,
                    "group_id": item.group_id,
                    "priority": int(item.priority),
                    "movable": item.movable,
                    "cancelable": item.cancelable,
                }
                for item in activities
            ],
        },
    )
    assert response.status_code == 200


def create_plan(
    client: TestClient,
    school_id: str,
    plan_date: str = "2026-09-15",
) -> dict[str, object]:
    response = client.post(
        "/day-plans",
        json={"school_id": school_id, "plan_date": plan_date},
    )
    assert response.status_code == 201
    return response.json()


def solve_once(client: TestClient, school_id: str, plan_id: object, **extra: object):
    payload: dict[str, object] = {
        "absences": [{"teacher_id": "P02", "slot_ids": ["S1"]}],
        **extra,
    }
    return client.post(
        f"/schools/{school_id}/day-plans/{plan_id}/solve",
        json=payload,
    )


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
    assert plan["version"] == 1
    assert plan["payload"]["absences"] == ["P02", "P04"]

    read_response = client.get(f"/schools/{school_id}/day-plans/{plan['id']}")
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


def test_school_configuration_round_trip(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    response = client.get(f"/schools/{school_id}/configuration")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["groups"]) == 6
    assert len(payload["teachers"]) == 12
    assert len(payload["time_slots"]) == 6
    assert payload["activities"]


def test_solve_requires_persisted_configuration(client: TestClient) -> None:
    school_id = create_school(client)
    plan = create_plan(client, school_id)
    response = solve_once(client, school_id, plan["id"])
    assert response.status_code == 409
    assert "configuration is incomplete" in response.json()["detail"]


def test_solve_day_plan_persists_absences_and_solution(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/solve",
        json={
            "absences": [
                {"teacher_id": "P02", "slot_ids": ["S1", "S2"]},
                {"teacher_id": "P04", "slot_ids": ["S1", "S2"]},
            ],
            "expected_version": 1,
        },
    )
    assert response.status_code == 200
    solved = response.json()
    assert solved["status"] == "SOLVED"
    assert solved["version"] == 2
    assert len(solved["payload"]["absences"]) == 2
    assert solved["payload"]["solution"]["coverage_ratio"] == 1.0
    assert len(solved["payload"]["solution"]["substitutions"]) == 4

    read_response = client.get(f"/schools/{school_id}/day-plans/{plan['id']}")
    assert read_response.status_code == 200
    assert read_response.json()["payload"]["solution"]["score"] > 0


def test_recalculation_respects_locked_manual_decision(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    response = solve_once(
        client,
        school_id,
        plan["id"],
        locked_substitutions=[
            {"activity_id": "A-S1-G2", "substitute_teacher_id": "P11"}
        ],
    )
    assert response.status_code == 200
    substitutions = response.json()["payload"]["solution"]["substitutions"]
    assert substitutions[0]["substitute_teacher_id"] == "P11"


def test_invalid_locked_decision_returns_domain_error(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    response = solve_once(
        client,
        school_id,
        plan["id"],
        locked_substitutions=[
            {"activity_id": "A-S1-G2", "substitute_teacher_id": "P07"}
        ],
    )
    assert response.status_code == 422
    assert "no está disponible o no es compatible" in response.json()["detail"]


def test_stale_day_plan_version_is_rejected(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    first = solve_once(client, school_id, plan["id"], expected_version=1)
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = solve_once(client, school_id, plan["id"], expected_version=1)
    assert stale.status_code == 409
    assert "version conflict" in stale.json()["detail"]


def test_solver_runs_are_audited(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    first = solve_once(client, school_id, plan["id"], expected_version=1)
    assert first.status_code == 200
    second = solve_once(client, school_id, plan["id"], expected_version=2)
    assert second.status_code == 200

    response = client.get(f"/schools/{school_id}/day-plans/{plan['id']}/runs")
    assert response.status_code == 200
    runs = response.json()
    assert [item["version"] for item in runs] == [2, 3]
    assert all(item["coverage_ratio"] == 1.0 for item in runs)
    assert runs[0]["input_payload"]["absences"][0]["teacher_id"] == "P02"


def test_draft_plan_cannot_be_confirmed(client: TestClient) -> None:
    school_id = create_school(client)
    plan = create_plan(client, school_id)
    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/confirm",
        json={"expected_version": 1},
    )
    assert response.status_code == 409
    assert "must be SOLVED" in response.json()["detail"]


def test_confirmed_plan_blocks_recalculation_until_reopened(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    solved = solve_once(client, school_id, plan["id"], expected_version=1)
    assert solved.status_code == 200

    confirmed = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/confirm",
        json={"expected_version": 2, "reason": "Validado por jefatura"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["version"] == 3

    blocked = solve_once(client, school_id, plan["id"], expected_version=3)
    assert blocked.status_code == 409
    assert "must be reopened" in blocked.json()["detail"]

    reopened = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/reopen",
        json={"expected_version": 3, "reason": "Nueva ausencia sobrevenida"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "SOLVED"
    assert reopened.json()["version"] == 4

    recalculated = solve_once(client, school_id, plan["id"], expected_version=4)
    assert recalculated.status_code == 200
    assert recalculated.json()["version"] == 5


def test_lifecycle_events_are_audited(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)
    assert solve_once(client, school_id, plan["id"], expected_version=1).status_code == 200

    assert client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/confirm",
        json={"expected_version": 2, "reason": "Plan definitivo"},
    ).status_code == 200
    assert client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/reopen",
        json={"expected_version": 3, "reason": "Incidencia de última hora"},
    ).status_code == 200

    response = client.get(f"/schools/{school_id}/day-plans/{plan['id']}/events")
    assert response.status_code == 200
    events = response.json()
    assert [item["event_type"] for item in events] == ["CONFIRMED", "REOPENED"]
    assert [item["version"] for item in events] == [3, 4]
    assert events[0]["reason"] == "Plan definitivo"


def test_school_scoped_plan_access_is_isolated(client: TestClient) -> None:
    school_a = create_school(client, "CEIP A")
    school_b = create_school(client, "CEIP B")
    configure_school(client, school_a)
    plan = create_plan(client, school_a)

    read_response = client.get(f"/schools/{school_b}/day-plans/{plan['id']}")
    assert read_response.status_code == 404

    solve_response = solve_once(client, school_b, plan["id"])
    assert solve_response.status_code == 404


def test_viewer_can_read_but_cannot_change_configuration(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)

    readable = client.get(
        f"/schools/{school_id}/configuration",
        headers={"X-Actor-Role": "VIEWER"},
    )
    assert readable.status_code == 200

    forbidden = client.put(
        f"/schools/{school_id}/configuration",
        json=readable.json(),
        headers={"X-Actor-Role": "VIEWER"},
    )
    assert forbidden.status_code == 403
    assert "ADMIN role required" in forbidden.json()["detail"]


def test_viewer_cannot_solve_day_plan(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    plan = create_plan(client, school_id)

    response = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/solve",
        json={"absences": [{"teacher_id": "P02", "slot_ids": ["S1"]}]},
        headers={"X-Actor-Role": "VIEWER"},
    )
    assert response.status_code == 403
    assert "PLANNER or ADMIN role required" in response.json()["detail"]


def test_planner_cannot_reconfigure_or_reopen(client: TestClient) -> None:
    school_id = create_school(client)
    configure_school(client, school_id)
    configuration = client.get(f"/schools/{school_id}/configuration").json()

    forbidden_configuration = client.put(
        f"/schools/{school_id}/configuration",
        json=configuration,
        headers={"X-Actor-Role": "PLANNER"},
    )
    assert forbidden_configuration.status_code == 403

    plan = create_plan(client, school_id)
    assert solve_once(client, school_id, plan["id"], expected_version=1).status_code == 200
    assert client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/confirm",
        json={"expected_version": 2},
        headers={"X-Actor-Role": "PLANNER"},
    ).status_code == 200

    forbidden_reopen = client.post(
        f"/schools/{school_id}/day-plans/{plan['id']}/reopen",
        json={"expected_version": 3},
        headers={"X-Actor-Role": "PLANNER"},
    )
    assert forbidden_reopen.status_code == 403
    assert "ADMIN role required" in forbidden_reopen.json()["detail"]
