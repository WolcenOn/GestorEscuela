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


def _register(client: TestClient, email: str = "admin@example.test") -> None:
    response = client.post(
        "/auth/register-school",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Admin",
            "school_name": "CEIP Prueba",
        },
    )
    assert response.status_code == 201


def test_repeated_login_failures_are_throttled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_LOGIN_WINDOW_MINUTES", "15")
    monkeypatch.setenv("AUTH_LOGIN_BLOCK_MINUTES", "10")

    with _client() as client:
        _register(client)
        for _ in range(3):
            response = client.post(
                "/auth/login",
                json={"email": "ADMIN@example.test", "password": "wrong-password"},
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid email or password"

        blocked = client.post(
            "/auth/login",
            headers={"Origin": "https://wolcenon.github.io"},
            json={
                "email": "admin@example.test",
                "password": "correct horse battery staple",
            },
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        exposed = blocked.headers["access-control-expose-headers"].lower()
        assert "retry-after" in exposed
        assert blocked.json()["detail"] == "Too many failed login attempts. Try again later."


def test_unknown_accounts_are_throttled_without_revealing_account_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FAILURES", "2")

    with _client() as client:
        for _ in range(2):
            response = client.post(
                "/auth/login",
                json={"email": "missing@example.test", "password": "wrong-password"},
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid email or password"

        blocked = client.post(
            "/auth/login",
            json={"email": "missing@example.test", "password": "wrong-password"},
        )
        assert blocked.status_code == 429


def test_successful_login_clears_previous_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FAILURES", "3")

    with _client() as client:
        _register(client)
        failed = client.post(
            "/auth/login",
            json={"email": "admin@example.test", "password": "wrong-password"},
        )
        assert failed.status_code == 401

        success = client.post(
            "/auth/login",
            json={
                "email": "admin@example.test",
                "password": "correct horse battery staple",
            },
        )
        assert success.status_code == 200

        for _ in range(2):
            response = client.post(
                "/auth/login",
                json={"email": "admin@example.test", "password": "wrong-password"},
            )
            assert response.status_code == 401

        still_not_blocked = client.post(
            "/auth/login",
            json={
                "email": "admin@example.test",
                "password": "correct horse battery staple",
            },
        )
        assert still_not_blocked.status_code == 200
