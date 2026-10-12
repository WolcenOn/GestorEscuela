"""Optional room occupancies and opening hours for weekly timetable previews.

Unconfigured rooms retain legacy exclusive-session semantics; only explicitly
configured capacities are counted by number of pupils. Class lessons and
room-only reservations always reserve an entire configured room.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model


@dataclass(frozen=True, slots=True)
class RoomWindow:
    weekday: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class RoomSpec:
    room_id: str
    capacity: int
    windows: tuple[RoomWindow, ...] = ()


@dataclass(frozen=True, slots=True)
class RoomUse:
    interval: cp_model.IntervalVar
    persons: int | cp_model.IntVar
    exclusive: bool = False


class WeeklyRooms:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, int], list[RoomUse]] = defaultdict(list)

    def reserve(
        self,
        room_id: str,
        weekday: int,
        interval: cp_model.IntervalVar,
        persons: int | cp_model.IntVar = 1,
        exclusive: bool = False,
    ) -> None:
        self.entries[(room_id, weekday)].append(RoomUse(interval, persons, exclusive))

    def constrain(
        self,
        model: cp_model.CpModel,
        specs: tuple[RoomSpec, ...],
        day_start: int,
        day_end: int,
    ) -> None:
        rooms = {item.room_id: item for item in specs}
        if len(rooms) != len(specs):
            raise ValueError("No se puede definir dos veces la misma sala.")
        for spec in specs:
            if not spec.room_id or not 1 <= spec.capacity <= 30:
                raise ValueError("Cada sala necesita identificador y aforo de 1 a 30.")
            by_day: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for window in spec.windows:
                if (
                    window.weekday not in range(5)
                    or window.start < day_start or window.end > day_end
                    or window.start >= window.end
                    or window.start % 15 or window.end % 15
                ):
                    raise ValueError("Horario de sala fuera de jornada o rejilla.")
                by_day[window.weekday].append((window.start, window.end))
            for entries in by_day.values():
                entries.sort()
                if any(entries[i][1] > entries[i + 1][0] for i in range(len(entries) - 1)):
                    raise ValueError("Los horarios de la misma sala se solapan.")

        for (room_id, weekday), uses in self.entries.items():
            if room_id not in rooms:
                # Compatibility: previously any PT/AL group, regardless of
                # participants, booked an *exclusive* room session.
                if len(uses) > 1:
                    model.add_no_overlap([use.interval for use in uses])
                continue
            spec = rooms[room_id]
            cumulative_intervals = [entry.interval for entry in uses]
            cumulative_demands: list[int | cp_model.IntVar] = [
                spec.capacity if entry.exclusive else entry.persons for entry in uses
            ]
            if spec.windows:
                windows = sorted(
                    (window.start, window.end)
                    for window in spec.windows if window.weekday == weekday
                )
                cursor = day_start
                unavailable: list[tuple[int, int]] = []
                for opening, closing in windows:
                    if cursor < opening:
                        unavailable.append((cursor, opening))
                    cursor = closing
                if cursor < day_end:
                    unavailable.append((cursor, day_end))
                for index, (opening, closing) in enumerate(unavailable):
                    fixed = model.new_fixed_size_interval_var(
                        opening // 15, (closing - opening) // 15,
                        f"room_closed_{room_id}_{weekday}_{index}",
                    )
                    cumulative_intervals.append(fixed)
                    cumulative_demands.append(spec.capacity)
            model.add_cumulative(
                cumulative_intervals, cumulative_demands, spec.capacity
            )
