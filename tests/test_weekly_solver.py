from __future__ import annotations

from datetime import date

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.solver.weekly import SchoolWeekOptimizer, WeekDayProblem


def test_weekly_solver_carries_fairness_load_between_days() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher("P02", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1"})),
        Teacher("P03", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1"})),
    )
    activities = (
        Activity(
            id="A-G1-S1",
            slot_id="S1",
            activity_type=ActivityType.CLASS,
            teacher_id="P01",
            group_id="G1",
        ),
    )
    absence = (Absence("P01", frozenset({"S1"})),)
    days = (
        WeekDayProblem(date(2026, 9, 7), activities, absence),
        WeekDayProblem(date(2026, 9, 8), activities, absence),
    )

    result = SchoolWeekOptimizer().solve(teachers=teachers, days=days)

    first = result.days[0].solution.substitutions[0].substitute_teacher_id
    second = result.days[1].solution.substitutions[0].substitute_teacher_id
    assert first != second
    assert result.uncovered_count == 0

    final_by_id = {teacher.id: teacher for teacher in result.final_teachers}
    assert final_by_id[first].substitutions_last_7_days == 1
    assert final_by_id[second].substitutions_last_7_days == 1


def test_weekly_solver_orders_days_chronologically() -> None:
    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, can_cover_groups=frozenset({"G1"})),
        Teacher("P02", TeacherProfile.SUPPORT, can_cover_groups=frozenset({"G1"})),
    )
    activities = (
        Activity("A-G1-S1", "S1", ActivityType.CLASS, "P01", group_id="G1"),
    )
    absence = (Absence("P01", frozenset({"S1"})),)

    result = SchoolWeekOptimizer().solve(
        teachers=teachers,
        days=(
            WeekDayProblem(date(2026, 9, 8), activities, absence),
            WeekDayProblem(date(2026, 9, 7), activities, absence),
        ),
    )

    assert [item.day for item in result.days] == [date(2026, 9, 7), date(2026, 9, 8)]
