from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.solver.group_support import GroupParticipant, GroupSupportDemand
from gestor_escuela.solver.weekly_diagnostics import explain_weekly_infeasible
from gestor_escuela.solver.weekly_timetable import (
    BusyInterval,
    LessonDemand,
    SupportDemand,
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


def test_pt_al_can_extract_from_allowed_subject_but_not_blocked_subject() -> None:
    lesson = LessonDemand(
        "1A", "MAT", "MATH", 90, (90,),
        allowed_days=(0,), max_sessions_per_day=1,
    )
    support = SupportDemand(
        "request-1", "PT", "P-PT", "anonymous-pupil", "1A", 45, (45,),
        allowed_days=(0,), max_sessions_per_day=1,
    )
    allowed = solve_weekly_timetable((lesson,), (), 540, 630, supports=(support,))
    assert allowed.status == "feasible"
    assert allowed.supports[0].weekday == 0
    assert allowed.supports[0].start < allowed.lessons[0].end
    blocked = solve_weekly_timetable(
        (lesson,), (), 540, 630,
        supports=(
            SupportDemand(
                "request-1", "PT", "P-PT", "anonymous-pupil", "1A",
                45, (45,), blocked_subjects=("MAT",), allowed_days=(0,),
            ),
        ),
    )
    assert blocked.status == "infeasible"
    assert not blocked.supports


def test_two_support_services_never_double_book_one_pupil() -> None:
    lesson = LessonDemand("1A", "MAT", "MATH", 45, (45,), allowed_days=(0,))
    pt = SupportDemand(
        "r-pt", "PT", "PT-PRO", "anon-1", "1A", 45, (45,), allowed_days=(0,)
    )
    al = SupportDemand(
        "r-al", "AL", "AL-PRO", "anon-1", "1A", 45, (45,), allowed_days=(0,)
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 630, supports=(pt, al),
    )
    assert result.status == "feasible"
    assert len(result.supports) == 2
    a, b = result.supports
    assert a.end <= b.start or b.end <= a.start

    impossible = solve_weekly_timetable(
        (lesson,), (), 540, 615, supports=(pt, al),
    )
    assert impossible.status == "infeasible"


def test_existing_pt_al_session_counts_as_occupied_pupil_and_teacher_time() -> None:
    lesson = LessonDemand("1A", "MAT", "MATH", 45, (45,), allowed_days=(0,))
    support = SupportDemand(
        "remaining", "PT", "PT-PRO", "anon-pupil", "1A",
        45, (45,), allowed_days=(0,),
    )
    fixed = BusyInterval(
        weekday=0, start=540, end=585,
        teacher_id="PT-PRO", pupil_token="anon-pupil",
    )
    result = solve_weekly_timetable(
        (lesson,), (fixed,), 540, 630, supports=(support,),
    )
    assert result.status == "feasible"
    assert result.supports[0].start == 585


def test_api_accepts_opaque_support_and_never_returns_participants(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP PT AL"}).json()["id"]
    payload = _payload()
    payload["supports"] = [
        {
            "request_id": "request-one",
            "service": "PT",
            "teacher_id": "PT-TEACHER",
            "pupil_token": "request-opaque-student-token",
            "group_id": "1A",
            "weekly_minutes": 45,
            "durations": [45],
            "blocked_subjects": ["MAT"],
            "allowed_days": [0, 1, 2],
        }
    ]
    res = client.post(f"/schools/{school_id}/weekly-timetable/preview", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "feasible"
    assert data["preview_only"] is True
    assert len(data["supports"]) == 1
    assert data["supports"][0]["service"] == "PT"
    assert "pupil_token" not in str(data)
    assert "request-opaque-student-token" not in str(data)
    assert client.get(f"/schools/{school_id}/day-plans").json() == []


def test_api_rejects_unlinked_support_and_incorrect_minutes(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Validación AL"}).json()["id"]
    payload = _payload()
    payload["supports"] = [{
        "request_id": "r-al", "service": "AL", "teacher_id": "AL-PRO",
        "pupil_token": "opaque-2", "group_id": "UNLINKED",
        "weekly_minutes": 45, "durations": [60],
    }]
    response = client.post(f"/schools/{school_id}/weekly-timetable/preview", json=payload)
    assert response.status_code == 422
    payload["supports"][0]["durations"] = [45]
    response = client.post(f"/schools/{school_id}/weekly-timetable/preview", json=payload)
    assert response.status_code == 422


def test_shared_pt_group_counts_exact_minutes_for_two_different_goals() -> None:
    lesson = LessonDemand("1A", "MAT", "MATH", 45, (45,), allowed_days=(0,))
    group = GroupSupportDemand(
        "group-1", "PT", "PRO-PT", 45,
        (
            GroupParticipant("opaque-90", "1A", 90),
            GroupParticipant("opaque-45", "1A", 45),
        ),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 720, group_supports=(group,),
    )
    assert result.status == "feasible"
    assert len(result.group_supports) == 2
    minutes = {"opaque-90": 0, "opaque-45": 0}
    for session in result.group_supports:
        assert session.end - session.start == 45
        for token in session.participant_tokens:
            minutes[token] += 45
    assert minutes == {"opaque-90": 90, "opaque-45": 45}
    assert sorted(len(item.participant_tokens) for item in result.group_supports) == [1, 2]
    assert all(item.weekday == 0 for item in result.group_supports)


def test_grouped_and_individual_pt_al_never_overlap_same_pupil() -> None:
    lesson = LessonDemand("1A", "MAT", "MAT-T", 45, (45,), allowed_days=(0,))
    group = GroupSupportDemand(
        "group-pt", "PT", "T-PT", 45,
        (GroupParticipant("pupil-token", "1A", 45),),
        allowed_days=(0,),
    )
    individual = SupportDemand(
        "individual-al", "AL", "T-AL", "pupil-token", "1A", 45, (45,),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 630, supports=(individual,),
        group_supports=(group,),
    )
    assert result.status == "feasible"
    a = result.group_supports[0]
    b = result.supports[0]
    assert a.end <= b.start or b.end <= a.start


def test_blocked_subject_prevents_group_pupil_extraction() -> None:
    lesson = LessonDemand("1A", "MAT", "MAT-T", 90, (90,), allowed_days=(0,))
    group = GroupSupportDemand(
        "group-pt", "PT", "T-PT", 45,
        (
            GroupParticipant("student-a", "1A", 45, blocked_subjects=("MAT",)),
            GroupParticipant("student-b", "1A", 45),
        ),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 630, group_supports=(group,),
    )
    assert result.status == "infeasible"


def test_avoided_extraction_is_soft_not_forbidden_for_group() -> None:
    lesson = LessonDemand("1A", "MAT", "MAT-T", 90, (90,), allowed_days=(0,))
    avoided = GroupSupportDemand(
        "group-pt", "PT", "T-PT", 45,
        (GroupParticipant("student-a", "1A", 45, avoided_subjects=("MAT",)),),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 630, group_supports=(avoided,),
    )
    assert result.status == "feasible"
    assert len(result.group_supports) == 1


def test_avoided_extraction_chooses_non_overlapping_time_when_possible() -> None:
    lesson = LessonDemand("1A", "MAT", "MAT-T", 45, (45,), allowed_days=(0,))
    avoided = GroupSupportDemand(
        "group-pt", "PT", "T-PT", 45,
        (GroupParticipant("student-a", "1A", 45, avoided_subjects=("MAT",)),),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        (lesson,), (), 540, 630, group_supports=(avoided,),
    )
    assert result.status == "feasible"
    class_block = result.lessons[0]
    support_block = result.group_supports[0]
    assert class_block.end <= support_block.start or support_block.end <= class_block.start


def test_api_group_support_returns_counts_but_never_student_tokens(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Grupo PT"}).json()["id"]
    payload = _payload()
    payload["group_supports"] = [{
        "request_id": "group-1",
        "service": "PT",
        "teacher_id": "T-PT",
        "session_minutes": 45,
        "participants": [
            {"pupil_token": "opaque-90", "group_id": "1A", "weekly_minutes": 90},
            {"pupil_token": "opaque-45", "group_id": "1A", "weekly_minutes": 45},
        ],
    }]
    response = client.post(
        f"/schools/{school_id}/weekly-timetable/preview", json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "feasible"
    assert data["preview_only"] is True
    assert sorted(row["participant_count"] for row in data["group_supports"]) == [1, 2]
    assert "opaque-90" not in str(data)
    assert "opaque-45" not in str(data)
    assert client.get(f"/schools/{school_id}/day-plans").json() == []


def test_api_group_support_rejects_excess_pupil_minutes(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Objetivos"}).json()["id"]
    payload = _payload()
    payload["group_supports"] = [{
        "request_id": "group-1",
        "service": "AL",
        "teacher_id": "T-AL",
        "session_minutes": 45,
        "participants": [
            {"pupil_token": "one", "group_id": "1A", "weekly_minutes": 60},
        ],
    }]
    response = client.post(
        f"/schools/{school_id}/weekly-timetable/preview", json=payload,
    )
    assert response.status_code == 422


def test_api_refuses_duplicate_pupil_goals_in_multiple_groups(client: TestClient) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Duplicados"}).json()["id"]
    payload = _payload()
    payload["group_supports"] = [
        {
            "request_id": "first", "service": "PT", "teacher_id": "PT-1",
            "session_minutes": 45,
            "participants": [{
                "pupil_token": "shared", "group_id": "1A", "weekly_minutes": 45,
            }],
        },
        {
            "request_id": "second", "service": "PT", "teacher_id": "PT-2",
            "session_minutes": 45,
            "participants": [{
                "pupil_token": "shared", "group_id": "1A", "weekly_minutes": 45,
            }],
        },
    ]
    response = client.post(
        f"/schools/{school_id}/weekly-timetable/preview", json=payload,
    )
    assert response.status_code == 422


def test_cross_class_pt_group_respects_each_pupils_blocked_subjects() -> None:
    lessons = (
        LessonDemand("1A", "MAT", "T-MAT-A", 45, (45,), allowed_days=(0,)),
        LessonDemand("1B", "MAT", "T-MAT-B", 45, (45,), allowed_days=(0,)),
    )
    grouped = GroupSupportDemand(
        "cross-class-pt", "PT", "PT-ONE", 45,
        (
            GroupParticipant("pupil-1a", "1A", 45, blocked_subjects=("MAT",)),
            GroupParticipant("pupil-1b", "1B", 45),
        ),
        allowed_days=(0,),
    )
    result = solve_weekly_timetable(
        lessons, (), 540, 630, group_supports=(grouped,),
    )
    assert result.status == "feasible"
    session = result.group_supports[0]
    assert len(session.participant_tokens) == 2
    mat_1a = next(lesson for lesson in result.lessons if lesson.group_id == "1A")
    assert mat_1a.end <= session.start or session.end <= mat_1a.start


def test_diagnostics_show_overloaded_specialist_capacity_without_pupils() -> None:
    lessons = (
        LessonDemand("1A", "MAT", "P-SPECIAL", 105, (45, 60), allowed_days=(0, 1, 2)),
    )
    busy = tuple(
        BusyInterval(day, 540, 705, teacher_id="P-SPECIAL") for day in range(5)
    )
    result = solve_weekly_timetable(lessons, busy, 540, 720)
    assert result.status == "infeasible"
    reasons = explain_weekly_infeasible(lessons, (), (), busy, 540, 720)
    assert any("1A / MAT" in reason and "105 min" in reason for reason in reasons)
    assert any("Profesional P-SPECIAL" in reason for reason in reasons)
    assert "pupil_token" not in str(reasons)


def test_diagnostics_flag_overlapping_existing_specialist_blocks() -> None:
    lessons = (LessonDemand("1A", "MAT", "P1", 45, (45,), allowed_days=(0,)),)
    busy = (
        BusyInterval(0, 540, 600, teacher_id="P1"),
        BusyInterval(0, 570, 630, teacher_id="P1"),
    )
    result = solve_weekly_timetable(lessons, busy, 540, 660)
    assert result.status == "infeasible"
    reasons = explain_weekly_infeasible(lessons, (), (), busy, 540, 660)
    assert any("bloqueos fijos" in reason and "P1" in reason for reason in reasons)


def test_preview_api_returns_concrete_reasons_for_teacher_overload(
    client: TestClient,
) -> None:
    school_id = client.post("/schools", json={"name": "CEIP Diagnosticos"}).json()["id"]
    payload = _payload()
    payload["busy"] = [
        {
            "weekday": weekday,
            "start_time": "09:00",
            "end_time": "11:45",
            "teacher_id": "P1",
        }
        for weekday in range(5)
    ]
    response = client.post(
        f"/schools/{school_id}/weekly-timetable/preview", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "infeasible"
    assert any("Profesional P1" in reason for reason in data["reasons"])
    assert data["preview_only"] is True
    assert client.get(f"/schools/{school_id}/day-plans").json() == []
