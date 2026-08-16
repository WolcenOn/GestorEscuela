from __future__ import annotations

from statistics import mean
from time import perf_counter

from gestor_escuela.domain.models import Absence
from gestor_escuela.simulation.dataset import build_pilot_dataset
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


def main(iterations: int = 20) -> None:
    teachers, _, _, activities = build_pilot_dataset()
    scenarios = {
        "1 ausencia": (Absence("P02", frozenset({"S1", "S2", "S3"})),),
        "2 ausencias": (
            Absence("P02", frozenset({"S1", "S2", "S3"})),
            Absence("P04", frozenset({"S1", "S2", "S3"})),
        ),
        "3 ausencias": (
            Absence("P01", frozenset({"S1", "S2", "S3"})),
            Absence("P03", frozenset({"S1", "S2", "S3"})),
            Absence("P05", frozenset({"S1", "S2", "S3"})),
        ),
        "4 ausencias": tuple(
            Absence(teacher_id, frozenset({"S3"}))
            for teacher_id in ("P01", "P02", "P03", "P04")
        ),
    }
    optimizer = SchoolDayOptimizer()
    for name, absences in scenarios.items():
        timings: list[float] = []
        coverage: list[float] = []
        for _ in range(iterations):
            start = perf_counter()
            solution = optimizer.solve(
                teachers=teachers,
                activities=activities,
                absences=absences,
            )
            timings.append(perf_counter() - start)
            coverage.append(solution.coverage_ratio)
        print(
            f"{name}: media={mean(timings):.4f}s "
            f"máx={max(timings):.4f}s cobertura={mean(coverage):.1%}"
        )


if __name__ == "__main__":
    main()
