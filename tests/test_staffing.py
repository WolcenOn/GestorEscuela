from __future__ import annotations

from gestor_escuela.solver.staffing import (
    StaffingOptimizer,
    StaffingRequirement,
    StaffingTeacher,
)


def test_staffing_assigns_specialty_and_generalist_without_exceeding_capacity() -> None:
    teachers = (
        StaffingTeacher(
            id="EN",
            name="Especialista Inglés",
            role="especialista",
            available_minutes=300,
            allowed_subjects=frozenset({"Inglés"}),
            tutor_preference="evitar",
        ),
        StaffingTeacher(
            id="T4",
            name="Tutor generalista",
            role="generalista",
            available_minutes=300,
            allowed_subjects=frozenset({"Matemáticas"}),
            tutor_preference="preferente",
        ),
    )
    requirements = (
        StaffingRequirement("G4-EN", "4A", "Inglés", 180),
        StaffingRequirement("G4-MAT", "4A", "Matemáticas", 240),
    )
    solution = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=requirements,
        group_ids=("4A",),
    )
    assert solution.complete
    by_requirement = {item.requirement_id: item.teacher_id for item in solution.assignments}
    assert by_requirement == {"G4-EN": "EN", "G4-MAT": "T4"}
    assert solution.tutors[0].teacher_id == "T4"
    assert all(load.assigned_minutes <= load.available_minutes for load in solution.teacher_loads)


def test_staffing_uses_specialist_as_tutor_when_natural_tutors_are_insufficient() -> None:
    teachers = (
        StaffingTeacher(
            id="GEN",
            name="Generalista",
            role="generalista",
            available_minutes=600,
            allowed_subjects=frozenset(),
            tutor_preference="preferente",
        ),
        StaffingTeacher(
            id="SPEC",
            name="Especialista",
            role="especialista",
            available_minutes=600,
            allowed_subjects=frozenset(),
            tutor_preference="evitar",
        ),
    )
    solution = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=(),
        group_ids=("4A", "5A"),
    )
    assert solution.complete
    assert {item.teacher_id for item in solution.tutors} == {"GEN", "SPEC"}


def test_staffing_respects_fixed_cross_group_teaching_assignment() -> None:
    teachers = (
        StaffingTeacher(
            id="T4",
            name="Tutor 4A",
            role="generalista",
            available_minutes=600,
            allowed_subjects=frozenset({"Matemáticas"}),
            tutor_preference="preferente",
            fixed_tutor_group="4A",
        ),
        StaffingTeacher(
            id="T5",
            name="Tutor 5A",
            role="generalista",
            available_minutes=600,
            allowed_subjects=frozenset({"Matemáticas"}),
            tutor_preference="preferente",
            fixed_tutor_group="5A",
        ),
    )
    requirements = (
        StaffingRequirement(
            id="MATH-4A",
            group_id="4A",
            subject="Matemáticas",
            minutes=240,
            fixed_teacher_id="T5",
        ),
    )
    solution = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=requirements,
        group_ids=("4A", "5A"),
    )
    assert solution.complete
    assert solution.assignments[0].teacher_id == "T5"
    tutor_map = {item.group_id: item.teacher_id for item in solution.tutors}
    assert tutor_map == {"4A": "T4", "5A": "T5"}
