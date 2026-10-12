from __future__ import annotations

from gestor_escuela.domain.models import Absence, Activity, ActivityType, Teacher, TeacherProfile
from gestor_escuela.solver.optimizer import SchoolDayOptimizer
from gestor_escuela.solver.slot_intervals import build_slot_conflicts


def test_slot_conflicts_include_partial_overlap_but_not_adjacency() -> None:
    conflicts = build_slot_conflicts(
        [
            ("S90", "09:00", "10:30"),
            ("S45", "10:00", "10:45"),
            ("NEXT", "10:45", "11:30"),
            ("LEGACY", None, None),
        ]
    )
    assert conflicts["S90"] == frozenset({"S90", "S45"})
    assert conflicts["S45"] == frozenset({"S90", "S45"})
    assert conflicts["NEXT"] == frozenset({"NEXT"})
    assert conflicts["LEGACY"] == frozenset({"LEGACY"})


def test_busy_specialist_is_not_considered_free_on_overlapping_slot() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher("P02", TeacherProfile.SPECIALIST, can_cover_groups=frozenset({"G1", "G2"})),
        Teacher("P03", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1"})),
    )
    activities = (
        Activity("A1", "S90", ActivityType.CLASS, "P01", group_id="G1"),
        Activity("A2", "S45", ActivityType.CLASS, "P02", group_id="G2"),
    )
    conflicts = build_slot_conflicts(
        [("S90", "09:00", "10:30"), ("S45", "10:00", "10:45")]
    )
    result = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P01", frozenset({"S90"})),),
        slot_conflicts=conflicts,
    )
    assert len(result.substitutions) == 1
    assert result.substitutions[0].substitute_teacher_id == "P03"


def test_two_overlapping_absent_classes_cannot_share_one_substitute() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher("P02", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G2"})),
        Teacher("P03", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1", "G2"})),
    )
    activities = (
        Activity("A1", "S90", ActivityType.CLASS, "P01", group_id="G1"),
        Activity("A2", "S45", ActivityType.CLASS, "P02", group_id="G2"),
    )
    conflicts = build_slot_conflicts(
        [("S90", "09:00", "10:30"), ("S45", "10:00", "10:45")]
    )
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P01", frozenset({"S90"})),
            Absence("P02", frozenset({"S45"})),
        ),
        slot_conflicts=conflicts,
    )
    assert len(solution.substitutions) == 1
    assert len(solution.uncovered) == 1
    assert solution.substitutions[0].substitute_teacher_id == "P03"
