from __future__ import annotations

from gestor_escuela.domain.models import (
    Absence,
    CandidateRejectionReason,
    CandidateStatus,
    Teacher,
)
from gestor_escuela.simulation.dataset import build_pilot_dataset
from gestor_escuela.solver.explanations import explain_solution
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


def dataset():
    teachers, _, _, activities = build_pilot_dataset()
    return teachers, activities


def test_solver_records_structured_candidate_assessments() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )

    assessments = [
        item for item in solution.candidate_assessments if item.activity_id == "A-S1-G2"
    ]
    assert len(assessments) == len(teachers)
    assert sum(item.status is CandidateStatus.SELECTED for item in assessments) == 1
    assert any(item.status is CandidateStatus.VALID_ALTERNATIVE for item in assessments)

    absent_teacher = next(item for item in assessments if item.teacher_id == "P02")
    assert absent_teacher.status is CandidateStatus.REJECTED
    assert absent_teacher.rejection_reason is CandidateRejectionReason.ABSENT_TEACHER

    rejected = [item for item in assessments if item.status is CandidateStatus.REJECTED]
    assert rejected
    assert all(item.rejection_reason is not None for item in rejected)
    assert all(item.detail for item in rejected)


def test_simultaneous_needs_record_global_conflicts() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(
            Absence("P02", frozenset({"S1"})),
            Absence("P04", frozenset({"S1"})),
        ),
    )

    assert any(
        item.rejection_reason is CandidateRejectionReason.GLOBAL_CONFLICT
        for item in solution.candidate_assessments
    )


def test_human_explanation_includes_rejected_candidates() -> None:
    teachers, activities = dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )

    lines = explain_solution(solution, teachers=teachers, activities=activities)

    assert any("descartado" in line for line in lines)
    assert any("P02 descartado" in line for line in lines)


def test_recent_fairness_load_changes_selection_and_is_explained() -> None:
    teachers, activities = dataset()
    baseline = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    baseline_teacher = baseline.substitutions[0].substitute_teacher_id

    loaded = tuple(
        Teacher(
            id=teacher.id,
            profile=teacher.profile,
            substitution_count=teacher.substitution_count,
            can_cover_groups=teacher.can_cover_groups,
            emergency_only=teacher.emergency_only,
            substitutions_last_7_days=8 if teacher.id == baseline_teacher else 0,
            substitutions_last_30_days=12 if teacher.id == baseline_teacher else 0,
        )
        for teacher in teachers
    )
    solution = SchoolDayOptimizer().solve(
        teachers=loaded,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )

    assert solution.substitutions[0].substitute_teacher_id != baseline_teacher
    loaded_assessment = next(
        item
        for item in solution.candidate_assessments
        if item.activity_id == "A-S1-G2" and item.teacher_id == baseline_teacher
    )
    assert loaded_assessment.penalty_breakdown is not None
    assert loaded_assessment.penalty_breakdown.recent_7_days > 0
    assert loaded_assessment.penalty_breakdown.recent_30_days > 0
    assert loaded_assessment.penalty == loaded_assessment.penalty_breakdown.total
