from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.auth_models import AuthSessionRow
from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.web import app


@contextmanager
def _client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
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
            yield client, testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _register(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/auth/register-school",
        json={
            "email": "sessions@example.test",
            "password": "correct horse battery staple",
            "display_name": "Admin",
            "school_name": "CEIP Sesiones",
        },
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/auth/login",
        json={
            "email": "sessions@example.test",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 200
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_user_can_list_and_revoke_one_own_session() -> None:
    with _client() as (client, _testing_session):
        registered = _register(client)
        first_token = str(registered["access_token"])
        logged_in = _login(client)
        current_token = str(logged_in["access_token"])

        listed = client.get("/auth/sessions", headers=_bearer(current_token))
        assert listed.status_code == 200
        sessions = listed.json()
        assert len(sessions) == 2
        assert sum(1 for item in sessions if item["current"]) == 1
        old_session = next(item for item in sessions if not item["current"])
        assert old_session["revoked_at"] is None
        assert old_session["last_seen_at"]

        revoked = client.delete(
            f"/auth/sessions/{old_session['id']}",
            headers=_bearer(current_token),
        )
        assert revoked.status_code == 204

        old_rejected = client.get("/auth/me", headers=_bearer(first_token))
        assert old_rejected.status_code == 401
        current_ok = client.get("/auth/me", headers=_bearer(current_token))
        assert current_ok.status_code == 200

        missing = client.delete(
            f"/auth/sessions/{uuid4()}",
            headers=_bearer(current_token),
        )
        assert missing.status_code == 404


def test_logout_all_revokes_every_session() -> None:
    with _client() as (client, _testing_session):
        registered = _register(client)
        first_token = str(registered["access_token"])
        logged_in = _login(client)
        second_token = str(logged_in["access_token"])

        response = client.post("/auth/logout-all", headers=_bearer(second_token))
        assert response.status_code == 204

        assert client.get("/auth/me", headers=_bearer(first_token)).status_code == 401
        assert client.get("/auth/me", headers=_bearer(second_token)).status_code == 401


def test_session_expires_after_idle_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SESSION_IDLE_MINUTES", "5")
    monkeypatch.setenv("AUTH_SESSION_TOUCH_INTERVAL_MINUTES", "1")

    with _client() as (client, testing_session):
        registered = _register(client)
        token = str(registered["access_token"])

        with testing_session() as session:
            row = session.scalar(select(AuthSessionRow))
            assert row is not None
            row.last_seen_at = datetime.now(UTC) - timedelta(minutes=6)
            session.commit()

        expired = client.get("/auth/me", headers=_bearer(token))
        assert expired.status_code == 401
        assert expired.json()["detail"] == "Authentication session is invalid or expired"

        with testing_session() as session:
            row = session.scalar(select(AuthSessionRow))
            assert row is not None
            assert row.revoked_at is not None


def test_active_session_refreshes_last_seen_without_extending_absolute_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_SESSION_IDLE_MINUTES", "120")
    monkeypatch.setenv("AUTH_SESSION_TOUCH_INTERVAL_MINUTES", "1")

    with _client() as (client, testing_session):
        registered = _register(client)
        token = str(registered["access_token"])

        with testing_session() as session:
            row = session.scalar(select(AuthSessionRow))
            assert row is not None
            old_last_seen = datetime.now(UTC) - timedelta(minutes=2)
            absolute_expiry = row.expires_at
            row.last_seen_at = old_last_seen
            session.commit()

        active = client.get("/auth/me", headers=_bearer(token))
        assert active.status_code == 200

        with testing_session() as session:
            row = session.scalar(select(AuthSessionRow))
            assert row is not None
            refreshed = row.last_seen_at
            if refreshed.tzinfo is None:
                refreshed = refreshed.replace(tzinfo=UTC)
            assert refreshed > old_last_seen
            assert row.expires_at == absolute_expiry
