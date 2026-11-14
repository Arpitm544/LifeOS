from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CapacityTask:
    id: str
    title: str
    effort_min: int
    deadline: datetime
    priority_score: float = 0
    flexible: bool = True


@dataclass(frozen=True)
class CapacityConflict:
    deadline: datetime
    needed_min: int
    free_min: int
    shortfall_min: int
    task_ids: list[str]
    options: list[dict]


def check_capacity(*, tasks: list[CapacityTask], free_minutes_until: dict[datetime, int]) -> list[CapacityConflict]:
    conflicts: list[CapacityConflict] = []
    # Missing supply cannot silently make tasks disappear from the check.
    for deadline in sorted(set(free_minutes_until) | {task.deadline for task in tasks}):
        due = [task for task in tasks if task.deadline <= deadline]
        needed = sum(task.effort_min for task in due)
        free = max(0, free_minutes_until.get(deadline, 0))
        if needed <= free:
            continue
        shortfall = needed - free
        flexible = sorted((task for task in due if task.flexible), key=lambda task: (task.priority_score, task.deadline))
        options = [
            {"type": "extend_hours", "additional_min": shortfall},
            {"type": "move_flexible", "task_id": flexible[0].id if flexible else None},
            {"type": "renegotiate", "task_id": min(due, key=lambda task: task.priority_score).id},
        ]
        conflicts.append(CapacityConflict(deadline, needed, free, shortfall, [task.id for task in due], options))
    return conflicts

