from __future__ import annotations

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    CandidateStatus,
    Priority,
    Teacher,
    TeacherProfile,
)
from gestor_escuela.solver.flexible_specialty import FlexibleSpecialtySchoolDayOptimizer


def teacher(
    teacher_id: str,
    *,
    specialties: frozenset[str] = frozenset(),
    substitution_count: int = 0,
) -> Teacher:
    return Teacher(
        id=teacher_id,
        profile=TeacherProfile.SPECIALIST if specialties else TeacherProfile.TUTOR,
        substitution_count=substitution_count,
        can_cover_groups=frozenset({"G1"}),
        specialties=specialties,
    )


def english_class() -> Activity:
    return Activity(
        id="ENG-G1-S1",
        slot_id="S1",
        activity_type=ActivityType.CLASS,
        teacher_id="P01",
        group_id="G1",
        priority=Priority.NORMAL,
        required_specialty="ENGLISH",
    )


def test_qualified_specialist_beats_non_specialist_fallback() -> None:
    solution = FlexibleSpecialtySchoolDayOptimizer().solve(
        teachers=(
            teacher("P01", specialties=frozenset({"ENGLISH"})),
            teacher("P02", specialties=frozenset({"ENGLISH"}), substitution_count=5),
            teacher("P03"),
        ),
        activities=(english_class(),),
        absences=(Absence("P01", frozenset({"S1"})),),
    )

    assert len(solution.substitutions) == 1
    assert solution.substitutions[0].substitute_teacher_id == "P02"

    fallback = next(
        item for item in solution.candidate_assessments if item.teacher_id == "P03"
    )
    assert fallback.status is CandidateStatus.WARNING_ALTERNATIVE
    assert fallback.penalty is not None
    assert fallback.penalty >= 12_000
    assert fallback.warning is not None
    assert "sin especialidad" in fallback.warning.lower()


def test_non_specialist_fallback_covers_when_only_specialist_is_absent() -> None:
    solution = FlexibleSpecialtySchoolDayOptimizer().solve(
        teachers=(
            teacher("P01", specialties=frozenset({"ENGLISH"})),
            teacher("P03"),
        ),
        activities=(english_class(),),
        absences=(Absence("P01", frozenset({"S1"})),),
    )

    assert solution.coverage_ratio == 1.0
    assert solution.substitutions[0].substitute_teacher_id == "P03"

    selected = next(
        item for item in solution.candidate_assessments if item.teacher_id == "P03"
    )
    assert selected.status is CandidateStatus.SELECTED
    assert selected.penalty is not None
    assert selected.penalty >= 12_000
    assert selected.warning is not None
