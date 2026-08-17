from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api.app import app
from gestor_escuela.persistence.db import Base, get_session


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
        with TestClient(app, headers={"X-Actor-Role": "ADMIN"}) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_bootstrap_membership_enables_identity_only_tenant_access() -> None:
    with _client() as client:
        school = client.post("/schools", json={"name": "CEIP Identidad"})
        assert school.status_code == 201
        school_id = school.json()["id"]

        user = client.post(
            "/users",
            json={"email": "planner@example.test", "display_name": "Planner"},
        )
        assert user.status_code == 201
        user_id = user.json()["id"]

        membership = client.put(
            f"/schools/{school_id}/memberships",
            json={"user_id": user_id, "role": "PLANNER"},
        )
        assert membership.status_code == 200
        assert membership.json()["role"] == "PLANNER"

        created = client.post(
            f"/schools/{school_id}/day-plans",
            json={"plan_date": "2026-09-17"},
            headers={"X-Actor-Id": user_id},
        )
        assert created.status_code == 201
        assert created.json()["school_id"] == school_id
        assert created.json()["status"] == "DRAFT"


def test_viewer_membership_cannot_create_tenant_day_plan() -> None:
    with _client() as client:
        school = client.post("/schools", json={"name": "CEIP Lectura"})
        school_id = school.json()["id"]
        user = client.post(
            "/users",
            json={"email": "viewer2@example.test", "display_name": "Viewer"},
        )
        user_id = user.json()["id"]
        assert client.put(
            f"/schools/{school_id}/memberships",
            json={"user_id": user_id, "role": "VIEWER"},
        ).status_code == 200

        forbidden = client.post(
            f"/schools/{school_id}/day-plans",
            json={"plan_date": "2026-09-18"},
            headers={"X-Actor-Id": user_id, "X-Actor-Role": "ADMIN"},
        )
        assert forbidden.status_code == 403
        assert "PLANNER or ADMIN role required" in forbidden.json()["detail"]


def test_admin_identity_can_manage_memberships_for_own_school() -> None:
    with _client() as client:
        school = client.post("/schools", json={"name": "CEIP Admin"})
        school_id = school.json()["id"]

        admin = client.post(
            "/users",
            json={"email": "admin@example.test", "display_name": "Admin"},
        )
        admin_id = admin.json()["id"]
        assert client.put(
            f"/schools/{school_id}/memberships",
            json={"user_id": admin_id, "role": "ADMIN"},
        ).status_code == 200

        viewer = client.post(
            "/users",
            json={"email": "viewer3@example.test", "display_name": "Viewer"},
        )
        viewer_id = viewer.json()["id"]

        created = client.put(
            f"/schools/{school_id}/memberships",
            json={"user_id": viewer_id, "role": "VIEWER"},
            headers={"X-Actor-Id": admin_id},
        )
        assert created.status_code == 200

        listed = client.get(
            f"/schools/{school_id}/memberships",
            headers={"X-Actor-Id": admin_id},
        )
        assert listed.status_code == 200
        assert {item["user_id"] for item in listed.json()} == {admin_id, viewer_id}
