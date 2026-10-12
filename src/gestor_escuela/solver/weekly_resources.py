"""Explicit room exclusivity and minimum travel between teacher locations.

No travel is inferred unless both activities have distinct, known location IDs.
Times are integer 15-minute ticks; the same location needs no transition.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model


@dataclass(frozen=True, slots=True)
class TeacherEvent:
    start_tick: cp_model.IntVar | int
    duration_ticks: int
    presence: cp_model.IntVar | None
    location_id: str | None


class WeeklyResources:
    def __init__(self) -> None:
        self.events: dict[tuple[str, int], list[TeacherEvent]] = defaultdict(list)

    def add_teacher(
        self,
        teacher_id: str,
        weekday: int,
        start_tick: cp_model.IntVar | int,
        duration_ticks: int,
        presence: cp_model.IntVar | None,
        location_id: str | None,
    ) -> None:
        self.events[(teacher_id, weekday)].append(
            TeacherEvent(start_tick, duration_ticks, presence, location_id)
        )

    def constrain_travel(self, model: cp_model.CpModel, travel_minutes: int) -> None:
        if travel_minutes < 0 or travel_minutes > 60 or travel_minutes % 15:
            raise ValueError("El tiempo de desplazamiento debe ser 0–60 min en pasos de 15.")
        if not travel_minutes:
            return
        gap_ticks = travel_minutes // 15
        for teacher_day, activities in self.events.items():
            for index, first in enumerate(activities):
                if not first.location_id:
                    continue
                for other_index in range(index + 1, len(activities)):
                    second = activities[other_index]
                    if not second.location_id or first.location_id == second.location_id:
                        continue
                    first_before = model.new_bool_var(
                        f"travel_order_{teacher_day[0]}_{teacher_day[1]}_{index}_{other_index}"
                    )
                    prerequisites = [
                        presence
                        for presence in (first.presence, second.presence)
                        if presence is not None
                    ]
                    model.add(
                        second.start_tick
                        >= first.start_tick + first.duration_ticks + gap_ticks
                    ).only_enforce_if([*prerequisites, first_before])
                    model.add(
                        first.start_tick
                        >= second.start_tick + second.duration_ticks + gap_ticks
                    ).only_enforce_if([*prerequisites, first_before.Not()])
