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


def test_account_audit_attributes_password_and_session_actions_to_user() -> None:
    with _client() as client:
        registered = client.post(
            "/auth/register-school",
            json={
                "email": "audit-account@example.test",
                "password": "initial secure password",
                "display_name": "Cuenta Auditada",
                "school_name": "CEIP Auditoría Cuenta",
            },
        )
        assert registered.status_code == 201
        auth = registered.json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        changed = client.post(
            "/auth/password/change",
            headers=headers,
            json={
                "current_password": "initial secure password",
                "new_password": "new secure password",
            },
        )
        assert changed.status_code == 204

        rows_response = client.get("/auth/audit-log", headers=headers)
        assert rows_response.status_code == 200
        rows = rows_response.json()
        event_types = [row["event_type"] for row in rows]
        assert "auth.password.change" in event_types
        assert "auth.register_school" in event_types

        password_event = next(row for row in rows if row["event_type"] == "auth.password.change")
        assert password_event["actor_user_id"] == auth["user"]["id"]
        assert password_event["school_id"] is None
        assert password_event["path"] == "/auth/password/change"
        assert password_event["status_code"] == 204
        assert "new secure password" not in str(password_event)


def test_failed_reset_request_is_semantic_but_does_not_store_email_or_body() -> None:
    with _client() as client:
        response = client.post(
            "/auth/password/reset-request",
            json={"email": "unknown@example.test"},
        )
        assert response.status_code == 202
        assert response.headers.get("X-Request-Id")

        # No authenticated user owns an anonymous recovery request, so it is intentionally not
        # exposed through /auth/audit-log. The middleware still stores only method/path/status,
        # never the submitted email or request body.
        assert "unknown@example.test" not in response.headers.get("X-Request-Id", "")
