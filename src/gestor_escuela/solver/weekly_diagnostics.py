"""Conservative school timetable diagnostics for proven infeasible previews.

Only report capacity constraints that are mathematically impossible. Do not
include pupil tokens, health data or speculation about the solver's decisions.
"""

from __future__ import annotations

from collections import defaultdict

from gestor_escuela.solver.group_support import GroupSupportDemand
from gestor_escuela.solver.weekly_timetable import (
    BusyInterval,
    LessonDemand,
    SupportDemand,
)


def _available_minutes(
    busy: tuple[BusyInterval, ...],
    kind: str,
    resource_id: str,
    days: tuple[int, ...],
    start: int,
    end: int,
) -> int:
    if end <= start:
        return 0
    total = 0
    for weekday in set(days):
        occupied = sorted(
            (max(start, item.start), min(end, item.end))
            for item in busy
            if item.weekday == weekday
            and getattr(item, kind) == resource_id
            and item.start < end and item.end > start
        )
        cursor = start
        for block_start, block_end in occupied:
            if block_start > cursor:
                total += block_start - cursor
            cursor = max(cursor, block_end)
        if cursor < end:
            total += end - cursor
    return total


def explain_weekly_infeasible(
    lessons: tuple[LessonDemand, ...],
    supports: tuple[SupportDemand, ...],
    groups: tuple[GroupSupportDemand, ...],
    busy: tuple[BusyInterval, ...],
    start: int,
    end: int,
) -> tuple[str, ...]:
    reasons: list[str] = []

    # A single subject cannot fit if its declared windows and fixed class or
    # specialist unavailability leave fewer minutes than its required total.
    for lesson in lessons:
        window_start = max(start, lesson.earliest_start if lesson.earliest_start is not None else start)
        window_end = min(end, lesson.latest_end if lesson.latest_end is not None else end)
        teacher_free = _available_minutes(
            busy, "teacher_id", lesson.teacher_id, lesson.allowed_days,
            window_start, window_end,
        )
        group_free = _available_minutes(
            busy, "group_id", lesson.group_id, lesson.allowed_days,
            window_start, window_end,
        )
        available = min(teacher_free, group_free)
        if lesson.weekly_minutes > available:
            reasons.append(
                f"{lesson.group_id} / {lesson.subject_id}: requiere "
                f"{lesson.weekly_minutes} min, pero hay como máximo "
                f"{available} min disponibles en los días y franjas permitidos."
            )

    # Teacher demand is at least all class minutes plus one full group
    # session per allocated block, regardless of how many pupils attend.
    teacher_load: dict[str, int] = defaultdict(int)
    for lesson in lessons:
        teacher_load[lesson.teacher_id] += lesson.weekly_minutes
    for support in supports:
        teacher_load[support.teacher_id] += support.weekly_minutes
    for group in groups:
        teacher_load[group.teacher_id] += max(
            person.weekly_minutes for person in group.participants
        )

    for teacher_id, required in teacher_load.items():
        available = _available_minutes(
            busy, "teacher_id", teacher_id, (0, 1, 2, 3, 4), start, end
        )
        if required > available:
            reasons.append(
                f"Profesional {teacher_id}: tiene {required} min de docencia "
                f"y apoyos, pero solo {available} min libres en la semana."
            )

    class_load: dict[str, int] = defaultdict(int)
    for lesson in lessons:
        class_load[lesson.group_id] += lesson.weekly_minutes
    for class_id, required in class_load.items():
        available = _available_minutes(
            busy, "group_id", class_id, (0, 1, 2, 3, 4), start, end
        )
        if required > available:
            reasons.append(
                f"Clase {class_id}: requiere {required} min de materias "
                f"ordinarias, pero solo dispone de {available} min libres."
            )

    # Already-fixed teacher or whole-class blocks overlapping are themselves
    # impossible to satisfy. Do not inspect/report private pupil tokens.
    occupied: dict[tuple[str, str, int], list[tuple[int, int]]] = defaultdict(list)
    for block in busy:
        if block.teacher_id:
            occupied[("profesional", block.teacher_id, block.weekday)].append(
                (block.start, block.end)
            )
        if block.group_id:
            occupied[("clase", block.group_id, block.weekday)].append(
                (block.start, block.end)
            )
    for (kind, resource, weekday), entries in occupied.items():
        entries.sort()
        latest_end = -1
        for block_start, block_end in entries:
            if block_start < latest_end:
                reasons.append(
                    f"Los bloqueos fijos de {kind} {resource} se solapan "
                    f"el día {weekday + 1}; revisa esas asignaciones."
                )
                break
            latest_end = max(latest_end, block_end)

    return tuple(reasons[:8])
