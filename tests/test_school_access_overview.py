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
def client_with_db() -> Iterator[TestClient]:
    engine = create_engine("sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},poolclass=StaticPool)
    factory=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def session_override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session
    app.dependency_overrides[get_session]=session_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def register(client: TestClient, email: str) -> tuple[str,str]:
    response=client.post("/auth/register-school",json={
        "email":email,"password":"a sufficiently long password",
        "display_name":"Dirección",
        "school_name":"Centro ficticio",
    })
    assert response.status_code==201, response.text
    body=response.json()
    return body["school"]["id"],body["access_token"]


def invite(client: TestClient,school_id: str,token: str,email: str,role: str) -> dict:
    response=client.post(f"/schools/{school_id}/invitations",
        headers={"Authorization":f"Bearer {token}"},
        json={"email":email,"role":role,"expires_in_hours":48})
    assert response.status_code==201,response.text
    return response.json()


def test_admin_access_overview_is_scoped_and_does_not_expose_invitation_tokens() -> None:
    with client_with_db() as client:
        school,admin_token=register(client,"director@example.test")
        foreign_school,foreign_token=register(client,"other@example.test")
        invitation=invite(client,school,admin_token,"planner@example.test","PLANNER")
        pending=invite(client,school,admin_token,"viewer@example.test","VIEWER")
        acceptance=client.post("/auth/invitations/accept",json={
            "token":invitation["token"],
            "password":"another very long password",
            "display_name":"Jefatura",
        })
        assert acceptance.status_code==200,acceptance.text
        planner_token=acceptance.json()["access_token"]
        path=f"/schools/{school}/access-overview"
        overview=client.get(path,headers={"Authorization":f"Bearer {admin_token}"})
        assert overview.status_code==200,overview.text
        data=overview.json()
        assert len(data["members"])==2
        assert {row["role"] for row in data["members"]}=={"ADMIN","PLANNER"}
        assert all(row["access_status"]=="account_active" for row in data["members"])
        assert all(row["email_verified"] is False for row in data["members"])
        assert data["mailbox_verification_available"] is False
        statuses={row["email"]:row["status"] for row in data["invitations"]}
        assert statuses=={
            "planner@example.test":"accepted","viewer@example.test":"pending"
        }
        assert all(row["email_verified"] is False for row in data["invitations"])
        for secret in (invitation["token"],pending["token"],"password_hash","token_hash"):
            assert secret not in overview.text
        forbidden=client.get(path,headers={"Authorization":f"Bearer {planner_token}"})
        assert forbidden.status_code==403
        cross=client.get(path,headers={"Authorization":f"Bearer {foreign_token}"})
        assert cross.status_code==403
        spoof=client.get(path,headers={"X-Actor-Id":acceptance.json()["user"]["id"]})
        assert spoof.status_code in (401,403)
        foreign=client.get(f"/schools/{foreign_school}/access-overview",
            headers={"Authorization":f"Bearer {foreign_token}"})
        assert foreign.status_code==200
        assert len(foreign.json()["members"])==1
        assert foreign.json()["invitations"]==[]
