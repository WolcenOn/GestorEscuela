from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    LockedSubstitution,
    SolverSolution,
    SolverWeights,
    Teacher,
)
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


@dataclass(frozen=True, slots=True)
class WeekDayProblem:
    day: date
    activities: tuple[Activity, ...]
    absences: tuple[Absence, ...]
    locked_substitutions: tuple[LockedSubstitution, ...] = ()


@dataclass(frozen=True, slots=True)
class WeekDaySolution:
    day: date
    solution: SolverSolution


@dataclass(frozen=True, slots=True)
class WeekSolution:
    days: tuple[WeekDaySolution, ...]
    final_teachers: tuple[Teacher, ...]

    @property
    def total_penalty(self) -> int:
        return sum(item.solution.total_penalty for item in self.days)

    @property
    def uncovered_count(self) -> int:
        return sum(len(item.solution.uncovered) for item in self.days)


class SchoolWeekOptimizer:
    """Solve a school week sequentially while carrying fairness load between days."""

    def __init__(self, weights: SolverWeights | None = None, max_time_seconds: float = 5.0):
        self.weights = weights or SolverWeights()
        self.max_time_seconds = max_time_seconds

    def solve(
        self,
        *,
        teachers: tuple[Teacher, ...],
        days: tuple[WeekDayProblem, ...],
    ) -> WeekSolution:
        evolving = {teacher.id: teacher for teacher in teachers}
        solved_days: list[WeekDaySolution] = []

        for problem in sorted(days, key=lambda item: item.day):
            solution = SchoolDayOptimizer(
                weights=self.weights,
                max_time_seconds=self.max_time_seconds,
            ).solve(
                teachers=tuple(evolving.values()),
                activities=problem.activities,
                absences=problem.absences,
                locked_substitutions=problem.locked_substitutions,
            )
            solved_days.append(WeekDaySolution(problem.day, solution))

            substitutions_by_teacher: dict[str, int] = {}
            for substitution in solution.substitutions:
                substitutions_by_teacher[substitution.substitute_teacher_id] = (
                    substitutions_by_teacher.get(substitution.substitute_teacher_id, 0) + 1
                )

            for teacher_id, added in substitutions_by_teacher.items():
                teacher = evolving[teacher_id]
                evolving[teacher_id] = replace(
                    teacher,
                    substitution_count=teacher.substitution_count + added,
                    substitutions_last_7_days=teacher.substitutions_last_7_days + added,
                    substitutions_last_30_days=teacher.substitutions_last_30_days + added,
                )

        ordered_teachers = tuple(evolving[teacher.id] for teacher in teachers)
        return WeekSolution(tuple(solved_days), ordered_teachers)
