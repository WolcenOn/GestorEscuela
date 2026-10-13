"""Joint daily PT/AL absence regression tests (no pupil identity or deployment)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gestor_escuela.api.app import app
from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    CandidateRejectionReason,
    Priority,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.persistence.db import Base, get_session
from gestor_escuela.solver.flexible_specialty import FlexibleSpecialtySchoolDayOptimizer


def t(teacher_id: str, specialty: str | None = None, groups: tuple[str, ...] = ()) -> Teacher:
    return Teacher(
        teacher_id,
        TeacherProfile.PT if specialty == "PT" else
        TeacherProfile.AL if specialty == "AL" else TeacherProfile.TUTOR,
        can_cover_groups=frozenset(groups),
        specialties=frozenset([specialty]) if specialty else frozenset(),
    )

def activity(id: str, kind: ActivityType, teacher_id: str, *, group: str | None = None,
             slot: str = "S1") -> Activity:
    return Activity(
        id, slot, kind, teacher_id, group_id=group,
        required_specialty=kind.value if kind in {ActivityType.PT, ActivityType.AL} else None,
        priority=Priority.HIGH if kind in {ActivityType.PT, ActivityType.AL} else Priority.NORMAL,
        movable=False, cancelable=False,
    )

def solve(teachers: tuple[Teacher, ...], activities: tuple[Activity, ...],
          absences: tuple[Absence, ...]):
    return FlexibleSpecialtySchoolDayOptimizer().solve(
        teachers=teachers, activities=activities, absences=absences,
    )

def test_mixed_class_pt_is_a_replacement_need_without_group_id() -> None:
    solution = solve(
        (t("PT_ABSENT", "PT"), t("PT_SUBSTITUTE", "PT"), t("GENERAL", groups=("G1",))),
        (activity("PT_MIXED", ActivityType.PT, "PT_ABSENT"),),
        (Absence("PT_ABSENT", frozenset({"S1"})),),
    )
    assert len(solution.substitutions) == 1
    assert solution.substitutions[0].activity_id == "PT_MIXED"
    assert solution.substitutions[0].substitute_teacher_id == "PT_SUBSTITUTE"
    assert solution.substitutions[0].group_id == ""
    assert solution.coverage_ratio == 1.0
    invalid = next(x for x in solution.candidate_assessments if x.teacher_id == "GENERAL")
    assert invalid.rejection_reason is CandidateRejectionReason.MISSING_SPECIALTY

def test_al_support_needs_specialty_and_group_permission_when_known() -> None:
    solution = solve(
        (t("AL_ABSENT", "AL", ("G1",)),
         t("AL_WRONG_GROUP", "AL", ("G2",)),
         t("PT_ONLY", "PT", ("G1",)),
         t("AL_CORRECT", "AL", ("G1",))),
        (activity("AL_G1", ActivityType.AL, "AL_ABSENT", group="G1"),),
        (Absence("AL_ABSENT", frozenset({"S1"})),),
    )
    assert [s.substitute_teacher_id for s in solution.substitutions] == ["AL_CORRECT"]
    rejections = {x.teacher_id:x.rejection_reason for x in solution.candidate_assessments}
    assert rejections["AL_WRONG_GROUP"] is CandidateRejectionReason.INCOMPATIBLE_GROUP
    assert rejections["PT_ONLY"] is CandidateRejectionReason.MISSING_SPECIALTY

def test_multiple_absences_jointly_compete_for_only_one_qualified_pt() -> None:
    solution = solve(
        (t("PT1", "PT"), t("PT2", "PT"), t("SUBSTITUTE", "PT")),
        (activity("A", ActivityType.PT, "PT1"),
         activity("B", ActivityType.PT, "PT2")),
        (Absence("PT1", frozenset({"S1"})), Absence("PT2", frozenset({"S1"}))),
    )
    assert len(solution.substitutions) == 1
    assert len(solution.uncovered) == 1
    assert solution.coverage_ratio == .5
    assert {x.activity_id for x in (*solution.substitutions, *solution.uncovered)} == {"A","B"}

def test_pt_and_al_are_not_interchangeable_without_both_specialties() -> None:
    solution = solve(
        (t("PT_ABSENT", "PT"), t("AL_ABSENT", "AL"), t("PT_SUB", "PT")),
        (activity("PT", ActivityType.PT, "PT_ABSENT"),
         activity("AL", ActivityType.AL, "AL_ABSENT")),
        (Absence("PT_ABSENT", frozenset({"S1"})),
         Absence("AL_ABSENT", frozenset({"S1"}))),
    )
    assert [s.activity_id for s in solution.substitutions] == ["PT"]
    assert [u.activity_id for u in solution.uncovered] == ["AL"]

def test_supports_remain_protected_when_covering_other_absences() -> None:
    solution = solve(
        (t("PT_ABSENT", "PT"), t("PT_BUSY", "PT")),
        (activity("MISSING_PT", ActivityType.PT, "PT_ABSENT"),
         activity("FIXED_PT", ActivityType.PT, "PT_BUSY")),
        (Absence("PT_ABSENT", frozenset({"S1"})),),
    )
    assert not solution.substitutions
    assert len(solution.uncovered) == 1
    rejected = next(x for x in solution.candidate_assessments if x.teacher_id == "PT_BUSY")
    assert rejected.rejection_reason is CandidateRejectionReason.IMMOVABLE_ACTIVITY

def test_non_teaching_support_blocks_never_generate_a_substitution_need() -> None:
    solution = solve(
        (t("ABS", "PT"), t("SUB", "PT")),
        (activity("NO", ActivityType.SUPPORT, "ABS"),),
        (Absence("ABS", frozenset({"S1"})),),
    )
    assert solution.substitutions == ()
    assert solution.uncovered == ()

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread":False},
                           poolclass=StaticPool)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def session_override() -> Generator[Session, None, None]:
        with maker() as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with TestClient(app, headers={"X-Actor-Role":"ADMIN"}) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)

def test_academic_day_api_with_class_pt_al_and_group_less_pt(client: TestClient) -> None:
    school = client.post("/schools", json={"name":"Fictitious inclusive school"})
    assert school.status_code == 201
    root = f"/schools/{school.json()['id']}"
    configuration = {
        "groups":[{"id":"G1","label":"Class 1"}],
        "time_slots":[{"id":"S1","label":"09:00–09:45","order":1,
                       "start_time":"09:00","end_time":"09:45"}],
        "teachers":[
            {"id":"ABS_CLASS","profile":"TUTOR","can_cover_groups":["G1"]},
            {"id":"ABS_PT","profile":"PT","specialties":["PT"],"can_cover_groups":["G1"]},
            {"id":"ABS_AL","profile":"AL","specialties":["AL"],"can_cover_groups":["G1"]},
            {"id":"SUB_CLASS","profile":"TUTOR","can_cover_groups":["G1"]},
            {"id":"SUB_PT","profile":"PT","specialties":["PT"]},
            {"id":"SUB_AL","profile":"AL","specialties":["AL"],"can_cover_groups":["G1"]},
        ],
        "activities":[
            {"id":"CLASS","activity_type":"CLASS","slot_id":"S1","weekday":0,
             "teacher_id":"ABS_CLASS","group_id":"G1"},
            {"id":"PT_MIXED","activity_type":"PT","slot_id":"S1","weekday":0,
             "teacher_id":"ABS_PT","group_id":None,"required_specialty":"PT",
             "priority":40},
            {"id":"AL_G1","activity_type":"AL","slot_id":"S1","weekday":0,
             "teacher_id":"ABS_AL","group_id":"G1","required_specialty":"AL",
             "priority":40},
        ],
    }
    saved = client.put(f"{root}/configuration",json=configuration)
    assert saved.status_code == 200, saved.text
    plan = client.post(f"{root}/day-plans",json={"plan_date":"2026-10-12"})
    assert plan.status_code == 201
    response = client.post(f"{root}/day-plans/{plan.json()['id']}/solve-academic",
        json={"absences":[
            {"teacher_id":"ABS_CLASS","slot_ids":["S1"]},
            {"teacher_id":"ABS_PT","slot_ids":["S1"]},
            {"teacher_id":"ABS_AL","slot_ids":["S1"]},
        ],"expected_version":1})
    assert response.status_code == 200, response.text
    data = response.json()
    sol = data["payload"]["solution"]
    assert len(sol["substitutions"]) == 3, sol
    assert sol["uncovered"] == []
    assert {x["activity_id"]:x["substitute_teacher_id"] for x in sol["substitutions"]} == {
        "CLASS":"SUB_CLASS","PT_MIXED":"SUB_PT","AL_G1":"SUB_AL",
    }
    assert sol["coverage_ratio"] == 1
    assert data["status"] == "SOLVED"
    assert data["version"] == 2

def test_group_less_al_without_qualified_candidate_is_uncovered() -> None:
    solution = solve(
        (t("ABS_AL", "AL"), t("ONLY_PT", "PT")),
        (activity("AL_GROUPLESS", ActivityType.AL, "ABS_AL"),),
        (Absence("ABS_AL", frozenset({"S1"})),),
    )
    assert not solution.substitutions
    assert len(solution.uncovered) == 1
    assert solution.uncovered[0].group_id == ""
