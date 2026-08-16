from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    LockedSubstitution,
    Priority,
    SolverSolution,
    SolverWeights,
    Substitution,
    Teacher,
    UncoveredActivity,
)


@dataclass(frozen=True, slots=True)
class _Need:
    activity: Activity
    absent_teacher_id: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    teacher: Teacher
    displaced_activity: Activity | None
    penalty: int


class SchoolDayOptimizer:
    """Global CP-SAT optimizer for the substitution needs of one school day."""

    def __init__(self, weights: SolverWeights | None = None, max_time_seconds: float = 5.0):
        self.weights = weights or SolverWeights()
        self.max_time_seconds = max_time_seconds

    def solve(
        self,
        *,
        teachers: tuple[Teacher, ...],
        activities: tuple[Activity, ...],
        absences: tuple[Absence, ...],
        locked_substitutions: tuple[LockedSubstitution, ...] = (),
    ) -> SolverSolution:
        activities_by_teacher_slot = {(a.teacher_id, a.slot_id): a for a in activities}
        absent_slots = {
            (absence.teacher_id, slot_id)
            for absence in absences
            for slot_id in absence.slot_ids
        }

        needs = tuple(
            _Need(activity=a, absent_teacher_id=a.teacher_id)
            for a in activities
            if a.requires_group_coverage and (a.teacher_id, a.slot_id) in absent_slots
        )

        model = cp_model.CpModel()
        assignment_vars: dict[tuple[int, str], cp_model.IntVar] = {}
        uncovered_vars: dict[int, cp_model.IntVar] = {}
        candidates_by_need: dict[int, tuple[_Candidate, ...]] = {}

        for need_index, need in enumerate(needs):
            candidates = self._candidates_for_need(
                need=need,
                teachers=teachers,
                activities_by_teacher_slot=activities_by_teacher_slot,
                absent_slots=absent_slots,
            )
            candidates_by_need[need_index] = candidates
            for candidate in candidates:
                assignment_vars[(need_index, candidate.teacher.id)] = model.new_bool_var(
                    f"assign_n{need_index}_{candidate.teacher.id}"
                )
            uncovered_vars[need_index] = model.new_bool_var(f"uncovered_n{need_index}")
            model.add(
                sum(assignment_vars[(need_index, c.teacher.id)] for c in candidates)
                + uncovered_vars[need_index]
                == 1
            )

        self._apply_locked_substitutions(
            model=model,
            needs=needs,
            candidates_by_need=candidates_by_need,
            assignment_vars=assignment_vars,
            locked_substitutions=locked_substitutions,
        )

        by_teacher_slot: dict[tuple[str, str], list[cp_model.IntVar]] = defaultdict(list)
        for need_index, need in enumerate(needs):
            for candidate in candidates_by_need[need_index]:
                by_teacher_slot[(candidate.teacher.id, need.activity.slot_id)].append(
                    assignment_vars[(need_index, candidate.teacher.id)]
                )
        for variables in by_teacher_slot.values():
            model.add(sum(variables) <= 1)

        objective_terms: list[cp_model.LinearExpr] = []
        for need_index, candidates in candidates_by_need.items():
            objective_terms.append(uncovered_vars[need_index] * self.weights.uncovered)
            for candidate in candidates:
                objective_terms.append(
                    assignment_vars[(need_index, candidate.teacher.id)] * candidate.penalty
                )
        model.minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_seconds
        solver.parameters.num_search_workers = 1
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"Unexpected CP-SAT status: {solver.status_name(status)}")

        substitutions: list[Substitution] = []
        uncovered: list[UncoveredActivity] = []
        for need_index, need in enumerate(needs):
            selected = None
            for candidate in candidates_by_need[need_index]:
                if solver.value(assignment_vars[(need_index, candidate.teacher.id)]):
                    selected = candidate
                    break
            if selected is None:
                uncovered.append(
                    UncoveredActivity(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=need.activity.group_id or "",
                        absent_teacher_id=need.absent_teacher_id,
                        reason=(
                            "No existe ningún docente compatible disponible sin violar "
                            "restricciones duras."
                        ),
                    )
                )
                continue
            substitutions.append(
                Substitution(
                    activity_id=need.activity.id,
                    slot_id=need.activity.slot_id,
                    group_id=need.activity.group_id or "",
                    absent_teacher_id=need.absent_teacher_id,
                    substitute_teacher_id=selected.teacher.id,
                    displaced_activity_id=(
                        selected.displaced_activity.id if selected.displaced_activity else None
                    ),
                    penalty=selected.penalty,
                )
            )

        return SolverSolution(
            substitutions=tuple(substitutions),
            uncovered=tuple(uncovered),
            total_penalty=round(solver.objective_value),
            objective_bound=solver.best_objective_bound,
            wall_time_seconds=solver.wall_time,
        )

    @staticmethod
    def _apply_locked_substitutions(
        *,
        model: cp_model.CpModel,
        needs: tuple[_Need, ...],
        candidates_by_need: dict[int, tuple[_Candidate, ...]],
        assignment_vars: dict[tuple[int, str], cp_model.IntVar],
        locked_substitutions: tuple[LockedSubstitution, ...],
    ) -> None:
        need_index_by_activity = {need.activity.id: index for index, need in enumerate(needs)}
        locked_activities: set[str] = set()
        locked_teacher_slots: set[tuple[str, str]] = set()

        for locked in locked_substitutions:
            if locked.activity_id in locked_activities:
                raise ValueError(
                    f"La actividad {locked.activity_id} tiene más de una decisión bloqueada."
                )
            locked_activities.add(locked.activity_id)

            need_index = need_index_by_activity.get(locked.activity_id)
            if need_index is None:
                raise ValueError(
                    f"La actividad {locked.activity_id} no necesita sustitución en este cálculo."
                )

            need = needs[need_index]
            candidate_ids = {
                candidate.teacher.id for candidate in candidates_by_need[need_index]
            }
            if locked.substitute_teacher_id not in candidate_ids:
                raise ValueError(
                    f"La decisión bloqueada para {locked.activity_id} no es posible porque "
                    f"{locked.substitute_teacher_id} no está disponible o no es compatible."
                )

            teacher_slot = (locked.substitute_teacher_id, need.activity.slot_id)
            if teacher_slot in locked_teacher_slots:
                raise ValueError(
                    f"{locked.substitute_teacher_id} tiene dos decisiones bloqueadas en "
                    f"{need.activity.slot_id}."
                )
            locked_teacher_slots.add(teacher_slot)
            model.add(assignment_vars[(need_index, locked.substitute_teacher_id)] == 1)

    def _candidates_for_need(
        self,
        *,
        need: _Need,
        teachers: tuple[Teacher, ...],
        activities_by_teacher_slot: dict[tuple[str, str], Activity],
        absent_slots: set[tuple[str, str]],
    ) -> tuple[_Candidate, ...]:
        candidates: list[_Candidate] = []
        group_id = need.activity.group_id
        if group_id is None:
            return ()

        for teacher in teachers:
            if teacher.id == need.absent_teacher_id:
                continue
            if (teacher.id, need.activity.slot_id) in absent_slots:
                continue
            if teacher.can_cover_groups and group_id not in teacher.can_cover_groups:
                continue

            current = activities_by_teacher_slot.get((teacher.id, need.activity.slot_id))
            if current and not self._can_displace(current):
                continue

            penalty = teacher.substitution_count * self.weights.substitution_history
            if teacher.emergency_only:
                penalty += self.weights.emergency_teacher
            if current:
                penalty += self._displacement_penalty(current)
            candidates.append(_Candidate(teacher, current, penalty))

        return tuple(candidates)

    @staticmethod
    def _can_displace(activity: Activity) -> bool:
        if activity.activity_type == ActivityType.CLASS:
            return False
        if activity.priority >= Priority.HIGH:
            return False
        return activity.cancelable or activity.movable

    def _displacement_penalty(self, activity: Activity) -> int:
        by_priority = {
            Priority.CANCELABLE: 30,
            Priority.FLEXIBLE: self.weights.displacement_flexible,
            Priority.NORMAL: self.weights.displacement_normal,
            Priority.HIGH: self.weights.displacement_high,
            Priority.CRITICAL: self.weights.uncovered,
        }
        penalty = by_priority[activity.priority]
        if activity.activity_type in (ActivityType.PT, ActivityType.AL):
            penalty *= self.weights.pt_al_displacement_multiplier
        return penalty
