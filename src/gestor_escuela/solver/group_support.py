"""Shared PT/AL sessions with exact per-pupil attendance and minutes.

One group session occupies a single teacher interval even if several pupils
attend. Attendance is individually optional, but each remaining target must
be met exactly, without allocating surplus minutes.
"""

from __future__ import annotations

from collections.abc import MutableSequence
from dataclasses import dataclass

from ortools.sat.python import cp_model

from gestor_escuela.solver.support_preferences import (
    ClassEvents,
    add_extraction_preferences,
)
from gestor_escuela.solver.weekly_resources import WeeklyResources
from gestor_escuela.solver.weekly_rooms import WeeklyRooms


@dataclass(frozen=True, slots=True)
class GroupParticipant:
    pupil_token: str
    group_id: str
    weekly_minutes: int
    blocked_subjects: tuple[str, ...] = ()
    avoided_subjects: tuple[str, ...] = ()
    preferred_subjects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GroupSupportDemand:
    request_id: str
    service: str
    teacher_id: str
    session_minutes: int
    participants: tuple[GroupParticipant, ...]
    allowed_days: tuple[int, ...] = (0, 1, 2, 3, 4)
    max_sessions_per_day: int = 2
    location_id: str | None = None
    room_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlacedGroupSupport:
    request_id: str
    service: str
    weekday: int
    start: int
    end: int
    participant_tokens: tuple[str, ...]


@dataclass(slots=True)
class _GroupSession:
    request: GroupSupportDemand
    duration: int
    start: cp_model.IntVar
    days: dict[int, cp_model.IntVar]
    attendees: dict[str, cp_model.IntVar]


def add_group_supports(
    model: cp_model.CpModel,
    groups: tuple[GroupSupportDemand, ...],
    intervals: dict[tuple[str, str, int], list[cp_model.IntervalVar]],
    classes: dict[tuple[str, str, int], list[cp_model.IntervalVar]],
    events: ClassEvents,
    objective: MutableSequence[cp_model.LinearExpr],
    day_start: int,
    day_end: int,
    resources: WeeklyResources,
    rooms: WeeklyRooms,
) -> list[_GroupSession]:
    selections: list[_GroupSession] = []
    for index, group in enumerate(groups):
        duration = group.session_minutes
        if not group.participants or duration < 15 or duration > 180 or duration % 15:
            raise ValueError("Los apoyos grupales necesitan participantes y duración válida.")
        maximum = max(person.weekly_minutes for person in group.participants)
        if any(
            person.weekly_minutes <= 0
            or person.weekly_minutes % duration
            or person.weekly_minutes > 900
            for person in group.participants
        ):
            raise ValueError("Cada participante necesita sesiones completas sin exceso.")
        if not group.allowed_days:
            raise ValueError("Un apoyo grupal necesita al menos un día.")
        slots = maximum // duration
        if slots > 20:
            raise ValueError("El grupo supera el límite de 20 sesiones.")
        if duration > day_end - day_start:
            raise ValueError("Una sesión grupal no cabe en la jornada.")
        pupil_attendance: dict[str, list[cp_model.IntVar]] = {
            person.pupil_token: [] for person in group.participants
        }
        day_attendance: dict[int, list[cp_model.IntVar]] = {
            weekday: [] for weekday in group.allowed_days
        }
        for slot in range(slots):
            start = model.new_int_var(
                day_start // 15, (day_end - duration) // 15,
                f"group_start_{index}_{slot}",
            )
            days: dict[int, cp_model.IntVar] = {}
            attendees: dict[str, cp_model.IntVar] = {}
            for person in group.participants:
                attendee = model.new_bool_var(
                    f"group_attendee_{index}_{slot}_{person.pupil_token}"
                )
                attendees[person.pupil_token] = attendee
                pupil_attendance[person.pupil_token].append(attendee)

            attendance_count = model.new_int_var(
                1, len(group.participants), f"group_count_{index}_{slot}"
            )
            model.add(attendance_count == sum(attendees.values()))
            for weekday in group.allowed_days:
                present = model.new_bool_var(f"group_day_{index}_{slot}_{weekday}")
                days[weekday] = present
                group_interval = model.new_optional_fixed_size_interval_var(
                    start, duration // 15, present,
                    f"group_teacher_{index}_{slot}_{weekday}",
                )
                intervals[("teacher", group.teacher_id, weekday)].append(group_interval)
                if group.room_id:
                    rooms.reserve(group.room_id, weekday, group_interval, attendance_count)
                resources.add_teacher(
                    group.teacher_id, weekday, start, duration // 15,
                    present, group.location_id,
                )
                day_attendance[weekday].append(present)

                for person in group.participants:
                    attending = model.new_bool_var(
                        f"group_on_day_{index}_{slot}_{person.pupil_token}_{weekday}"
                    )
                    attendee = attendees[person.pupil_token]
                    model.add(attending <= attendee)
                    model.add(attending <= present)
                    model.add(attending >= attendee + present - 1)
                    pupil_interval = model.new_optional_fixed_size_interval_var(
                        start, duration // 15, attending,
                        f"group_pupil_{index}_{slot}_{person.pupil_token}_{weekday}",
                    )
                    intervals[("pupil", person.pupil_token, weekday)].append(
                        pupil_interval
                    )
                    for subject in person.blocked_subjects:
                        for class_interval in classes.get(
                            (person.group_id, subject, weekday), ()
                        ):
                            model.add_no_overlap([pupil_interval, class_interval])
                    add_extraction_preferences(
                        model, start, start + duration // 15, attending,
                        person.group_id, weekday,
                        person.avoided_subjects, person.preferred_subjects,
                        events, objective,
                        f"group_pref_{index}_{slot}_{person.pupil_token}_{weekday}",
                    )
            model.add_exactly_one(days.values())
            selections.append(_GroupSession(group, duration, start, days, attendees))
            objective.append(start - day_start // 15)

        # The pupil with the largest target necessarily attends all group
        # sessions; other pupils join only as many as their objective requires.
        for person in group.participants:
            model.add(
                sum(pupil_attendance[person.pupil_token])
                == person.weekly_minutes // duration
            )
        for weekday in group.allowed_days:
            model.add(sum(day_attendance[weekday]) <= group.max_sessions_per_day)
    return selections


def extract_group_supports(
    solver: cp_model.CpSolver, selections: list[_GroupSession],
) -> tuple[PlacedGroupSupport, ...]:
    placed = []
    for item in selections:
        weekday = next(
            day for day, present in item.days.items() if solver.value(present)
        )
        start = solver.value(item.start) * 15
        attending = tuple(
            pupil for pupil, selected in item.attendees.items() if solver.value(selected)
        )
        placed.append(
            PlacedGroupSupport(
                item.request.request_id, item.request.service, weekday, start,
                start + item.duration, attending,
            )
        )
    return tuple(sorted(placed, key=lambda item: (item.weekday, item.start, item.request_id)))
