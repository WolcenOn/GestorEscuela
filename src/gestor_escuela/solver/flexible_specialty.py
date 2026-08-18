from __future__ import annotations

from gestor_escuela.domain.models import (
    Activity,
    ActivityType,
    CandidateAssessment,
    CandidatePenaltyBreakdown,
    CandidateRejectionReason,
    CandidateStatus,
    Teacher,
)
from gestor_escuela.solver.optimizer import SchoolDayOptimizer, _Candidate, _Need


class FlexibleSpecialtySchoolDayOptimizer(SchoolDayOptimizer):
    """School-day optimizer with a warned fallback for ordinary specialist classes.

    A missing specialty remains a hard rejection for non-class activities. For a CLASS,
    a teacher who can cover the group may remain in the candidate ranking with a high
    penalty and an explicit warning. A qualified specialist therefore wins whenever a
    reasonably available qualified candidate exists, while a small school can still
    cover the class when its only specialist is absent.
    """

    def _evaluate_candidates_for_need(
        self,
        *,
        need: _Need,
        teachers: tuple[Teacher, ...],
        activities_by_teacher_slot: dict[tuple[str, str], Activity],
        absent_slots: set[tuple[str, str]],
    ) -> tuple[tuple[_Candidate, ...], tuple[CandidateAssessment, ...]]:
        candidates: list[_Candidate] = []
        assessments: list[CandidateAssessment] = []
        group_id = need.activity.group_id
        if group_id is None:
            return (), ()

        for teacher in teachers:
            if teacher.id == need.absent_teacher_id:
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.REJECTED,
                        rejection_reason=CandidateRejectionReason.ABSENT_TEACHER,
                        detail="Es el docente ausente responsable de la actividad.",
                    )
                )
                continue
            if (teacher.id, need.activity.slot_id) in absent_slots:
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.REJECTED,
                        rejection_reason=CandidateRejectionReason.ABSENT_IN_SLOT,
                        detail="El docente también está ausente en esta franja.",
                    )
                )
                continue
            if group_id not in teacher.can_cover_groups:
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.REJECTED,
                        rejection_reason=CandidateRejectionReason.INCOMPATIBLE_GROUP,
                        detail=f"No está habilitado para cubrir el grupo {group_id}.",
                    )
                )
                continue

            required_specialty = need.activity.required_specialty
            missing_specialty = (
                required_specialty is not None and required_specialty not in teacher.specialties
            )
            if missing_specialty and need.activity.activity_type is not ActivityType.CLASS:
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.REJECTED,
                        rejection_reason=CandidateRejectionReason.MISSING_SPECIALTY,
                        detail=(
                            f"La actividad requiere la especialidad {required_specialty} y el "
                            "docente no la tiene."
                        ),
                    )
                )
                continue

            current = activities_by_teacher_slot.get((teacher.id, need.activity.slot_id))
            if current and not self._can_displace(current):
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.REJECTED,
                        displaced_activity_id=current.id,
                        rejection_reason=CandidateRejectionReason.IMMOVABLE_ACTIVITY,
                        detail=(
                            f"Tiene {current.activity_type.value} {current.id} que no puede "
                            "desplazarse en esta franja."
                        ),
                    )
                )
                continue

            historical_total = teacher.substitution_count * self.weights.substitution_history
            recent_7_days = (
                teacher.substitutions_last_7_days * self.weights.recent_substitution_7_days
            )
            recent_30_days = (
                teacher.substitutions_last_30_days * self.weights.recent_substitution_30_days
            )
            emergency = self.weights.emergency_teacher if teacher.emergency_only else 0
            displacement = self._displacement_penalty(current) if current else 0
            specialty_mismatch = self.weights.specialty_mismatch if missing_specialty else 0
            breakdown = CandidatePenaltyBreakdown(
                historical_total=historical_total,
                recent_7_days=recent_7_days,
                recent_30_days=recent_30_days,
                emergency=emergency,
                displacement=displacement,
                specialty_mismatch=specialty_mismatch,
            )
            penalty = breakdown.total
            candidates.append(_Candidate(teacher, current, penalty, breakdown))

            if missing_specialty:
                warning = (
                    f"Cobertura excepcional sin especialidad {required_specialty}. "
                    "El docente puede atender al grupo, pero no posee la especialidad requerida."
                )
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.WARNING_ALTERNATIVE,
                        penalty=penalty,
                        penalty_breakdown=breakdown,
                        displaced_activity_id=current.id if current else None,
                        detail=(
                            "Candidato utilizable solo como cobertura excepcional; se penaliza "
                            "por falta de especialidad."
                        ),
                        warning=warning,
                    )
                )
            else:
                assessments.append(
                    CandidateAssessment(
                        activity_id=need.activity.id,
                        slot_id=need.activity.slot_id,
                        group_id=group_id,
                        teacher_id=teacher.id,
                        status=CandidateStatus.VALID_ALTERNATIVE,
                        penalty=penalty,
                        penalty_breakdown=breakdown,
                        displaced_activity_id=current.id if current else None,
                        detail="Cumple las restricciones duras para esta cobertura.",
                    )
                )

        return tuple(candidates), tuple(assessments)
