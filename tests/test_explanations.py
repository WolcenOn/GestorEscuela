from gestor_escuela.domain.models import Absence
from gestor_escuela.simulation.dataset import build_pilot_dataset
from gestor_escuela.solver.explanations import explain_solution
from gestor_escuela.solver.optimizer import SchoolDayOptimizer


def test_explanation_uses_domain_language() -> None:
    teachers, _, _, activities = build_pilot_dataset()
    solution = SchoolDayOptimizer().solve(
        teachers=teachers,
        activities=activities,
        absences=(Absence("P02", frozenset({"S1"})),),
    )
    explanation = " ".join(explain_solution(solution, teachers=teachers, activities=activities))
    assert "sustituye" in explanation
    assert "constraint" not in explanation.lower()
