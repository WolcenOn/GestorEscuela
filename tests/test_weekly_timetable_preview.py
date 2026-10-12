from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.solver.weekly_timetable import (
    BusyInterval,
    LessonDemand,
    solve_weekly_timetable,
)
from gestor_escuela.web import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app, headers={"X-Actor-Role": "ADMIN"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_two_courses_use_distinct_durations_without_specialist_collisions() -> None:
    first = LessonDemand(
        "1A", "MAT", "SPECIALIST", 105, (45, 60),
        allowed_days=(0, 1, 2),
    )
    second = LessonDemand(
        "2A", "MAT", "SPECIALIST", 180, (90, 90),
        allowed_days=(0, 1, 2),
    )
    result = solve_weekly_timetable(
        (first, second),
        (BusyInterval(0, 540, 600, teacher_id="SPECIALIST"),),
        540, 720,
    )
    assert result.status == "feasible"
    assert sum(item.end - item.start for item in result.lessons if item.group_id == "1A") == 105
    assert sum(item.end - item.start for item in result.lessons if item.group_id == "2A") == 180
    first_durations = sorted(
        item.end - item.start for item in result.lessons if item.group_id == "1A"
    )
    second_durations = sorted(
        item.end - item.start for item in result.lessons if item.group_id == "2A"
    )
    assert first_durations == [45, 60]
    assert second_durations == [90, 90]
    for index, first_lesson in enumerate(result.lessons):
        for second_lesson in result.lessons[index + 1:]:
            if first_lesson.weekday != second_lesson.weekday:
                continue
            assert not (first_lesson.start < second_lesson.end
                        and second_lesson.start < first_lesson.end)


def test_pt_al_reserved_teacher_is_not_double_booked() -> None:
    result = solve_weekly_timetable(
        (LessonDemand("G1", "MAT", "PT1", 45, (45,), allowed_days=(0,)),),
        (BusyInterval(0, 540, 600, teacher_id="PT1"),),
        540, 645,
    )
    assert result.status == "feasible"
    assert result.lessons[0].start == 600


def test_insufficient_hard_capacity_is_explicitly_infeasible() -> None:
    result = solve_weekly_timetable(
        (LessonDemand("G1", "MAT", "P1", 90, (90,), allowed_days=(0,)),),
        (BusyInterval(0, 540, 600, group_id="G1"),),
        540, 630,
    )
    assert result.status == "infeasible"
    assert not result.lessons


def _payload() -> dict[str, object]:
    return {
        "start_time": "09:00",
        "end_time": "12:00",
        "lessons": [
            {
                "group_id": "1A", "subject_id": "MAT", "teacher_id": "P1",
                "weekly_minutes": 105, "durations": [45, 60],
                "allowed_days": [0, 1, 2], "max_sessions_per_day": 1,
            },
            {
                "group_id": "2A", "subject_id": "MAT", "teacher_id": "P1",
                "weekly_minutes": 180, "durations": [90, 90],
                "allowed_days": [0, 1, 2], "max_sessions_per_day": 1,
            },
        ],
        "busy": [
            {
                "weekday": 0, "start_time": "09:00", "end_time": "10:00",
                "teacher_id": "P1",
            }
        ],
    }


def test_planner_can_preview_but_cannot_persist_any_day_plan(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Matemáticas"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    result = client.post(
        f"/schools/{school_id}/weekly-timetable/preview", json=_payload()
    )
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "feasible"
    assert data["preview_only"] is True
    assert len(data["lessons"]) == 4
    assert client.get(f"/schools/{school_id}/day-plans").json() == []

    # The whole API remains scoped to the chosen school.
    other_school = client.post("/schools", json={"name": "Otro CEIP"})
    assert other_school.status_code == 201
    other_id = other_school.json()["id"]
    assert other_id != school_id


def test_invalid_weekly_durations_are_rejected(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "Validación"}).json()["id"]
    payload = _payload()
    payload["lessons"][0]["durations"] = [60, 60]
    response = client.post(f"/schools/{school_id}/weekly-timetable/preview", json=payload)
    assert response.status_code == 422


def test_viewer_cannot_request_full_weekly_preview(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "Privacidad"}).json()["id"]
    result = client.post(
        f"/schools/{school_id}/weekly-timetable/preview",
        json=_payload(),
        headers={"X-Actor-Role": "VIEWER"},
    )
    assert result.status_code == 403
