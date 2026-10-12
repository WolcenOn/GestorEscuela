"""Non-destructive CP-SAT timetable preview from explicit curriculum session lengths.

All intervals use 15-minute integers to avoid floating-point drift. A hard
constraint must never be relaxed to manufacture a feasible school timetable.
PT/AL pupils and explicit room resources share the same constraint model.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from gestor_escuela.solver.group_support import (
    GroupSupportDemand,
    PlacedGroupSupport,
    add_group_supports,
    extract_group_supports,
)
from gestor_escuela.solver.support_preferences import add_extraction_preferences
from gestor_escuela.solver.weekly_resources import TravelRule, WeeklyResources
from gestor_escuela.solver.weekly_rooms import (
    RoomSpec,
    WeeklyRooms,
    allocate_candidate_room,
)


@dataclass(frozen=True, slots=True)
class LessonDemand:
    group_id: str
    subject_id: str
    teacher_id: str
    weekly_minutes: int
    durations: tuple[int, ...]
    allowed_days: tuple[int, ...] = (0, 1, 2, 3, 4)
    preferred_days: tuple[int, ...] = ()
    earliest_start: int | None = None
    latest_end: int | None = None
    max_sessions_per_day: int = 2
    location_id: str | None = None
    room_id: str | None = None


@dataclass(frozen=True, slots=True)
class BusyInterval:
    weekday: int
    start: int
    end: int
    teacher_id: str | None = None
    group_id: str | None = None
    pupil_token: str | None = None
    location_id: str | None = None
    room_id: str | None = None
    room_units: int | None = None


@dataclass(frozen=True, slots=True)
class SupportDemand:
    request_id: str
    service: str
    teacher_id: str
    pupil_token: str
    group_id: str
    weekly_minutes: int
    durations: tuple[int, ...]
    blocked_subjects: tuple[str, ...] = ()
    avoided_subjects: tuple[str, ...] = ()
    preferred_subjects: tuple[str, ...] = ()
    allowed_days: tuple[int, ...] = (0, 1, 2, 3, 4)
    max_sessions_per_day: int = 2
    location_id: str | None = None
    room_id: str | None = None
    room_candidates: tuple[str, ...] = ()
    required_features: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlacedSupport:
    request_id: str
    service: str
    teacher_id: str
    pupil_token: str
    weekday: int
    start: int
    end: int
    room_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlacedLesson:
    group_id: str
    subject_id: str
    teacher_id: str
    weekday: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TimetablePreview:
    status: str
    lessons: tuple[PlacedLesson, ...] = ()
    solver_status: str = ""
    wall_time_seconds: float = 0.0
    reasons: tuple[str, ...] = ()
    supports: tuple[PlacedSupport, ...] = ()
    group_supports: tuple[PlacedGroupSupport, ...] = ()


def solve_weekly_timetable(
    demands: tuple[LessonDemand, ...],
    busy: tuple[BusyInterval, ...],
    start: int,
    end: int,
    max_time_seconds: float = 5.0,
    supports: tuple[SupportDemand, ...] = (),
    group_supports: tuple[GroupSupportDemand, ...] = (),
    travel_minutes: int = 0,
    travel_rules: tuple[TravelRule, ...] = (),
    room_specs: tuple[RoomSpec, ...] = (),
) -> TimetablePreview:
    """Place explicit durations exactly; never invent a remainder or miss minutes."""
    if start >= end or any(value % 15 for value in (start, end)):
        raise ValueError("Jornada inválida: se exige una rejilla de 15 minutos.")
    if not 0 < max_time_seconds <= 15:
        raise ValueError("El límite de búsqueda debe estar entre 0 y 15 segundos.")

    model = cp_model.CpModel()
    resources = WeeklyResources()
    rooms = WeeklyRooms()

    # Equipment restrictions are hard: a missing feature must not be
    # "optimized away". This check is independent of when sessions start.
    room_catalog = {spec.room_id: spec for spec in room_specs}
    required_needs: tuple[SupportDemand | GroupSupportDemand, ...] = (
        *supports, *group_supports,
    )
    for need in required_needs:
        if not need.required_features:
            continue
        if need.room_candidates:
            if any(
                set(need.required_features).issubset(room_catalog[room_id].features)
                for room_id in need.room_candidates if room_id in room_catalog
            ):
                continue
            return TimetablePreview(
                "infeasible",
                reasons=("No hay salas candidatas que cumplan el equipamiento requerido.",),
            )
        if need.room_id is None or need.room_id not in room_catalog:
            raise ValueError(
                "Un apoyo requiere equipamiento, pero su sala no está configurada."
            )
        if not set(need.required_features).issubset(room_catalog[need.room_id].features):
            return TimetablePreview(
                "infeasible",
                reasons=("La sala fija del apoyo carece del equipamiento requerido.",),
            )
    intervals: dict[tuple[str, str, int], list[cp_model.IntervalVar]] = defaultdict(list)
    daily_demands: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    decisions: list[tuple[LessonDemand, int, cp_model.IntVar, dict[int, cp_model.IntVar]]] = []
    soft_terms: list[cp_model.LinearExpr] = []
    class_intervals: dict[tuple[str, str, int], list[cp_model.IntervalVar]] = defaultdict(list)
    class_events: dict[
        tuple[str, str, int], list[tuple[cp_model.IntVar, int, cp_model.IntVar]]
    ] = defaultdict(list)
    support_choices: list[
        tuple[
            SupportDemand, int, cp_model.IntVar,
            dict[int, cp_model.IntVar], dict[str, cp_model.IntVar],
        ]
    ] = []

    for index, demand in enumerate(demands):
        if sum(demand.durations) != demand.weekly_minutes:
            raise ValueError(
                f"{demand.group_id}/{demand.subject_id}: las sesiones no suman "
                "la carga curricular semanal."
            )
        for session_index, duration in enumerate(demand.durations):
            if duration <= 0 or duration > 180 or duration % 15:
                raise ValueError("Cada sesión debe durar entre 15 y 180 minutos, en pasos de 15.")
            day_start = max(start, demand.earliest_start or start)
            day_end = min(end, demand.latest_end or end)
            if day_start % 15 or day_end % 15:
                raise ValueError("Las ventanas docentes deben usar la rejilla de 15 minutos.")
            if day_end - day_start < duration:
                return TimetablePreview(
                    status="infeasible",
                    reasons=(f"{demand.group_id}/{demand.subject_id}: "
                             f"no cabe una sesión de {duration} min en la ventana.",),
                )
            first_tick = day_start // 15
            last_tick = (day_end - duration) // 15
            duration_ticks = duration // 15
            start_var = model.new_int_var(first_tick, last_tick, f"start_{index}_{session_index}")
            days: dict[int, cp_model.IntVar] = {}
            for weekday in demand.allowed_days:
                present = model.new_bool_var(f"day_{index}_{session_index}_{weekday}")
                interval = model.new_optional_fixed_size_interval_var(
                    start_var, duration_ticks, present,
                    f"lesson_{index}_{session_index}_{weekday}",
                )
                intervals[("teacher", demand.teacher_id, weekday)].append(interval)
                intervals[("group", demand.group_id, weekday)].append(interval)
                if demand.room_id:
                    rooms.reserve(demand.room_id, weekday, interval, exclusive=True)
                resources.add_teacher(
                    demand.teacher_id, weekday, start_var, duration_ticks,
                    present, demand.location_id,
                )
                class_intervals[(demand.group_id, demand.subject_id, weekday)].append(interval)
                class_events[(demand.group_id, demand.subject_id, weekday)].append(
                    (start_var, duration_ticks, present)
                )
                daily_demands[(index, weekday)].append(present)
                days[weekday] = present
                if demand.preferred_days and weekday not in demand.preferred_days:
                    soft_terms.append(60 * present)
            model.add_exactly_one(days.values())
            decisions.append((demand, duration, start_var, days))
            soft_terms.append(start_var - first_tick)

    for index, demand in enumerate(demands):
        for weekday in demand.allowed_days:
            model.add(sum(daily_demands[(index, weekday)]) <= demand.max_sessions_per_day)

    # PT/AL groups may extract one pupil during ordinary class instruction.
    # Only lessons for which extraction is forbidden block that pupil's support.
    # Every pupil token and professional gets a global no-overlap timeline.
    for index, support in enumerate(supports):
        if sum(support.durations) != support.weekly_minutes:
            raise ValueError(f"Apoyo {index}: los minutos no coinciden con el objetivo.")
        if not support.allowed_days:
            raise ValueError(f"Apoyo {index}: debe admitir al menos un día.")
        for session_index, duration in enumerate(support.durations):
            if not 15 <= duration <= 180 or duration % 15:
                raise ValueError("Los apoyos deben tener duración de 15–180 min.")
            if duration > end - start:
                return TimetablePreview(
                    "infeasible",
                    reasons=(f"Apoyo {index}: sesión de {duration} min fuera de jornada.",),
                )
            start_var = model.new_int_var(
                start // 15, (end - duration) // 15,
                f"support_start_{index}_{session_index}",
            )
            by_day: dict[int, cp_model.IntVar] = {}
            for weekday in support.allowed_days:
                present = model.new_bool_var(f"support_day_{index}_{session_index}_{weekday}")
                interval = model.new_optional_fixed_size_interval_var(
                    start_var, duration // 15, present,
                    f"support_{index}_{session_index}_{weekday}",
                )
                intervals[("teacher", support.teacher_id, weekday)].append(interval)
                intervals[("pupil", support.pupil_token, weekday)].append(interval)
                if support.room_id:
                    rooms.reserve(support.room_id, weekday, interval)
                if not support.room_candidates:
                    resources.add_teacher(
                        support.teacher_id, weekday, start_var, duration // 15,
                        present, support.location_id,
                    )
                daily_demands[(len(demands) + index, weekday)].append(present)
                for subject in support.blocked_subjects:
                    for class_interval in class_intervals.get(
                        (support.group_id, subject, weekday), ()
                    ):
                        model.add_no_overlap([interval, class_interval])
                add_extraction_preferences(
                    model, start_var, start_var + duration // 15, present,
                    support.group_id, weekday,
                    support.avoided_subjects, support.preferred_subjects,
                    class_events, soft_terms,
                    f"single_pref_{index}_{session_index}_{weekday}",
                )
                by_day[weekday] = present
            model.add_exactly_one(by_day.values())
            chosen = (
                allocate_candidate_room(
                    model, rooms, resources, support.teacher_id,
                    by_day, start_var, duration // 15,
                    tuple(
                        room_id for room_id in support.room_candidates
                        if room_id in room_catalog
                        and set(support.required_features).issubset(
                            room_catalog[room_id].features
                        )
                    ),
                    1, f"single_{index}_{session_index}",
                )
                if support.room_candidates else {}
            )
            support_choices.append((support, duration, start_var, by_day, chosen))
            soft_terms.append(start_var - start // 15)
        for weekday in support.allowed_days:
            model.add(
                sum(daily_demands[(len(demands) + index, weekday)])
                <= support.max_sessions_per_day
            )

    grouped = add_group_supports(
        model, group_supports, intervals, class_intervals,
        class_events, soft_terms, start, end,
        resources, rooms, room_catalog,
    )

    for index, block in enumerate(busy):
        if block.start >= block.end:
            raise ValueError("Un bloqueo debe terminar después de su inicio.")
        fixed = model.new_fixed_size_interval_var(
            block.start // 15,
            (block.end - block.start) // 15,
            f"blocked_{index}",
        )
        if block.teacher_id:
            intervals[("teacher", block.teacher_id, block.weekday)].append(fixed)
            resources.add_teacher(
                block.teacher_id, block.weekday,
                block.start // 15, (block.end - block.start) // 15,
                None, block.location_id,
            )
        if block.room_id:
            rooms.reserve(
                block.room_id, block.weekday, fixed,
                persons=block.room_units or 1,
                exclusive=block.room_units is None,
            )
        if block.group_id:
            intervals[("group", block.group_id, block.weekday)].append(fixed)
        if block.pupil_token:
            intervals[("pupil", block.pupil_token, block.weekday)].append(fixed)

    for entries in intervals.values():
        if len(entries) > 1:
            model.add_no_overlap(entries)

    resources.constrain_travel(model, travel_minutes, travel_rules)
    known_rooms = {item.room_id for item in room_specs}
    selected_demands: tuple[SupportDemand | GroupSupportDemand, ...] = (
        *supports, *group_supports,
    )
    for need in selected_demands:
        if need.room_candidates and (
            need.room_id or need.location_id
            or any(candidate not in known_rooms for candidate in need.room_candidates)
        ):
            raise ValueError("La selección automática requiere salas configuradas sin aula fija.")
    rooms.constrain(model, room_specs, start, end)

    if soft_terms:
        model.minimize(sum(soft_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE:
            return TimetablePreview(
                "infeasible", solver_status=name,
                wall_time_seconds=solver.wall_time,
                reasons=("No existe una distribución que cumpla todas las restricciones duras.",),
            )
        return TimetablePreview(
            "unknown", solver_status=name,
            wall_time_seconds=solver.wall_time,
            reasons=("La búsqueda terminó sin solución demostrada; no equivale a inviable.",),
        )

    lessons = []
    for demand, duration, start_var, days in decisions:
        weekday = next(day for day, present in days.items() if solver.value(present))
        start_minute = solver.value(start_var) * 15
        lessons.append(PlacedLesson(
            demand.group_id, demand.subject_id, demand.teacher_id,
            weekday, start_minute, start_minute + duration,
        ))
    lessons.sort(key=lambda item: (item.weekday, item.start, item.group_id, item.subject_id))
    placed_support = []
    for support, duration, start_var, days, chosen in support_choices:
        weekday = next(day for day, present in days.items() if solver.value(present))
        start_minute = solver.value(start_var) * 15
        room_id = next(
            (room for room, selected in chosen.items() if solver.value(selected)),
            support.room_id,
        )
        placed_support.append(
            PlacedSupport(
                support.request_id, support.service, support.teacher_id,
                support.pupil_token, weekday, start_minute, start_minute + duration,
                room_id,
            )
        )
    placed_support.sort(key=lambda item: (item.weekday, item.start, item.request_id))
    return TimetablePreview(
        "feasible", tuple(lessons), name, solver.wall_time,
        supports=tuple(placed_support),
        group_supports=extract_group_supports(solver, grouped),
    )
