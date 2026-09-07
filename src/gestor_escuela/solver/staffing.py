from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model


@dataclass(frozen=True, slots=True)
class StaffingTeacher:
    id: str
    name: str
    role: str
    available_minutes: int
    allowed_subjects: frozenset[str]
    specialty_subjects: frozenset[str] = frozenset()
    tutor_preference: str = "disponible"
    fixed_tutor_group: str | None = None
    minimum_tutor_minutes: int = 0


@dataclass(frozen=True, slots=True)
class StaffingRequirement:
    id: str
    group_id: str
    subject: str
    minutes: int
    fixed_teacher_id: str | None = None


@dataclass(frozen=True, slots=True)
class StaffingAssignment:
    requirement_id: str
    group_id: str
    subject: str
    minutes: int
    teacher_id: str


@dataclass(frozen=True, slots=True)
class TutorAssignment:
    group_id: str
    teacher_id: str


@dataclass(frozen=True, slots=True)
class StaffingTeacherLoad:
    teacher_id: str
    assigned_minutes: int
    available_minutes: int
    remaining_minutes: int
    groups_taught: int
    tutor_group: str | None


@dataclass(frozen=True, slots=True)
class StaffingSolution:
    assignments: tuple[StaffingAssignment, ...]
    tutors: tuple[TutorAssignment, ...]
    uncovered_requirement_ids: tuple[str, ...]
    uncovered_tutor_groups: tuple[str, ...]
    teacher_loads: tuple[StaffingTeacherLoad, ...]
    objective_value: float
    wall_time_seconds: float

    @property
    def complete(self) -> bool:
        return not self.uncovered_requirement_ids and not self.uncovered_tutor_groups


