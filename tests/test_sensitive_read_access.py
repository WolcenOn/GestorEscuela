"""Regression tests: read-only membership is not permission to export pupil identities."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Iterator

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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _invite_member(
    client: TestClient, school_id: str, admin_token: str, role: str
) -> str:
    invitation = client.post(
        f"/schools/{school_id}/invitations",
        headers=_headers(admin_token),
        json={"email": f"{role.lower()}@example.test", "role": role},
    )
    assert invitation.status_code == 201
    accepted = client.post(
        "/auth/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "password": "secure test password 123",
            "display_name": f"Test {role}",
        },
    )
    assert accepted.status_code == 200
    return accepted.json()["access_token"]


def test_viewer_cannot_download_raw_pupil_roster_or_scenario_snapshot(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", "false")
    with _client() as client:
        registration = client.post(
            "/auth/register-school",
            json={
                "email": "admin@example.test",
                "password": "secure admin password 123",
                "display_name": "Admin",
                "school_name": "CEIP Privacidad",
            },
        )
        assert registration.status_code == 201
        school_id = registration.json()["school"]["id"]
        admin_token = registration.json()["access_token"]
        admin_headers = _headers(admin_token)

        academic_config = client.put(
            f"/schools/{school_id}/academic-configuration",
            headers=admin_headers,
            json={
                "groups": [{"id": "4A", "label": "4A", "stage": "Primaria"}],
                "subjects": [],
                "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
                "teachers": [],
                "activities": [],
            },
        )
        assert academic_config.status_code == 200
        roster_url = f"/schools/{school_id}/students"
        saved_roster = client.put(
            roster_url,
            headers=admin_headers,
            json={
                "students": [
                    {
                        "id": "student-secret",
                        "first_name": "NombreSensible",
                        "last_name": "ApellidoSensible",
                        "group_id": "4A",
                        "notes": "Observacion privada",
                        "supports": [
                            {
                                "service": "PT",
                                "target_minutes": 90,
                                "notes": "Necesidad confidencial",
                            }
                        ],
                    }
                ]
            },
        )
        assert saved_roster.status_code == 200

        year = client.post(
            f"/schools/{school_id}/academic-years",
            headers=admin_headers,
            json={"label": "2026/27"},
        )
        assert year.status_code == 201
        year_id = year.json()["id"]
        scenario = client.post(
            f"/schools/{school_id}/academic-years/{year_id}/scenarios",
            headers=admin_headers,
            json={"name": "Escenario protegido"},
        )
        assert scenario.status_code == 201
        scenario_id = scenario.json()["id"]
        scenario_list_url = (
            f"/schools/{school_id}/academic-years/{year_id}/scenarios"
        )
        snapshot_url = f"{scenario_list_url}/{scenario_id}/snapshot"
        saved_snapshot = client.put(
            snapshot_url,
            headers=admin_headers,
            json={
                "payload": {
                    "format": "horario-pt-al",
                    "data": {"students": [{"nombre": "NombreSensible"}]},
                }
            },
        )
        assert saved_snapshot.status_code == 200

        viewer_token = _invite_member(client, school_id, admin_token, "VIEWER")
        viewer_headers = _headers(viewer_token)
        assert client.get(
            f"/schools/{school_id}/auth/context", headers=viewer_headers
        ).json()["role"] == "VIEWER"
        # Viewer retains access to basic navigation metadata.
        assert client.get(
            f"/schools/{school_id}/academic-years", headers=viewer_headers
        ).status_code == 200
        assert client.get(
            scenario_list_url, headers=viewer_headers
        ).status_code == 200

        for url in (roster_url, snapshot_url):
            denied = client.get(url, headers=viewer_headers)
            assert denied.status_code == 403
            assert "NombreSensible" not in denied.text
            assert "confidencial" not in denied.text

        planner_token = _invite_member(client, school_id, admin_token, "PLANNER")
        for headers in (admin_headers, _headers(planner_token)):
            roster = client.get(roster_url, headers=headers)
            assert roster.status_code == 200
            assert roster.json()["students"][0]["first_name"] == "NombreSensible"
            snapshot = client.get(snapshot_url, headers=headers)
            assert snapshot.status_code == 200
            assert (
                snapshot.json()["payload"]["data"]["students"][0]["nombre"]
                == "NombreSensible"
            )
