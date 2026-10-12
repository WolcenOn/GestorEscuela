from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

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


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_registers_school_and_bearer_resolves_membership() -> None:
    with _client() as client:
        registered = client.post(
            "/auth/register-school",
            json={
                "email": "admin@example.test",
                "password": "correct horse battery staple",
                "display_name": "Admin Centro",
                "school_name": "CEIP Online",
            },
        )
        assert registered.status_code == 201
        body = registered.json()
        token = body["access_token"]
        school_id = body["school"]["id"]
        assert body["memberships"][0]["role"] == "ADMIN"

        context = client.get(
            f"/schools/{school_id}/auth/context",
            headers=_bearer(token),
        )
        assert context.status_code == 200
        assert context.json()["role"] == "ADMIN"
        assert context.json()["user_id"] == body["user"]["id"]


def test_admin_invites_planner_and_invited_user_accepts() -> None:
    with _client() as client:
        registered = client.post(
            "/auth/register-school",
            json={
                "email": "owner@example.test",
                "password": "owner password 123",
                "display_name": "Dirección",
                "school_name": "CEIP Invitaciones",
            },
        ).json()
        school_id = registered["school"]["id"]
        admin_token = registered["access_token"]

        invitation = client.post(
            f"/schools/{school_id}/invitations",
            headers=_bearer(admin_token),
            json={
                "email": "planner@example.test",
                "role": "PLANNER",
                "expires_in_hours": 48,
            },
        )
        assert invitation.status_code == 201
        invitation_body = invitation.json()
        assert invitation_body["role"] == "PLANNER"
        assert invitation_body["token"]

        listed = client.get(
            f"/schools/{school_id}/invitations",
            headers=_bearer(admin_token),
        )
        assert listed.status_code == 200
        assert listed.json()[0]["token"] is None

        accepted = client.post(
            "/auth/invitations/accept",
            json={
                "token": invitation_body["token"],
                "password": "planner password 123",
                "display_name": "Jefatura",
            },
        )
        assert accepted.status_code == 200
        accepted_body = accepted.json()
        assert accepted_body["memberships"][0]["role"] == "PLANNER"

        planner_token = accepted_body["access_token"]
        context = client.get(
            f"/schools/{school_id}/auth/context",
            headers=_bearer(planner_token),
        )
        assert context.status_code == 200
        assert context.json()["role"] == "PLANNER"

        forbidden = client.post(
            f"/schools/{school_id}/invitations",
            headers=_bearer(planner_token),
            json={"email": "viewer@example.test", "role": "VIEWER"},
        )
        assert forbidden.status_code == 403


def test_login_and_logout_revoke_bearer_session() -> None:
    with _client() as client:
        registered = client.post(
            "/auth/register-school",
            json={
                "email": "login@example.test",
                "password": "very secure password",
                "display_name": "Administrador",
                "school_name": "CEIP Login",
            },
        ).json()
        school_id = registered["school"]["id"]

        wrong = client.post(
            "/auth/login",
            json={"email": "login@example.test", "password": "incorrect password"},
        )
        assert wrong.status_code == 401

        login = client.post(
            "/auth/login",
            json={"email": "LOGIN@example.test", "password": "very secure password"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        context = client.get(
            f"/schools/{school_id}/auth/context",
            headers=_bearer(token),
        )
        assert context.status_code == 200

        logout = client.post("/auth/logout", headers=_bearer(token))
        assert logout.status_code == 204

        rejected = client.get(
            f"/schools/{school_id}/auth/context",
            headers=_bearer(token),
        )
        assert rejected.status_code == 401
