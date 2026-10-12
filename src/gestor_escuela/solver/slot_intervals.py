"""Overlap relations between school timetable slots.

Unknown legacy time ranges intentionally imply no overlap with *different*
slot IDs: never infer times from the slot label or display order.
"""

from __future__ import annotations

from collections.abc import Iterable


def build_slot_conflicts(
    slots: Iterable[tuple[str, str | None, str | None]],
) -> dict[str, frozenset[str]]:
    intervals: dict[str, tuple[int, int]] = {}
    slot_ids: set[str] = set()
    for slot_id, start_time, end_time in slots:
        slot_ids.add(slot_id)
        if start_time is None or end_time is None:
            continue
        start_h, start_m = (int(piece) for piece in start_time.split(":"))
        end_h, end_m = (int(piece) for piece in end_time.split(":"))
        intervals[slot_id] = (start_h * 60 + start_m, end_h * 60 + end_m)

    result: dict[str, frozenset[str]] = {}
    for slot_id in slot_ids:
        related = {slot_id}
        if slot_id in intervals:
            a_start, a_end = intervals[slot_id]
            for other_id, (b_start, b_end) in intervals.items():
                if a_start < b_end and b_start < a_end:
                    related.add(other_id)
        result[slot_id] = frozenset(related)
    return result
