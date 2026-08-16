from __future__ import annotations

from gestor_escuela.solver.explanations import explain_solution
from gestor_escuela.solver.optimizer import SchoolDayOptimizer
from gestor_escuela.simulation.dataset import build_pilot_dataset, demo_absences


def main() -> None:
    teachers, _, slots, activities = build_pilot_dataset()
    absences = demo_absences()
    optimizer = SchoolDayOptimizer()
    solution = optimizer.solve(teachers=teachers, activities=activities, absences=absences)

    print("SIMULACIÓN\n")
    print("Ausencias:")
    slot_order = {slot.id: slot.order for slot in slots}
    slot_label = {slot.id: slot.label for slot in slots}
    for absence in absences:
        ordered = sorted(absence.slot_ids, key=slot_order.__getitem__)
        print(f"- {absence.teacher_id}: {slot_label[ordered[0]]}–{slot_label[ordered[-1]]}")

    affected = len(solution.substitutions) + len(solution.uncovered)
    print(f"\nActividades obligatorias afectadas: {affected}")
    print("\nSOLUCIÓN RECOMENDADA")
    print(f"{solution.score}/100\n")

    for substitution in sorted(solution.substitutions, key=lambda s: slot_order[s.slot_id]):
        displaced = (
            f" · desplaza {substitution.displaced_activity_id}"
            if substitution.displaced_activity_id
            else ""
        )
        print(
            f"{slot_label[substitution.slot_id]}  {substitution.group_id} → "
            f"{substitution.substitute_teacher_id}{displaced}"
        )

    print("\nImpacto:")
    if not solution.uncovered:
        print("✓ Todos los grupos obligatorios atendidos")
    else:
        print(f"⚠ {len(solution.uncovered)} actividades obligatorias sin cubrir")
    pt_al_displaced = sum(
        1
        for s in solution.substitutions
        if s.displaced_activity_id and ("P07" in s.displaced_activity_id or "P08" in s.displaced_activity_id)
    )
    print(f"{'✓' if pt_al_displaced == 0 else '⚠'} PT/AL desplazados: {pt_al_displaced}")
    print(f"Penalización total: {solution.total_penalty}")

    print("\nExplicación:")
    for line in explain_solution(solution, teachers=teachers, activities=activities):
        print(f"- {line}")

    print(f"\nTiempo solver: {solution.wall_time_seconds:.4f} s")


if __name__ == "__main__":
    main()
