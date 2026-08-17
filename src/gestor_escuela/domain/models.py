from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class ActivityType(StrEnum):
    CLASS = "CLASS"
    SUPPORT = "SUPPORT"
    PT = "PT"
    AL = "AL"
    COORDINATION = "COORDINATION"
    RECESS = "RECESS"


class Priority(IntEnum):
    CANCELABLE = 10
    FLEXIBLE = 20
    NORMAL = 30
    HIGH = 40
    CRITICAL = 50


class TeacherProfile(StrEnum):
    TUTOR = "TUTOR"
    SPECIALIST = "SPECIALIST"
    PT = "PT"
    AL = "AL"
    SUPPORT = "SUPPORT"
    MANAGEMENT = "MANAGEMENT"


class CandidateStatus(StrEnum):
    SELECTED = "SELECTED"
    VALID_ALTERNATIVE = "VALID_ALTERNATIVE"
    REJECTED = "REJECTED"


class CandidateRejectionReason(StrEnum):
    ABSENT_TEACHER = "ABSENT_TEACHER"
    ABSENT_IN_SLOT = "ABSENT_IN_SLOT"
    INCOMPATIBLE_GROUP = "INCOMPATIBLE_GROUP"
    MISSING_SPECIALTY = "MISSING_SPECIALTY"
    IMMOVABLE_ACTIVITY = "IMMOVABLE_ACTIVITY"
    GLOBAL_CONFLICT = "GLOBAL_CONFLICT"


@dataclass(frozen=True, slots=True)
class TimeSlot:
    id: str
    label: str
    order: int


@dataclass(frozen=True, slots=True)
class Teacher:
    id: str
    profile: TeacherProfile
    substitution_count: int = 0
    can_cover_groups: frozenset[str] = field(default_factory=frozenset)
    emergency_only: bool = False
    substitutions_last_7_days: int = 0
    substitutions_last_30_days: int = 0
    specialties: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Group:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class Activity:
    id: str
    slot_id: str
    activity_type: ActivityType
    teacher_id: str
    group_id: str | None = None
    priority: Priority = Priority.NORMAL
    movable: bool = False
    cancelable: bool = False
    required_specialty: str | None = None

    @property
    def requires_group_coverage(self) -> bool:
        return self.group_id is not None and self.activity_type == ActivityType.CLASS


@dataclass(frozen=True, slots=True)
class Absence:
    teacher_id: str
    slot_ids: frozenset[str]

    def affects(self, slot_id: str) -> bool:
        return slot_id in self.slot_ids


@dataclass(frozen=True, slots=True)
class LockedSubstitution:
    """Manual substitution decision that must survive solver recalculation."""

    activity_id: str
    substitute_teacher_id: str


@dataclass(frozen=True, slots=True)
class Substitution:
    activity_id: str
    slot_id: str
    group_id: str
    absent_teacher_id: str
    substitute_teacher_id: str
    displaced_activity_id: str | None
    penalty: int


@dataclass(frozen=True, slots=True)
class CandidatePenaltyBreakdown:
    historical_total: int = 0
    recent_7_days: int = 0
    recent_30_days: int = 0
    emergency: int = 0
    displacement: int = 0

    @property
    def total(self) -> int:
        return (
            self.historical_total
            + self.recent_7_days
            + self.recent_30_days
            + self.emergency
            + self.displacement
        )


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    activity_id: str
    slot_id: str
    group_id: str
    teacher_id: str
    status: CandidateStatus
    penalty: int | None = None
    penalty_breakdown: CandidatePenaltyBreakdown | None = None
    displaced_activity_id: str | None = None
    rejection_reason: CandidateRejectionReason | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class UncoveredActivity:
    activity_id: str
    slot_id: str
    group_id: str
    absent_teacher_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class SolverWeights:
    uncovered: int = 100_000
    displacement_flexible: int = 120
    displacement_normal: int = 800
    displacement_high: int = 5_000
    substitution_history: int = 30
    recent_substitution_7_days: int = 120
    recent_substitution_30_days: int = 30
    emergency_teacher: int = 2_000
    pt_al_displacement_multiplier: int = 5


@dataclass(frozen=True, slots=True)
class SolverSolution:
    substitutions: tuple[Substitution, ...]
    uncovered: tuple[UncoveredActivity, ...]
    total_penalty: int
    objective_bound: float
    wall_time_seconds: float
    candidate_assessments: tuple[CandidateAssessment, ...] = ()

    @property
    def coverage_ratio(self) -> float:
        total = len(self.substitutions) + len(self.uncovered)
        return 1.0 if total == 0 else len(self.substitutions) / total

    @property
    def score(self) -> int:
        if self.uncovered:
            return max(0, round(100 * self.coverage_ratio) - min(20, len(self.uncovered) * 5))
        impact = min(20, self.total_penalty // 500)
        return max(0, 100 - impact)
