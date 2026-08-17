from __future__ import annotations

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    CandidateRejectionReason,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


def test_required_specialty_is_a_hard_constraint() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher(
            "P02",
            TeacherProfile.SUPPORT,
            substitution_count=0,
            can_cover_groups=frozenset({"G1"}),
        ),
        Teacher(
            "P03",
            TeacherProfile.SPECIALIST,
            substitution_count=100,
            can_cover_groups=frozenset({"G1"}),
            substitutions_last_7_days=20,
            substitutions_last_30_days=40,
            specialties=frozenset({"ENGLISH"}),
        ),
    )
    activity = Activity(
        id="A-G1-S1",
        slot_id="S1",
        activity_type=ActivityType.CLASS,
        teacher_id="P01",
        group_id="G1",
        required_specialty="ENGLISH",
    )

    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=(activity,),
        absences=(Absence("P01", frozenset({"S1"})),),
    )

    assert solution.substitutions[0].substitute_teacher_id == "P03"
    p02 = next(item for item in solution.candidate_assessments if item.teacher_id == "P02")
    assert p02.rejection_reason is CandidateRejectionReason.MISSING_SPECIALTY


def test_specialty_requirement_can_make_activity_uncovered() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher("P02", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1"})),
    )
    activity = Activity(
        id="A-G1-S1",
        slot_id="S1",
        activity_type=ActivityType.CLASS,
        teacher_id="P01",
        group_id="G1",
        required_specialty="MUSIC",
    )

    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=(activity,),
        absences=(Absence("P01", frozenset({"S1"})),),
    )

    assert not solution.substitutions
    assert len(solution.uncovered) == 1
