from __future__ import annotations

from gestor_escuela.domain.models import (
    Absence,
    CandidateRejectionReason,
    CandidateStatus,
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
