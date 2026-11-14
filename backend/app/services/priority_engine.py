from __future__ import annotations
from typing import Optional

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class PriorityResult:
    score: float
    band: str
    urgency: float
    importance: float
    blocking: float
    staleness: float
    why: str

def calculate_priority(*, now: datetime, deadline: Optional[datetime], effort_min: int,
                       importance: int, blocking_count: int, created_at: datetime,
                       free_working_hours: float) -> PriorityResult:
    if deadline is None:
        urgency = 0.0
    elif deadline <= now:
        urgency = 1.0
    else:
        slack = free_working_hours - effort_min / 60
        urgency = 1.0 if slack <= 0 else max(0.0, 1.0 - slack / 40)
    importance_term = (importance - 1) / 4
    blocking = min(1.0, blocking_count / 3)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400)
    staleness = min(1.0, age_days / 14)
    score = round(100 * (0.45 * urgency + 0.30 * importance_term + 0.15 * blocking + 0.10 * staleness), 2)
    band = "P1" if score >= 70 else "P2" if score >= 40 else "P3"
    if deadline and deadline <= now:
        why = "Overdue"
    elif deadline:
        hours = max(0, (deadline - now).total_seconds() / 3600)
        why = f"Due in {hours:.0f} h, needs {effort_min / 60:g} h"
    elif blocking_count:
        why = f"Blocks {blocking_count} task{'s' if blocking_count != 1 else ''}"
    else:
        why = "Importance and age"
    return PriorityResult(score, band, urgency, importance_term, blocking, staleness, why)

