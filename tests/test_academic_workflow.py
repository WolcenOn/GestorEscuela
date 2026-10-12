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
def client() -> Generator[TestClient, None, None]:
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
    engine.dispose()


def configuration() -> dict[str, object]:
    return {
        "groups": [
            {"id": "G1", "label": "1º A", "stage": "Primaria", "tutor_teacher_id": "P01"}
        ],
        "subjects": [
            {"id": "MAT", "label": "Matemáticas"},
        ],
        "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
        "teachers": [
            {
                "id": "P01",
                "display_name": "Ana",
                "profile": "TUTOR",
                "can_cover_groups": ["G1"],
            },
            {
                "id": "P02",
                "display_name": "Luis",
                "profile": "SUPPORT",
                "can_cover_groups": ["G1"],
            },
        ],
        "activities": [
            {
                "id": "MON-G1-S1",
                "weekday": 0,
                "slot_id": "S1",
                "activity_type": "CLASS",
                "teacher_id": "P01",
                "group_id": "G1",
                "subject_id": "MAT",
                "priority": 30,
            },
            {
                "id": "TUE-G1-S1",
                "weekday": 1,
                "slot_id": "S1",
                "activity_type": "CLASS",
                "teacher_id": "P02",
                "group_id": "G1",
                "subject_id": "MAT",
                "priority": 30,
            },
        ],
    }


