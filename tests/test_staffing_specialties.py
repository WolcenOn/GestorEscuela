from gestor_escuela.solver.staffing import (
    StaffingOptimizer,
    StaffingRequirement,
    StaffingTeacher,
)


def test_prefers_specialist_for_specialist_subject_and_keeps_generalist_for_tutoring() -> None:
    teachers = (
        StaffingTeacher(
            id="english",
            name="Especialista Inglés",
            role="especialista",
            available_minutes=360,
            allowed_subjects=frozenset({"Inglés", "Matemáticas"}),
            specialty_subjects=frozenset({"Inglés"}),
            tutor_preference="evitar",
        ),
        StaffingTeacher(
            id="generalist",
            name="Generalista",
            role="generalista",
            available_minutes=360,
            allowed_subjects=frozenset({"Inglés", "Matemáticas"}),
            tutor_preference="preferente",
            minimum_tutor_minutes=180,
        ),
    )
    requirements = (
        StaffingRequirement("g1-en", "1A", "Inglés", 180),
        StaffingRequirement("g1-ma", "1A", "Matemáticas", 180),
        StaffingRequirement("g2-en", "2A", "Inglés", 180),
        StaffingRequirement("g2-ma", "2A", "Matemáticas", 180),
    )

    solution = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=requirements,
        group_ids=("1A", "2A"),
    )

    by_requirement = {item.requirement_id: item.teacher_id for item in solution.assignments}
    assert by_requirement["g1-en"] == "english"
    assert by_requirement["g2-en"] == "english"
    assert by_requirement["g1-ma"] == "generalist"
    assert by_requirement["g2-ma"] == "generalist"
    assert solution.complete


def test_specialty_subjects_must_also_be_allowed() -> None:
    teachers = (
        StaffingTeacher(
            id="music",
            name="Música",
            role="especialista",
            available_minutes=180,
            allowed_subjects=frozenset({"Matemáticas"}),
            specialty_subjects=frozenset({"Música"}),
        ),
    )

    try:
        StaffingOptimizer().solve(
            teachers=teachers,
            requirements=(StaffingRequirement("m", "1A", "Matemáticas", 60),),
            group_ids=("1A",),
        )
    except ValueError as exc:
        assert "Specialty subjects" in str(exc)
    else:
        raise AssertionError("Expected specialty validation to fail")
