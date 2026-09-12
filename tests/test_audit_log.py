from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.web import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", "true")
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


def test_mutating_school_request_is_audited_with_semantic_event(client: TestClient) -> None:
    school_response = client.post("/schools", json={"name": "CEIP Auditoría"})
    assert school_response.status_code == 201
    school_id = school_response.json()["id"]

    user_response = client.post(
        "/users",
        json={"email": "audit@example.test", "display_name": "Responsable Auditoría"},
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    response = client.put(
        f"/schools/{school_id}/memberships",
        json={"user_id": user_id, "role": "ADMIN"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")

    audit_response = client.get(
        f"/schools/{school_id}/audit-log",
        headers={"X-Actor-Id": user_id},
    )
    assert audit_response.status_code == 200
    rows = audit_response.json()
    assert rows
    latest = rows[0]
    assert latest["school_id"] == school_id
    assert latest["actor_role"] == "ADMIN"
    assert latest["event_type"] == "membership.update"
    assert latest["method"] == "PUT"
    assert latest["path"] == f"/schools/{school_id}/memberships"
    assert latest["status_code"] == 200
    assert latest["request_id"] == response.headers["X-Request-Id"]
