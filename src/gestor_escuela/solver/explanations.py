from __future__ import annotations

from gestor_escuela.domain.models import Activity, SolverSolution, Teacher


def explain_solution(
    solution: SolverSolution,
    *,
    teachers: tuple[Teacher, ...],
    activities: tuple[Activity, ...],
) -> tuple[str, ...]:
    teachers_by_id = {teacher.id: teacher for teacher in teachers}
    activities_by_id = {activity.id: activity for activity in activities}
    lines: list[str] = []

    for substitution in solution.substitutions:
        teacher = teachers_by_id[substitution.substitute_teacher_id]
        reasons = [
            "está disponible y es compatible con el grupo",
            f"lleva {teacher.substitution_count} sustituciones previas",
        ]
        if substitution.displaced_activity_id:
            displaced = activities_by_id[substitution.displaced_activity_id]
            reasons.append(
                f"su actividad {displaced.activity_type.value} es desplazable "
                f"(prioridad {displaced.priority.name})"
            )
        else:
            reasons.append("no necesita abandonar otra actividad")
        lines.append(
            f"{substitution.substitute_teacher_id} sustituye a "
            f"{substitution.absent_teacher_id} en {substitution.group_id} "
            f"({substitution.slot_id}) porque " + "; ".join(reasons) + "."
        )

    for item in solution.uncovered:
        lines.append(f"{item.group_id} queda sin cobertura en {item.slot_id}: {item.reason}")
    return tuple(lines)
