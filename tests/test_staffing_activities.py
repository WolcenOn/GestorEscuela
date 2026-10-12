from gestor_escuela.solver.staffing import (
    StaffingActivity,
    StaffingOptimizer,
    StaffingRequirement,
    StaffingTeacher,
)


def teacher(
    teacher_id: str,
    *,
    minutes: int = 600,
    role: str = "generalista",
    subjects: frozenset[str] = frozenset({"Lengua"}),
) -> StaffingTeacher:
    return StaffingTeacher(
        id=teacher_id,
        name=teacher_id,
        role=role,
        available_minutes=minutes,
        allowed_subjects=subjects,
        tutor_preference="disponible",
    )


def test_assigns_flexible_activity_to_available_candidate() -> None:
    teachers = (
        teacher("generalista"),
        teacher("especialista", role="especialista"),
    )
    activity = StaffingActivity(
        id="biblioteca",
        name="Biblioteca",
        minutes=120,
        eligible_teacher_ids=frozenset({"generalista", "especialista"}),
    )

    result = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=(),
        group_ids=("4A",),
        activities=(activity,),
    )

    assert result.complete is True
    assert len(result.activity_assignments) == 1
    assert result.activity_assignments[0].teacher_id == "generalista"
    general_load = next(
        item for item in result.teacher_loads if item.teacher_id == "generalista"
    )
    assert general_load.activity_minutes == 120
    assert general_load.remaining_minutes == 480


def test_activity_respects_capacity_after_curricular_teaching() -> None:
    teachers = (
        teacher("tutor", minutes=300),
        teacher("apoyo", minutes=300),
    )
    requirement = StaffingRequirement(
        id="4A-lengua",
        group_id="4A",
        subject="Lengua",
        minutes=240,
        fixed_teacher_id="tutor",
    )
    activity = StaffingActivity(
        id="lectura",
        name="Plan lector",
        minutes=120,
        eligible_teacher_ids=frozenset({"tutor", "apoyo"}),
        group_ids=frozenset({"4A"}),
    )

    result = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=(requirement,),
        group_ids=("4A",),
        activities=(activity,),
    )

    activity_assignment = result.activity_assignments[0]
    assert activity_assignment.teacher_id == "apoyo"
    tutor_load = next(item for item in result.teacher_loads if item.teacher_id == "tutor")
    assert tutor_load.teaching_minutes == 240
    assert tutor_load.activity_minutes == 0


def test_multi_teacher_coordination_keeps_all_fixed_participants() -> None:
    teachers = (teacher("a"), teacher("b"), teacher("c"))
    activity = StaffingActivity(
        id="coord",
        name="Coordinación de ciclo",
        minutes=60,
        required_staff=2,
        fixed_teacher_ids=frozenset({"a", "b"}),
        eligible_teacher_ids=frozenset({"c"}),
    )

    result = StaffingOptimizer().solve(
        teachers=teachers,
        requirements=(),
        group_ids=("4A",),
        activities=(activity,),
    )

    assigned = {
        item.teacher_id
        for item in result.activity_assignments
        if item.activity_id == "coord"
    }
    assert assigned == {"a", "b"}
    assert result.uncovered_activity_ids == ()