def test_academic_configuration_round_trip(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Académico"})
    assert school.status_code == 201
    school_id = school.json()["id"]

    saved = client.put(
        f"/schools/{school_id}/academic-configuration",
        json=configuration(),
    )
    assert saved.status_code == 200

    read = client.get(f"/schools/{school_id}/academic-configuration")
    assert read.status_code == 200
    payload = read.json()
    assert payload["subjects"][0]["label"] == "Matemáticas"
    assert payload["groups"][0]["tutor_teacher_id"] == "P01"
    assert payload["teachers"][0]["display_name"] == "Ana"
    assert {item["weekday"] for item in payload["activities"]} == {0, 1}


def test_academic_solver_only_loads_selected_weekday(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Semana"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    assert client.put(
        f"/schools/{school_id}/academic-configuration",
        json=configuration(),
    ).status_code == 200

    plan = client.post(
        f"/schools/{school_id}/day-plans",
        json={"plan_date": "2026-08-17"},
    )
    assert plan.status_code == 201

    solved = client.post(
        f"/schools/{school_id}/day-plans/{plan.json()['id']}/solve-academic",
        json={"absences": [{"teacher_id": "P01", "slot_ids": ["S1"]}]},
    )
    assert solved.status_code == 200
    substitutions = solved.json()["payload"]["solution"]["substitutions"]
    assert len(substitutions) == 1
    assert substitutions[0]["substitute_teacher_id"] == "P02"


@pytest.mark.parametrize(
    ("second_weekday", "expected_status"),
    [(0, 422), (None, 422), (1, 200)],
)
def test_specialist_cannot_be_double_booked_across_classes(
    client: TestClient, second_weekday: int | None, expected_status: int
) -> None:
    school = client.post("/schools", json={"name": "CEIP Sin Solapes"})
    assert school.status_code == 201
    payload = configuration()
    groups = payload["groups"]
    activities = payload["activities"]
    assert isinstance(groups, list)
    assert isinstance(activities, list)
    groups.append({"id": "G2", "label": "2º A", "stage": "Primaria"})
    # A specialist (or PT/AL professional) is shared by both classes.
    activities[1]["teacher_id"] = "P01"
    activities[1]["group_id"] = "G2"
    activities[1]["weekday"] = second_weekday
    result = client.put(
        f"/schools/{school.json()['id']}/academic-configuration",
        json=payload,
    )
    assert result.status_code == expected_status
    if expected_status == 422:
        assert "Teacher P01" in result.json()["detail"]
        assert "slot S1" in result.json()["detail"]


@pytest.mark.parametrize(
    ("second_start", "second_end", "expected_status"),
    [
        ("10:00", "10:45", 422),  # Partial overlap with a 90-minute block.
        ("10:30", "11:15", 200),  # Adjacent blocks are allowed.
        ("09:00", "09:45", 422),  # Full overlap with different slot IDs.
    ],
)
def test_unequal_length_slots_reject_teacher_overlap(
    client: TestClient,
    second_start: str,
    second_end: str,
    expected_status: int,
) -> None:
    school = client.post("/schools", json={"name": "CEIP Intervalos"})
    assert school.status_code == 201
    payload = configuration()
    payload["groups"].append({"id": "G2", "label": "2º A", "stage": "Primaria"})
    payload["time_slots"][0].update({"start_time": "09:00", "end_time": "10:30"})
    payload["time_slots"].append(
        {
            "id": "S2",
            "label": "Segundo bloque",
            "order": 2,
            "start_time": second_start,
            "end_time": second_end,
        }
    )
    second_activity = payload["activities"][1]
    second_activity.update(
        {"weekday": 0, "slot_id": "S2", "teacher_id": "P01", "group_id": "G2"}
    )

    saved = client.put(
        f"/schools/{school.json()['id']}/academic-configuration",
        json=payload,
    )
    assert saved.status_code == expected_status
    if expected_status == 422:
        detail = saved.json()["detail"]
        assert "Teacher P01" in detail
        assert "S1" in detail and "S2" in detail
    else:
        read = client.get(
            f"/schools/{school.json()['id']}/academic-configuration"
        )
        assert read.status_code == 200
        assert read.json()["time_slots"] == payload["time_slots"]


def test_same_class_cannot_have_two_teachers_at_once(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Aula Unica"})
    assert school.status_code == 201
    payload = configuration()
    payload["time_slots"][0].update({"start_time": "09:00", "end_time": "10:30"})
    payload["time_slots"].append(
        {
            "id": "S2", "label": "Solapado", "order": 2,
            "start_time": "10:00", "end_time": "10:45",
        }
    )
    payload["activities"][1].update({"weekday": 0, "slot_id": "S2"})
    saved = client.put(
        f"/schools/{school.json()['id']}/academic-configuration",
        json=payload,
    )
    assert saved.status_code == 422
    assert "Group G1" in saved.json()["detail"]


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [
        ("09:00", None),
        (None, "10:30"),
        ("10:30", "09:00"),
        ("09:05", "10:30"),
        ("09:00", "12:15"),
        ("09:xx", "10:00"),
    ],
)
def test_invalid_slot_ranges_are_rejected_before_saving(
    client: TestClient, start_time: str | None, end_time: str | None
) -> None:
    school = client.post("/schools", json={"name": "CEIP Validacion"})
    assert school.status_code == 201
    payload = configuration()
    payload["time_slots"][0].update(
        {"start_time": start_time, "end_time": end_time}
    )
    saved = client.put(
        f"/schools/{school.json()['id']}/academic-configuration",
        json=payload,
    )
    assert saved.status_code == 422


def test_legacy_slots_remain_valid_without_times(client: TestClient) -> None:
    school = client.post("/schools", json={"name": "CEIP Compatibilidad"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    payload = configuration()
    assert client.put(
        f"/schools/{school_id}/academic-configuration", json=payload
    ).status_code == 200
    read = client.get(f"/schools/{school_id}/academic-configuration")
    assert read.status_code == 200
    assert read.json()["time_slots"][0]["start_time"] is None
    assert read.json()["time_slots"][0]["end_time"] is None


def test_academic_solver_does_not_use_busy_overlapping_specialist(
    client: TestClient,
) -> None:
    school = client.post("/schools", json={"name": "CEIP Especialistas"})
    assert school.status_code == 201
    school_id = school.json()["id"]
    payload = configuration()
    payload["groups"].append({"id": "G2", "label": "2º A", "stage": "Primaria"})
    payload["time_slots"][0].update({"start_time": "09:00", "end_time": "10:30"})
    payload["time_slots"].append(
        {
            "id": "S2", "label": "10:00-10:45", "order": 2,
            "start_time": "10:00", "end_time": "10:45",
        }
    )
    payload["teachers"].append(
        {
            "id": "P03", "display_name": "Apoyo libre",
            "profile": "SUPPORT", "can_cover_groups": ["G1"],
        }
    )
    payload["activities"][1].update(
        {"weekday": 0, "slot_id": "S2", "group_id": "G2"}
    )
    assert client.put(
        f"/schools/{school_id}/academic-configuration", json=payload
    ).status_code == 200
    plan = client.post(
        f"/schools/{school_id}/day-plans", json={"plan_date": "2026-08-17"}
    )
    assert plan.status_code == 201
    result = client.post(
        f"/schools/{school_id}/day-plans/{plan.json()['id']}/solve-academic",
        json={"absences": [{"teacher_id": "P01", "slot_ids": ["S1"]}]},
    )
    assert result.status_code == 200
    substitutions = result.json()["payload"]["solution"]["substitutions"]
    assert len(substitutions) == 1
    assert substitutions[0]["substitute_teacher_id"] == "P03"


def test_pt_al_may_extract_pupils_during_ordinary_class(
    client: TestClient,
) -> None:
    school = client.post("/schools", json={"name": "CEIP Apoyo compatible"})
    assert school.status_code == 201
    payload = configuration()
    payload["time_slots"][0].update({"start_time": "09:00", "end_time": "09:45"})
    payload["activities"][1].update(
        {
            "weekday": 0,
            "slot_id": "S1",
            "group_id": "G1",
            "activity_type": "PT",
            "subject_id": None,
        }
    )
    saved = client.put(
        f"/schools/{school.json()['id']}/academic-configuration",
        json=payload,
    )
    assert saved.status_code == 200
    read = client.get(
        f"/schools/{school.json()['id']}/academic-configuration"
    )
    assert read.status_code == 200
    assert len(read.json()["activities"]) == 2
