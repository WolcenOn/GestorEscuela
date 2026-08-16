from __future__ import annotations

import pytest

from gestor_escuela.domain.models import Absence, LockedSubstitution, SolverWeights, Teacher
from gestor_escuela.simulation.dataset import build_pilot_dataset
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


def dataset():
    teachers, _, _, activities = build_pilot_dataset()
    return teachers, activities


def test_single_absence_is_fully_covered() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    assert len(solution.substitutions) == 1
    assert not solution.uncovered


def test_two_absences_are_solved_globally() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P02", frozenset({"S1"})),
            Absence("P04", frozenset({"S1"})),
        ),
    )
    assert len(solution.substitutions) == 2
    assert len({s.substitute_teacher_id for s in solution.substitutions}) == 2


def test_three_simultaneous_absences_are_supported() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P01", frozenset({"S3"})),
            Absence("P03", frozenset({"S3"})),
            Absence("P05", frozenset({"S3"})),
        ),
    )
    assert len(solution.substitutions) == 3
    assert not solution.uncovered


def test_four_simultaneous_absences_use_distinct_teachers() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=tuple(
            Absence(teacher_id, frozenset({"S3"}))
            for teacher_id in ("P01", "P02", "P03", "P04")
        ),
    )
    assert len(solution.substitutions) == 4
    assert not solution.uncovered
    assert len({s.substitute_teacher_id for s in solution.substitutions}) == 4


def test_absent_teacher_is_never_selected_as_substitute() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P02", frozenset({"S1"})),
            Absence("P10", frozenset({"S1"})),
        ),
    )
    assert all(s.substitute_teacher_id != "P10" for s in solution.substitutions)


def test_tutor_plus_pt_absence_never_uses_absent_pt() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P02", frozenset({"S1"})),
            Absence("P07", frozenset({"S1"})),
        ),
    )
    assert len(solution.substitutions) == 1
    assert solution.substitutions[0].substitute_teacher_id != "P07"


def test_protected_pt_is_not_displaced_when_flexible_support_exists() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    assert solution.substitutions[0].substitute_teacher_id != "P07"


def test_pt_or_al_can_be_used_when_other_resources_are_absent() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P02", frozenset({"S3"})),
            Absence("P09", frozenset({"S3"})),
            Absence("P10", frozenset({"S3"})),
            Absence("P11", frozenset({"S3"})),
            Absence("P12", frozenset({"S3"})),
        ),
    )
    assert len(solution.substitutions) == 1
    assert solution.substitutions[0].substitute_teacher_id in {"P07", "P08"}


def test_fairness_history_changes_selection() -> None:
    teachers, activities = dataset()
    adjusted = tuple(
        Teacher(
            id=t.id,
            profile=t.profile,
            substitution_count=50 if t.id == "P10" else t.substitution_count,
            can_cover_groups=t.can_cover_groups,
            emergency_only=t.emergency_only,
        )
        for t in teachers
    )
    solution = SchoolDayOptimizer().solve(
        teachers=adjusted,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    assert solution.substitutions[0].substitute_teacher_id != "P10"


def test_locked_manual_decision_is_respected_on_recalculation() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
        locked_substitutions=(LockedSubstitution("A-S1-G2", "P11"),),
    )
    assert solution.substitutions[0].substitute_teacher_id == "P11"


def test_invalid_locked_manual_decision_is_rejected_in_domain_language() -> None:
    teachers, activities = dataset()
    with pytest.raises(ValueError, match="no está disponible o no es compatible"):
        SchoolDayOptimizer().solve(
            teachers=teachers,
            activities=activities,
            absences=(Absence("P02", frozenset({"S1"})),),
            locked_substitutions=(LockedSubstitution("A-S1-G2", "P07"),),
        )


def test_partial_solution_is_returned_instead_of_failure() -> None:
    teachers, activities = dataset()
    tutors_only = tuple(t for t in teachers if t.id <= "P06")
    solution = SchoolDayOptimizer().solve(
        teachers=tutors_only,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    assert not solution.substitutions
    assert len(solution.uncovered) == 1
    assert solution.total_penalty >= SolverWeights().uncovered
