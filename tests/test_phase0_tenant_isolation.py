from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.web import app


@contextmanager
def _client() -> Iterator[TestClient]:
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
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _register(client: TestClient, *, email: str, school_name: str) -> dict[str, object]:
    response = client.post(
        "/auth/register-school",
        json={
            "email": email,
            "password": "phase zero secure password",
            "display_name": f"Admin {school_name}",
            "school_name": school_name,
        },
    )
    assert response.status_code == 201
    return response.json()


def _bearer(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _assert_cross_tenant_forbidden(response) -> None:
    assert response.status_code == 403
    assert "not a member" in response.json()["detail"]


def test_legacy_role_bootstrap_is_disabled_when_not_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", raising=False)

    with _client() as client:
        response = client.post(
            "/schools",
            headers={"X-Actor-Role": "ADMIN"},
            json={"name": "No debe crearse"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Legacy role bootstrap is disabled"


def test_bearer_identity_cannot_cross_school_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", "false")

    with _client() as client:
        school_a = _register(client, email="admin-a@example.test", school_name="CEIP A")
        school_b = _register(client, email="admin-b@example.test", school_name="CEIP B")
        school_a_id = school_a["school"]["id"]
        school_b_id = school_b["school"]["id"]
        headers_a = _bearer(school_a)
        headers_b = _bearer(school_b)

        year_b_response = client.post(
            f"/schools/{school_b_id}/academic-years",
            headers=headers_b,
            json={"label": "2026/27"},
        )
        assert year_b_response.status_code == 201
        year_b_id = year_b_response.json()["id"]

        scenario_b_response = client.post(
            f"/schools/{school_b_id}/academic-years/{year_b_id}/scenarios",
            headers=headers_b,
            json={"name": "Escenario B"},
        )
        assert scenario_b_response.status_code == 201
        scenario_b_id = scenario_b_response.json()["id"]

        read_attempts = [
            client.get(f"/schools/{school_b_id}/auth/context", headers=headers_a),
            client.get(f"/schools/{school_b_id}/academic-configuration", headers=headers_a),
            client.get(f"/schools/{school_b_id}/students", headers=headers_a),
            client.get(f"/schools/{school_b_id}/operations", headers=headers_a),
            client.get(f"/schools/{school_b_id}/academic-years", headers=headers_a),
            client.get(
                f"/schools/{school_b_id}/academic-years/{year_b_id}/scenarios",
                headers=headers_a,
            ),
            client.get(
                f"/schools/{school_b_id}/academic-years/{year_b_id}/scenarios/"
                f"{scenario_b_id}/snapshot",
                headers=headers_a,
            ),
            client.get(f"/schools/{school_b_id}/invitations", headers=headers_a),
            client.get(f"/schools/{school_b_id}/audit-log", headers=headers_a),
        ]
        for response in read_attempts:
            _assert_cross_tenant_forbidden(response)

        write_attempts = [
            client.put(
                f"/schools/{school_b_id}/students",
                headers=headers_a,
                json={"students": []},
            ),
            client.put(
                f"/schools/{school_b_id}/operations",
                headers=headers_a,
                json={"recess_shifts": [], "scheduled_activities": []},
            ),
            client.post(
                f"/schools/{school_b_id}/academic-years",
                headers=headers_a,
                json={"label": "2027/28"},
            ),
            client.post(
                f"/schools/{school_b_id}/academic-years/{year_b_id}/scenarios",
                headers=headers_a,
                json={"name": "Intrusión"},
            ),
            client.post(
                f"/schools/{school_b_id}/invitations",
                headers=headers_a,
                json={"email": "intruder@example.test", "role": "VIEWER"},
            ),
            client.post(
                f"/schools/{school_b_id}/staffing/solve",
                headers=headers_a,
                json={
                    "group_ids": ["G1"],
                    "teachers": [
                        {
                            "id": "T1",
                            "name": "Docente",
                            "available_minutes": 60,
                        }
                    ],
                    "requirements": [],
                    "activities": [],
                },
            ),
            client.post(
                f"/schools/{school_b_id}/day-plans",
                headers=headers_a,
                json={"plan_date": "2026-09-15"},
            ),
        ]
        for response in write_attempts:
            _assert_cross_tenant_forbidden(response)

        own_context = client.get(f"/schools/{school_a_id}/auth/context", headers=headers_a)
        assert own_context.status_code == 200
        assert own_context.json()["school_id"] == school_a_id
        assert own_context.json()["role"] == "ADMIN"
