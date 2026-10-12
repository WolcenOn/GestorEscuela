"""Tenant-scoped, read-only weekly timetable preview.

The browser supplies planned session lengths from its per-course subject
patterns. No sensitive student data is required or stored.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from gestor_escuela.api.auth import PlannerDep, SessionDep
from gestor_escuela.persistence.models import SchoolRow
from gestor_escuela.solver.group_support import (
    GroupParticipant,
    GroupSupportDemand,
)
from gestor_escuela.solver.weekly_diagnostics import explain_weekly_infeasible
from gestor_escuela.solver.weekly_timetable import (
    BusyInterval,
    LessonDemand,
    SupportDemand,
    TimetablePreview,
    solve_weekly_timetable,
)

router = APIRouter()
_CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


def _minute(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def _clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


class LessonDemandInput(BaseModel):
    group_id: str = Field(min_length=1, max_length=64)
    subject_id: str = Field(min_length=1, max_length=120)
    teacher_id: str = Field(min_length=1, max_length=64)
    weekly_minutes: int = Field(gt=0, le=1800, multiple_of=15)
    durations: list[int] = Field(min_length=1, max_length=30)
    allowed_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    preferred_days: list[int] = Field(default_factory=list)
    earliest_start: str | None = Field(default=None, pattern=_CLOCK)
    latest_end: str | None = Field(default=None, pattern=_CLOCK)
    max_sessions_per_day: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def check_durations(self) -> LessonDemandInput:
        if sum(self.durations) != self.weekly_minutes:
            raise ValueError("La suma de sesiones debe igualar los minutos curriculares")
        if any(value < 15 or value > 180 or value % 15 for value in self.durations):
            raise ValueError("Las sesiones deben durar 15–180 min en pasos de 15")
        if any(day not in range(5) for day in self.allowed_days + self.preferred_days):
            raise ValueError("Los días permitidos deben estar entre 0 y 4")
        if len(set(self.allowed_days)) != len(self.allowed_days):
            raise ValueError("No se pueden repetir días permitidos")
        if any(day not in self.allowed_days for day in self.preferred_days):
            raise ValueError("Los días preferidos deben ser también permitidos")
        if self.earliest_start and _minute(self.earliest_start) % 15:
            raise ValueError("Las horas deben encajar en la rejilla de 15 min")
        if self.latest_end and _minute(self.latest_end) % 15:
            raise ValueError("Las horas deben encajar en la rejilla de 15 min")
        if (self.earliest_start and self.latest_end
                and self.earliest_start >= self.latest_end):
            raise ValueError("La ventana temporal tiene un fin anterior al inicio")
        return self


class BusyBlockInput(BaseModel):
    weekday: int = Field(ge=0, le=4)
    start_time: str = Field(pattern=_CLOCK)
    end_time: str = Field(pattern=_CLOCK)
    teacher_id: str | None = Field(default=None, max_length=64)
    group_id: str | None = Field(default=None, max_length=64)
    pupil_token: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def check_block(self) -> BusyBlockInput:
        if not self.teacher_id and not self.group_id and not self.pupil_token:
            raise ValueError("Indica docente, grupo o alumno anónimo para el bloqueo")
        if self.end_time <= self.start_time:
            raise ValueError("El bloqueo debe acabar después de empezar")
        if _minute(self.start_time) % 15 or _minute(self.end_time) % 15:
            raise ValueError("Los bloqueos deben ajustarse a 15 minutos")
        return self


class SupportDemandInput(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    service: str = Field(pattern=r"^(PT|AL)$")
    teacher_id: str = Field(min_length=1, max_length=64)
    pupil_token: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=64)
    weekly_minutes: int = Field(gt=0, le=900, multiple_of=15)
    durations: list[int] = Field(min_length=1, max_length=20)
    blocked_subjects: list[str] = Field(default_factory=list, max_length=30)
    avoided_subjects: list[str] = Field(default_factory=list, max_length=30)
    preferred_subjects: list[str] = Field(default_factory=list, max_length=30)
    allowed_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    max_sessions_per_day: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def check_sessions(self) -> SupportDemandInput:
        if sum(self.durations) != self.weekly_minutes:
            raise ValueError("La carga PT/AL debe coincidir con la suma de sesiones")
        if any(duration < 15 or duration > 180 or duration % 15 for duration in self.durations):
            raise ValueError("Los apoyos deben durar entre 15 y 180 minutos")
        if any(day not in range(5) for day in self.allowed_days):
            raise ValueError("Los días deben estar entre lunes y viernes")
        if len(set(self.allowed_days)) != len(self.allowed_days):
            raise ValueError("No se pueden repetir días de apoyo")
        if len(set(self.blocked_subjects)) != len(self.blocked_subjects):
            raise ValueError("No se pueden repetir asignaturas bloqueadas")
        return self


class GroupParticipantInput(BaseModel):
    pupil_token: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=64)
    weekly_minutes: int = Field(gt=0, le=900, multiple_of=15)
    blocked_subjects: list[str] = Field(default_factory=list, max_length=30)
    avoided_subjects: list[str] = Field(default_factory=list, max_length=30)
    preferred_subjects: list[str] = Field(default_factory=list, max_length=30)


class GroupSupportInput(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    service: str = Field(pattern=r"^(PT|AL)$")
    teacher_id: str = Field(min_length=1, max_length=64)
    session_minutes: int = Field(ge=15, le=180, multiple_of=15)
    participants: list[GroupParticipantInput] = Field(min_length=1, max_length=8)
    allowed_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    max_sessions_per_day: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_group(self) -> GroupSupportInput:
        if any(day not in range(5) for day in self.allowed_days):
            raise ValueError("Los días del apoyo grupal deben ser de lunes a viernes")
        if len(set(self.allowed_days)) != len(self.allowed_days):
            raise ValueError("No se pueden repetir días del apoyo grupal")
        if len({person.pupil_token for person in self.participants}) != len(self.participants):
            raise ValueError("Un alumno no puede aparecer dos veces en el mismo apoyo")
        if any(
            person.weekly_minutes % self.session_minutes for person in self.participants
        ):
            raise ValueError("La duración grupal debe cubrir objetivos individuales exactos")
        if max(person.weekly_minutes for person in self.participants) // self.session_minutes > 20:
            raise ValueError("El apoyo grupal supera 20 sesiones")
        return self


class WeeklyPreviewInput(BaseModel):
    start_time: str = Field(pattern=_CLOCK)
    end_time: str = Field(pattern=_CLOCK)
    lessons: list[LessonDemandInput] = Field(min_length=1, max_length=100)
    supports: list[SupportDemandInput] = Field(default_factory=list, max_length=100)
    group_supports: list[GroupSupportInput] = Field(default_factory=list, max_length=50)
    busy: list[BusyBlockInput] = Field(default_factory=list, max_length=500)
    max_time_seconds: float = Field(default=5.0, gt=0, le=15)

    @model_validator(mode="after")
    def check_school_day(self) -> WeeklyPreviewInput:
        if self.end_time <= self.start_time:
            raise ValueError("La jornada debe terminar después de comenzar")
        if _minute(self.start_time) % 15 or _minute(self.end_time) % 15:
            raise ValueError("La jornada debe respetar la rejilla de 15 minutos")
        total_sessions = (
            sum(len(lesson.durations) for lesson in self.lessons)
            + sum(len(support.durations) for support in self.supports)
        )
        total_sessions += sum(
            max(person.weekly_minutes for person in group.participants)
            // group.session_minutes
            for group in self.group_supports
        )
        if total_sessions > 150:
            raise ValueError("El avance semanal admite hasta 150 sesiones")
        if len(self.lessons) + len(self.supports) + len(self.group_supports) > 100:
            raise ValueError("El avance semanal admite hasta 100 asignaturas y apoyos")
        requests = [
            item.request_id for item in self.supports
        ] + [item.request_id for item in self.group_supports]
        if len(set(requests)) != len(requests):
            raise ValueError("Cada apoyo necesita un identificador único")
        lesson_groups = {lesson.group_id for lesson in self.lessons}
        if any(item.group_id not in lesson_groups for item in self.supports):
            raise ValueError("El apoyo debe estar vinculado a un grupo del horario")
        if any(
            person.group_id not in lesson_groups
            for group in self.group_supports for person in group.participants
        ):
            raise ValueError("El grupo de cada participante debe existir en el horario")
        participation = [
            (support.pupil_token, support.service) for support in self.supports
        ] + [
            (person.pupil_token, group.service)
            for group in self.group_supports for person in group.participants
        ]
        if len(set(participation)) != len(participation):
            raise ValueError("Cada alumno puede tener un objetivo por servicio")
        pairs = [(lesson.group_id, lesson.subject_id) for lesson in self.lessons]
        if any(count > 1 for count in Counter(pairs).values()):
            raise ValueError("Cada clase/asignatura debe aparecer una sola vez")
        return self


@router.post("/schools/{school_id}/weekly-timetable/preview")
def preview_weekly_timetable(
    school_id: UUID,
    payload: WeeklyPreviewInput,
    session: SessionDep,
    _actor: PlannerDep,
) -> dict[str, object]:
    if session.get(SchoolRow, school_id) is None:
        raise HTTPException(status_code=404, detail="School not found")

    requirements = tuple(
        LessonDemand(
            group_id=lesson.group_id,
            subject_id=lesson.subject_id,
            teacher_id=lesson.teacher_id,
            weekly_minutes=lesson.weekly_minutes,
            durations=tuple(lesson.durations),
            allowed_days=tuple(lesson.allowed_days),
            preferred_days=tuple(lesson.preferred_days),
            earliest_start=_minute(lesson.earliest_start) if lesson.earliest_start else None,
            latest_end=_minute(lesson.latest_end) if lesson.latest_end else None,
            max_sessions_per_day=lesson.max_sessions_per_day,
        )
        for lesson in payload.lessons
    )
    busy = tuple(
        BusyInterval(
            weekday=block.weekday,
            start=_minute(block.start_time),
            end=_minute(block.end_time),
            teacher_id=block.teacher_id,
            group_id=block.group_id,
            pupil_token=block.pupil_token,
        )
        for block in payload.busy
    )
    support_needs = tuple(
        SupportDemand(
            request_id=item.request_id,
            service=item.service,
            teacher_id=item.teacher_id,
            pupil_token=item.pupil_token,
            group_id=item.group_id,
            weekly_minutes=item.weekly_minutes,
            durations=tuple(item.durations),
            blocked_subjects=tuple(item.blocked_subjects),
            avoided_subjects=tuple(item.avoided_subjects),
            preferred_subjects=tuple(item.preferred_subjects),
            allowed_days=tuple(item.allowed_days),
            max_sessions_per_day=item.max_sessions_per_day,
        )
        for item in payload.supports
    )
    grouped_needs = tuple(
        GroupSupportDemand(
            request_id=group.request_id,
            service=group.service,
            teacher_id=group.teacher_id,
            session_minutes=group.session_minutes,
            participants=tuple(
                GroupParticipant(
                    pupil_token=person.pupil_token,
                    group_id=person.group_id,
                    weekly_minutes=person.weekly_minutes,
                    blocked_subjects=tuple(person.blocked_subjects),
                    avoided_subjects=tuple(person.avoided_subjects),
                    preferred_subjects=tuple(person.preferred_subjects),
                )
                for person in group.participants
            ),
            allowed_days=tuple(group.allowed_days),
            max_sessions_per_day=group.max_sessions_per_day,
        )
        for group in payload.group_supports
    )
    try:
        result: TimetablePreview = solve_weekly_timetable(
            requirements,
            busy,
            _minute(payload.start_time),
            _minute(payload.end_time),
            payload.max_time_seconds,
            supports=support_needs,
            group_supports=grouped_needs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    reasons = result.reasons
    if result.status == "infeasible":
        concrete = explain_weekly_infeasible(
            requirements, support_needs, grouped_needs, busy,
            _minute(payload.start_time), _minute(payload.end_time),
        )
        if concrete:
            reasons = concrete

    return {
        "status": result.status,
        "solver_status": result.solver_status,
        "wall_time_seconds": result.wall_time_seconds,
        "preview_only": True,
        "lessons": [
            {
                "group_id": item.group_id,
                "subject_id": item.subject_id,
                "teacher_id": item.teacher_id,
                "weekday": item.weekday,
                "start_time": _clock(item.start),
                "end_time": _clock(item.end),
            }
            for item in result.lessons
        ],
        "reasons": list(reasons),
        "group_supports": [
            {
                "request_id": item.request_id,
                "service": item.service,
                "weekday": item.weekday,
                "start_time": _clock(item.start),
                "end_time": _clock(item.end),
                "participant_count": len(item.participant_tokens),
            }
            for item in result.group_supports
        ],
        "supports": [
            {
                "request_id": item.request_id,
                "service": item.service,
                "weekday": item.weekday,
                "start_time": _clock(item.start),
                "end_time": _clock(item.end),
            }
            for item in result.supports
        ],
    }
