from __future__ import annotations

from collections import defaultdict

from gestor_escuela.domain.models import (
    Activity,
    CandidateStatus,
    SolverSolution,
    Teacher,
)


def explain_solution(
    solution: SolverSolution,
    *,
    teachers: tuple[Teacher, ...],
    activities: tuple[Activity, ...],
) -> tuple[str, ...]:
    teachers_by_id = {teacher.id: teacher for teacher in teachers}
    activities_by_id = {activity.id: activity for activity in activities}
    assessments_by_activity = defaultdict(list)
    for assessment in solution.candidate_assessments:
        assessments_by_activity[assessment.activity_id].append(assessment)

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

        valid_alternatives = sorted(
            (
                assessment
                for assessment in assessments_by_activity[substitution.activity_id]
                if assessment.status is CandidateStatus.VALID_ALTERNATIVE
                and assessment.penalty is not None
            ),
            key=lambda item: (item.penalty or 0, item.teacher_id),
        )
        comparison = ""
        if valid_alternatives:
            best = valid_alternatives[0]
            comparison = (
                f" La mejor alternativa no elegida era {best.teacher_id} "
                f"con coste {best.penalty}, frente a {substitution.penalty} del elegido."
            )

        lines.append(
            f"{substitution.substitute_teacher_id} sustituye a "
            f"{substitution.absent_teacher_id} en {substitution.group_id} "
            f"({substitution.slot_id}) porque " + "; ".join(reasons) + "." + comparison
        )

        for assessment in assessments_by_activity[substitution.activity_id]:
            if assessment.status is not CandidateStatus.REJECTED:
                continue
            lines.append(
                f"- {assessment.teacher_id} descartado: "
                f"{assessment.detail or assessment.rejection_reason or 'restricción no satisfecha'}."
            )

    for item in solution.uncovered:
        lines.append(f"{item.group_id} queda sin cobertura en {item.slot_id}: {item.reason}")
    return tuple(lines)
