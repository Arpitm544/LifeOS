from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class CompletedTask:
    category: str
    estimated_min: int
    actual_min: int
    completed_hour: int


@dataclass(frozen=True)
class ActivitySummary:
    calibration_factors: dict[str, float]
    focus_windows: list[tuple[int, int]]
    plan_adherence: float
    overdue_rates: dict[str, float]
    snooze_rates: dict[str, float]
    cold_start: bool


def compute_insights(*, completed: list[CompletedTask], planned_blocks: int,
                     completed_blocks: int, overdue_by_category: dict[str, tuple[int, int]],
                     snoozes_by_category: dict[str, tuple[int, int]]) -> ActivitySummary:
    by_category: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[int, list[int]] = defaultdict(list)
    for item in completed:
        if item.estimated_min <= 0 or item.actual_min < 0:
            continue
        by_category[item.category].append(item.actual_min / item.estimated_min)
        by_hour[item.completed_hour].append(1)
    factors = {category: round(max(0.5, min(3.0, median(values[-20:]))), 2)
               if len(completed) >= 10 else 1.0 for category, values in by_category.items()}
    productive_hours = sorted(range(23),
        key=lambda hour: -(len(by_hour[hour]) + len(by_hour[hour + 1])))
    windows = []
    for hour in productive_hours:
        if (by_hour[hour] or by_hour[hour + 1]) and all(hour + 2 <= a or hour >= b for a, b in windows):
            windows.append((hour, hour + 2))
            if len(windows) == 2:
                break
    overdue_rates = {category: round(count / max(total, 1), 2) for category, (count, total) in overdue_by_category.items()}
    snooze_rates = {category: round(count / max(total, 1), 2) for category, (count, total) in snoozes_by_category.items()}
    return ActivitySummary(factors, windows, round(completed_blocks / max(planned_blocks, 1), 2), overdue_rates, snooze_rates, len(completed) < 10)

