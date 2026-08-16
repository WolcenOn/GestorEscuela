from __future__ import annotations

from gestor_escuela.domain.models import (
    Absence,
    Activity,
    ActivityType,
    Group,
    Priority,
    Teacher,
    TeacherProfile,
    TimeSlot,
)


def build_pilot_dataset() -> tuple[
    tuple[Teacher, ...], tuple[Group, ...], tuple[TimeSlot, ...], tuple[Activity, ...]
]:
    groups = tuple(Group(f"G{i}", f"{i}.º") for i in range(1, 7))
    group_ids = frozenset(group.id for group in groups)
    slots = tuple(
        TimeSlot(f"S{i}", label, i)
        for i, label in enumerate(
            ("09:00", "09:45", "10:30", "11:45", "12:30", "13:15"), start=1
        )
    )

    teachers = (
        Teacher("P01", TeacherProfile.TUTOR, 1, frozenset({"G1"})),
        Teacher("P02", TeacherProfile.TUTOR, 3, frozenset({"G2"})),
        Teacher("P03", TeacherProfile.TUTOR, 2, frozenset({"G3"})),
        Teacher("P04", TeacherProfile.TUTOR, 4, frozenset({"G4"})),
        Teacher("P05", TeacherProfile.TUTOR, 1, frozenset({"G5"})),
        Teacher("P06", TeacherProfile.TUTOR, 2, frozenset({"G6"})),
        Teacher("P07", TeacherProfile.PT, 0, group_ids),
        Teacher("P08", TeacherProfile.AL, 1, group_ids),
        Teacher("P09", TeacherProfile.SPECIALIST, 2, group_ids),
        Teacher("P10", TeacherProfile.SUPPORT, 1, group_ids),
        Teacher("P11", TeacherProfile.SPECIALIST, 3, group_ids),
        Teacher("P12", TeacherProfile.MANAGEMENT, 0, group_ids, emergency_only=True),
    )

    activities: list[Activity] = []
    for slot in slots:
        for index in range(1, 7):
            activities.append(
                Activity(
                    id=f"A-{slot.id}-G{index}",
                    slot_id=slot.id,
                    activity_type=ActivityType.CLASS,
                    teacher_id=f"P0{index}",
                    group_id=f"G{index}",
                    priority=Priority.CRITICAL,
                )
            )

    flexible_plan = {
        "P07": (ActivityType.PT, Priority.HIGH, False),
        "P08": (ActivityType.AL, Priority.HIGH, False),
        "P09": (ActivityType.COORDINATION, Priority.FLEXIBLE, True),
        "P10": (ActivityType.SUPPORT, Priority.FLEXIBLE, True),
        "P11": (ActivityType.SUPPORT, Priority.NORMAL, True),
        "P12": (ActivityType.COORDINATION, Priority.FLEXIBLE, True),
    }
    for slot in slots:
        for teacher_id, (kind, priority, cancelable) in flexible_plan.items():
            actual_priority = priority
            actual_cancelable = cancelable
            if teacher_id in {"P07", "P08"} and slot.id in {"S3", "S6"}:
                actual_priority = Priority.FLEXIBLE
                actual_cancelable = True
            activities.append(
                Activity(
                    id=f"A-{slot.id}-{teacher_id}",
                    slot_id=slot.id,
                    activity_type=kind,
                    teacher_id=teacher_id,
                    priority=actual_priority,
                    movable=actual_cancelable,
                    cancelable=actual_cancelable,
                )
            )

    return teachers, groups, slots, tuple(activities)


def demo_absences() -> tuple[Absence, ...]:
    return (
        Absence("P02", frozenset({"S1", "S2", "S3", "S4", "S5", "S6"})),
        Absence("P04", frozenset({"S1", "S2", "S3", "S4", "S5", "S6"})),
        Absence("P08", frozenset({"S1", "S2", "S3"})),
    )