class StaffingOptimizer:
    """Assign weekly teaching needs and tutor groups before timetable placement.

    The solver first protects coverage and hard capacity. Among complete solutions it favors
    specialist teachers for their specialist subjects, tutors teaching their own group and
    compact allocations with fewer teacher/group relationships. This keeps the future
    timetable stable and avoids unnecessary movement between classes.
    """

    def __init__(self, max_time_seconds: float = 8.0):
        self.max_time_seconds = max_time_seconds

    def solve(
        self,
        *,
        teachers: tuple[StaffingTeacher, ...],
        requirements: tuple[StaffingRequirement, ...],
        group_ids: tuple[str, ...],
    ) -> StaffingSolution:
        self._validate(teachers, requirements, group_ids)
        model = cp_model.CpModel()
        teacher_by_id = {teacher.id: teacher for teacher in teachers}
        specialist_ids_by_subject = {
            requirement.subject: frozenset(
                teacher.id
                for teacher in teachers
                if requirement.subject in teacher.specialty_subjects
            )
            for requirement in requirements
        }

        assignment_vars: dict[tuple[str, str], cp_model.IntVar] = {}
        uncovered_vars: dict[str, cp_model.IntVar] = {}
        eligible_by_requirement: dict[str, tuple[StaffingTeacher, ...]] = {}

        for requirement in requirements:
            eligible = tuple(
                teacher
                for teacher in teachers
                if self._teacher_can_cover(teacher, requirement)
            )
            eligible_by_requirement[requirement.id] = eligible
            for teacher in eligible:
                assignment_vars[(requirement.id, teacher.id)] = model.new_bool_var(
                    f"assign_{self._safe(requirement.id)}_{self._safe(teacher.id)}"
                )
            uncovered_var = model.new_bool_var(f"uncovered_{self._safe(requirement.id)}")
            uncovered_vars[requirement.id] = uncovered_var
            model.add(
                sum(assignment_vars[(requirement.id, teacher.id)] for teacher in eligible)
                + uncovered_var
                == 1
            )
            if requirement.fixed_teacher_id is not None:
                fixed_var = assignment_vars.get((requirement.id, requirement.fixed_teacher_id))
                if fixed_var is None:
                    model.add(uncovered_var == 1)
                else:
                    model.add(fixed_var == 1)

        for teacher in teachers:
            load_terms = [
                requirement.minutes * assignment_vars[(requirement.id, teacher.id)]
                for requirement in requirements
                if (requirement.id, teacher.id) in assignment_vars
            ]
            model.add(sum(load_terms) <= teacher.available_minutes)

        group_use_vars: dict[tuple[str, str], cp_model.IntVar] = {}
        for teacher in teachers:
            for group_id in group_ids:
                relevant = [
                    assignment_vars[(requirement.id, teacher.id)]
                    for requirement in requirements
                    if requirement.group_id == group_id
                    and (requirement.id, teacher.id) in assignment_vars
                ]
                if not relevant:
                    continue
                group_used_var = model.new_bool_var(
                    f"uses_{self._safe(teacher.id)}_{self._safe(group_id)}"
                )
                group_use_vars[(teacher.id, group_id)] = group_used_var
                for assignment_var in relevant:
                    model.add(assignment_var <= group_used_var)
                model.add(group_used_var <= sum(relevant))

        tutor_vars: dict[tuple[str, str], cp_model.IntVar] = {}
        uncovered_tutor_vars: dict[str, cp_model.IntVar] = {}
        for group_id in group_ids:
            candidates = tuple(
                teacher
                for teacher in teachers
                if teacher.tutor_preference != "no" or teacher.fixed_tutor_group == group_id
            )
            for teacher in candidates:
                tutor_vars[(group_id, teacher.id)] = model.new_bool_var(
                    f"tutor_{self._safe(group_id)}_{self._safe(teacher.id)}"
                )
            uncovered_tutor_var = model.new_bool_var(
                f"uncovered_tutor_{self._safe(group_id)}"
            )
            uncovered_tutor_vars[group_id] = uncovered_tutor_var
            model.add(
                sum(tutor_vars[(group_id, teacher.id)] for teacher in candidates)
                + uncovered_tutor_var
                == 1
            )

        for teacher in teachers:
            tutor_terms = [
                tutor_vars[(group_id, teacher.id)]
                for group_id in group_ids
                if (group_id, teacher.id) in tutor_vars
            ]
            if tutor_terms:
                model.add(sum(tutor_terms) <= 1)
            if teacher.fixed_tutor_group:
                fixed_tutor_var = tutor_vars.get((teacher.fixed_tutor_group, teacher.id))
                if fixed_tutor_var is not None:
                    model.add(fixed_tutor_var == 1)

        tutor_presence_shortfalls: list[cp_model.IntVar] = []
        tutor_teaches_vars: list[cp_model.IntVar] = []
        for (group_id, teacher_id), tutor_var in tutor_vars.items():
            teacher = teacher_by_id[teacher_id]
            group_requirements = [
                requirement
                for requirement in requirements
                if requirement.group_id == group_id
                and (requirement.id, teacher_id) in assignment_vars
            ]
            taught_minutes = sum(
                requirement.minutes * assignment_vars[(requirement.id, teacher_id)]
                for requirement in group_requirements
            )
            if teacher.minimum_tutor_minutes > 0:
                shortfall = model.new_int_var(
                    0,
                    teacher.minimum_tutor_minutes,
                    f"tutor_shortfall_{self._safe(group_id)}_{self._safe(teacher_id)}",
                )
                model.add(
                    taught_minutes + shortfall
                    >= teacher.minimum_tutor_minutes * tutor_var
                )
                model.add(shortfall <= teacher.minimum_tutor_minutes * tutor_var)
                tutor_presence_shortfalls.append(shortfall)

            group_used = group_use_vars.get((teacher_id, group_id))
            if group_used is not None:
                tutor_teaches_var = model.new_bool_var(
                    f"tutor_teaches_{self._safe(group_id)}_{self._safe(teacher_id)}"
                )
                model.add(tutor_teaches_var <= tutor_var)
                model.add(tutor_teaches_var <= group_used)
                model.add(tutor_teaches_var >= tutor_var + group_used - 1)
                tutor_teaches_vars.append(tutor_teaches_var)

        objective_terms: list[cp_model.LinearExpr] = []
        for requirement in requirements:
            objective_terms.append(
                requirement.minutes * 10_000 * uncovered_vars[requirement.id]
            )
            specialist_ids = specialist_ids_by_subject.get(requirement.subject, frozenset())
            if specialist_ids:
                for teacher in eligible_by_requirement[requirement.id]:
                    assignment_var = assignment_vars[(requirement.id, teacher.id)]
                    if teacher.id in specialist_ids:
                        # Small reward for keeping specialist hours with the specialist.
                        objective_terms.append(-8 * requirement.minutes * assignment_var)
                    else:
                        # A non-specialist may still cover the subject when necessary, but
                        # doing so should be noticeably more expensive than ordinary movement.
                        objective_terms.append(35 * requirement.minutes * assignment_var)

        for uncovered_tutor_var in uncovered_tutor_vars.values():
            objective_terms.append(500_000 * uncovered_tutor_var)

        for (_group_id, teacher_id), tutor_var in tutor_vars.items():
            teacher = teacher_by_id[teacher_id]
            if teacher.role == "especialista":
                objective_terms.append(18_000 * tutor_var)
            elif teacher.role == "mixto":
                objective_terms.append(3_000 * tutor_var)
            preference_penalty = {
                "preferente": 0,
                "disponible": 600,
                "evitar": 12_000,
                "no": 100_000,
            }.get(teacher.tutor_preference, 1_000)
            objective_terms.append(preference_penalty * tutor_var)

        # Every teacher/group relationship is a potential movement. A stronger weight here
        # favors compact allocations while still allowing cross-group swaps when capacity or
        # tutor continuity requires them.
        for group_used_var in group_use_vars.values():
            objective_terms.append(450 * group_used_var)
        for shortfall in tutor_presence_shortfalls:
            objective_terms.append(40 * shortfall)
        for tutor_teaches_var in tutor_teaches_vars:
            objective_terms.append(-2_500 * tutor_teaches_var)

        model.minimize(sum(objective_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_seconds
        solver.parameters.num_search_workers = 8
        status = solver.solve(model)
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            raise ValueError("No staffing solution could be produced")

        assignments: list[StaffingAssignment] = []
        uncovered_requirement_ids: list[str] = []
        for requirement in requirements:
            if solver.value(uncovered_vars[requirement.id]):
                uncovered_requirement_ids.append(requirement.id)
                continue
            for teacher in eligible_by_requirement[requirement.id]:
                assignment_var = assignment_vars[(requirement.id, teacher.id)]
                if solver.value(assignment_var):
                    assignments.append(
                        StaffingAssignment(
                            requirement_id=requirement.id,
                            group_id=requirement.group_id,
                            subject=requirement.subject,
                            minutes=requirement.minutes,
                            teacher_id=teacher.id,
                        )
                    )
                    break

        tutors: list[TutorAssignment] = []
        uncovered_tutors: list[str] = []
        for group_id in group_ids:
            if solver.value(uncovered_tutor_vars[group_id]):
                uncovered_tutors.append(group_id)
                continue
            for teacher in teachers:
                tutor_choice = tutor_vars.get((group_id, teacher.id))
                if tutor_choice is not None and solver.value(tutor_choice):
                    tutors.append(TutorAssignment(group_id=group_id, teacher_id=teacher.id))
                    break

        assigned_by_teacher = {teacher.id: 0 for teacher in teachers}
        groups_by_teacher = {teacher.id: set[str]() for teacher in teachers}
        tutor_by_teacher: dict[str, str] = {}
        for assignment in assignments:
            assigned_by_teacher[assignment.teacher_id] += assignment.minutes
            groups_by_teacher[assignment.teacher_id].add(assignment.group_id)
        for tutor in tutors:
            tutor_by_teacher[tutor.teacher_id] = tutor.group_id

        loads = tuple(
            StaffingTeacherLoad(
                teacher_id=teacher.id,
                assigned_minutes=assigned_by_teacher[teacher.id],
                available_minutes=teacher.available_minutes,
                remaining_minutes=max(
                    0, teacher.available_minutes - assigned_by_teacher[teacher.id]
                ),
                groups_taught=len(groups_by_teacher[teacher.id]),
                tutor_group=tutor_by_teacher.get(teacher.id),
            )
            for teacher in teachers
        )
        return StaffingSolution(
            assignments=tuple(assignments),
            tutors=tuple(tutors),
            uncovered_requirement_ids=tuple(uncovered_requirement_ids),
            uncovered_tutor_groups=tuple(uncovered_tutors),
            teacher_loads=loads,
            objective_value=solver.objective_value,
            wall_time_seconds=solver.wall_time,
        )

    @staticmethod
    def _teacher_can_cover(
        teacher: StaffingTeacher, requirement: StaffingRequirement
    ) -> bool:
        if requirement.fixed_teacher_id == teacher.id:
            return True
        return requirement.subject in teacher.allowed_subjects

    @staticmethod
    def _validate(
        teachers: tuple[StaffingTeacher, ...],
        requirements: tuple[StaffingRequirement, ...],
        group_ids: tuple[str, ...],
    ) -> None:
        if len({teacher.id for teacher in teachers}) != len(teachers):
            raise ValueError("Teacher ids must be unique")
        if len({requirement.id for requirement in requirements}) != len(requirements):
            raise ValueError("Requirement ids must be unique")
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("Group ids must be unique")
        known_groups = set(group_ids)
        known_teachers = {teacher.id for teacher in teachers}
        for teacher in teachers:
            if teacher.available_minutes < 0:
                raise ValueError("Teacher available minutes cannot be negative")
            if not teacher.specialty_subjects.issubset(teacher.allowed_subjects):
                raise ValueError(
                    f"Specialty subjects must also be allowed subjects for teacher {teacher.id}"
                )
            if teacher.fixed_tutor_group and teacher.fixed_tutor_group not in known_groups:
                raise ValueError(f"Unknown fixed tutor group: {teacher.fixed_tutor_group}")
        for requirement in requirements:
            if requirement.minutes <= 0:
                raise ValueError("Requirement minutes must be positive")
            if requirement.group_id not in known_groups:
                raise ValueError(f"Unknown requirement group: {requirement.group_id}")
            if (
                requirement.fixed_teacher_id is not None
                and requirement.fixed_teacher_id not in known_teachers
            ):
                raise ValueError(
                    f"Unknown fixed teacher: {requirement.fixed_teacher_id}"
                )

    @staticmethod
    def _safe(value: str) -> str:
        return "".join(character if character.isalnum() else "_" for character in value)
