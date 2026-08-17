from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api.app import app
from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.persistence.models import SchoolMembershipRow, SchoolRow, UserRow


def test_school_membership_is_source_of_truth_for_actor_role() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    school_id = uuid4()
    other_school_id = uuid4()
    user_id = uuid4()
    with testing_session() as setup:
        setup.add_all(
            [
                SchoolRow(id=school_id, name="CEIP A"),
                SchoolRow(id=other_school_id, name="CEIP B"),
                UserRow(id=user_id, email="viewer@example.test", display_name="Viewer"),
                SchoolMembershipRow(
                    school_id=school_id,
                    user_id=user_id,
                    role="VIEWER",
                ),
            ]
        )
        setup.commit()

    def override_session() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = {"X-Actor-Id": str(user_id), "X-Actor-Role": "ADMIN"}

            allowed = client.get(
                f"/schools/{school_id}/configuration",
                headers=headers,
            )
            assert allowed.status_code == 200

            privilege_escalation = client.put(
                f"/schools/{school_id}/configuration",
                headers=headers,
                json={
                    "groups": [{"id": "G1", "label": "1º A"}],
                    "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
                    "teachers": [
                        {
                            "id": "P01",
                            "profile": "TUTOR",
                            "can_cover_groups": ["G1"],
                        }
                    ],
                    "activities": [
                        {
                            "id": "A-S1-G1",
                            "slot_id": "S1",
                            "activity_type": "CLASS",
                            "teacher_id": "P01",
                            "group_id": "G1",
                        }
                    ],
                },
            )
            assert privilege_escalation.status_code == 403
            assert "ADMIN role required" in privilege_escalation.json()["detail"]

            other_school = client.get(
                f"/schools/{other_school_id}/configuration",
                headers=headers,
            )
            assert other_school.status_code == 403
            assert "not a member" in other_school.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
