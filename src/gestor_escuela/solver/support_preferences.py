"""Soft subject-extraction preferences for PT/AL in CP-SAT.

Hard prohibitions live in the timetable constraints. These terms optimize
preferred/avoided overlaps but NEVER make a hard-infeasible case feasible.
"""

from __future__ import annotations

from collections.abc import MutableSequence

from ortools.sat.python import cp_model

ClassEvents = dict[
    tuple[str, str, int],
    list[tuple[cp_model.IntVar, int, cp_model.IntVar]],
]


def add_extraction_preferences(
    model: cp_model.CpModel,
    start: cp_model.IntVar,
    end: cp_model.LinearExpr,
    active: cp_model.IntVar,
    group_id: str,
    weekday: int,
    avoided: tuple[str, ...],
    preferred: tuple[str, ...],
    events: ClassEvents,
    objective: MutableSequence[cp_model.LinearExpr],
    prefix: str,
) -> None:
    """Use 15-min ticks; minimize avoid penalties, reward preferred overlap."""
    for subject in avoided:
        for index, (class_start, duration, class_present) in enumerate(
            events.get((group_id, subject, weekday), ())
        ):
            left = model.new_bool_var(f"{prefix}_before_{subject}_{index}")
            right = model.new_bool_var(f"{prefix}_after_{subject}_{index}")
            penalty = model.new_bool_var(f"{prefix}_avoid_{subject}_{index}")
            model.add(end <= class_start).only_enforce_if(left)
            model.add(class_start + duration <= start).only_enforce_if(right)
            model.add_bool_or([active.Not(), class_present.Not(), left, right, penalty])
            objective.append(100 * penalty)

    for subject in preferred:
        for index, (class_start, duration, class_present) in enumerate(
            events.get((group_id, subject, weekday), ())
        ):
            reward = model.new_bool_var(f"{prefix}_prefer_{subject}_{index}")
            model.add_implication(reward, active)
            model.add_implication(reward, class_present)
            model.add(start < class_start + duration).only_enforce_if(reward)
            model.add(class_start < end).only_enforce_if(reward)
            objective.append(-20 * reward)
