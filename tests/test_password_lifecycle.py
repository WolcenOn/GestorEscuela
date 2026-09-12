from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api import password_reset_delivery
from gestor_escuela.api.auth_tokens import token_digest
from gestor_escuela.persistence.auth_models import AuthSessionRow, PasswordResetTokenRow
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
            "email": "account@example.test",
            "password": "initial secure password",
            "display_name": "Admin cuenta",
            "school_name": "CEIP Cuenta",
        },
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, password: str) -> dict[str, object]:
    response = client.post(
        "/auth/login",
        json={"email": "account@example.test", "password": password},
    )
    assert response.status_code == 200
    return response.json()


def _bearer(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_membership_includes_school_name() -> None:
    with _client() as (client, _testing_session):
        auth = _register(client)
        assert auth["memberships"] == [
            {
                "school_id": auth["school"]["id"],
                "school_name": "CEIP Cuenta",
                "user_id": auth["user"]["id"],
                "role": "ADMIN",
            }
        ]

        current = client.get("/auth/me", headers=_bearer(auth["access_token"]))
        assert current.status_code == 200
        assert current.json()["memberships"][0]["school_name"] == "CEIP Cuenta"


def test_change_password_requires_current_password_and_revokes_other_sessions() -> None:
    with _client() as (client, _testing_session):
        registered = _register(client)
        old_token = registered["access_token"]
        current = _login(client, "initial secure password")
        current_token = current["access_token"]

        rejected = client.post(
            "/auth/password/change",
            headers=_bearer(current_token),
            json={"current_password": "wrong password", "new_password": "new secure password"},
        )
        assert rejected.status_code == 401

        changed = client.post(
            "/auth/password/change",
            headers=_bearer(current_token),
            json={
                "current_password": "initial secure password",
                "new_password": "new secure password",
            },
        )
        assert changed.status_code == 204

        assert client.get("/auth/me", headers=_bearer(old_token)).status_code == 401
        assert client.get("/auth/me", headers=_bearer(current_token)).status_code == 200
        assert client.post(
            "/auth/login",
            json={"email": "account@example.test", "password": "initial secure password"},
        ).status_code == 401
        assert _login(client, "new secure password")["access_token"]


def test_reset_request_does_not_reveal_account_existence_and_stores_only_token_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        password_reset_delivery,
        "deliver_password_reset",
        lambda email, token: delivered.append((email, token)),
    )

    with _client() as (client, testing_session):
        _register(client)

        known = client.post(
            "/auth/password/reset-request",
            json={"email": "account@example.test"},
        )
        unknown = client.post(
            "/auth/password/reset-request",
            json={"email": "unknown@example.test"},
        )
        assert known.status_code == 202
        assert unknown.status_code == 202
        assert known.json() == unknown.json() == {"status": "accepted"}
        assert len(delivered) == 1
        email, raw_token = delivered[0]
        assert email == "account@example.test"

        with testing_session() as session:
            row = session.scalar(select(PasswordResetTokenRow))
            assert row is not None
            assert row.token_hash == token_digest(raw_token)
            assert raw_token not in row.token_hash


def test_reset_token_is_single_use_expires_and_revokes_existing_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[str] = []
    monkeypatch.setattr(
        password_reset_delivery,
        "deliver_password_reset",
        lambda _email, token: delivered.append(token),
    )

    with _client() as (client, testing_session):
        registered = _register(client)
        first_token = registered["access_token"]
        second = _login(client, "initial secure password")
        second_token = second["access_token"]

        requested = client.post(
            "/auth/password/reset-request",
            json={"email": "account@example.test"},
        )
        assert requested.status_code == 202
        raw_reset_token = delivered[-1]

        reset = client.post(
            "/auth/password/reset-confirm",
            json={"token": raw_reset_token, "new_password": "reset secure password"},
        )
        assert reset.status_code == 204
        assert client.get("/auth/me", headers=_bearer(first_token)).status_code == 401
        assert client.get("/auth/me", headers=_bearer(second_token)).status_code == 401

        reused = client.post(
            "/auth/password/reset-confirm",
            json={"token": raw_reset_token, "new_password": "another secure password"},
        )
        assert reused.status_code == 400
        assert _login(client, "reset secure password")["access_token"]

        client.post(
            "/auth/password/reset-request",
            json={"email": "account@example.test"},
        )
        expired_token = delivered[-1]
        with testing_session() as session:
            row = session.scalar(
                select(PasswordResetTokenRow).where(
                    PasswordResetTokenRow.token_hash == token_digest(expired_token)
                )
            )
            assert row is not None
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.commit()

        expired = client.post(
            "/auth/password/reset-confirm",
            json={"token": expired_token, "new_password": "expired secure password"},
        )
        assert expired.status_code == 400

        with testing_session() as session:
            active_sessions = session.scalars(
                select(AuthSessionRow).where(AuthSessionRow.revoked_at.is_(None))
            ).all()
            assert len(active_sessions) == 1
