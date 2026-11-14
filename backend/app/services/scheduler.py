from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class BusyBlock:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SchedulableTask:
    id: str
    effort_min: int
    deadline: datetime
    priority_score: float
    blocked: bool = False


@dataclass(frozen=True)
class PlanBlock:
    task_id: str
    start: datetime
    end: datetime


def build_free_slots(*, window_start: datetime, window_end: datetime,
                     working_hours: list[tuple[int, int]], busy: list[BusyBlock],
                     buffer_min: int = 10, minimum_slot_min: int = 25) -> list[BusyBlock]:
    slots: list[BusyBlock] = []
    cursor_day = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor_day < window_end:
        for start_hour, end_hour in working_hours:
            if not (0 <= start_hour <= 23 and 1 <= end_hour <= 24 and start_hour < end_hour):
                raise ValueError('working hours must be whole-hour ranges within one day')
            start = max(cursor_day.replace(hour=start_hour), window_start)
            end_base = cursor_day + timedelta(days=1) if end_hour == 24 else cursor_day.replace(hour=end_hour)
            end = min(end_base, window_end)
            if end <= start:
                continue
            fragments = [BusyBlock(start, end)]
            for event in busy:
                blocked = BusyBlock(event.start - timedelta(minutes=buffer_min), event.end + timedelta(minutes=buffer_min))
                next_fragments: list[BusyBlock] = []
                for fragment in fragments:
                    if blocked.end <= fragment.start or blocked.start >= fragment.end:
                        next_fragments.append(fragment)
                        continue
                    if fragment.start < blocked.start:
                        next_fragments.append(BusyBlock(fragment.start, min(blocked.start, fragment.end)))
                    if blocked.end < fragment.end:
                        next_fragments.append(BusyBlock(max(blocked.end, fragment.start), fragment.end))
                fragments = next_fragments
            slots.extend(fragment for fragment in fragments if (fragment.end - fragment.start).total_seconds() >= minimum_slot_min * 60)
        cursor_day += timedelta(days=1)
    return sorted(slots, key=lambda slot: slot.start)


def generate_plan(*, tasks: list[SchedulableTask], slots: list[BusyBlock], chunk_min: int = 90) -> tuple[list[PlanBlock], list[SchedulableTask]]:
    remaining = {task.id: task.effort_min for task in tasks if not task.blocked}
    ordered = sorted((task for task in tasks if not task.blocked), key=lambda task: (-task.priority_score, task.deadline))
    blocks: list[PlanBlock] = []
    # Consume one shared free-slot list across all tasks.
    available_slots = list(slots)
    for task in ordered:
        next_slots = []
        for slot in available_slots:
            if remaining[task.id] <= 0:
                next_slots.append(slot)
                continue
            cursor = slot.start
            while cursor < slot.end and remaining[task.id] > 0:
                available_min = int((slot.end - cursor).total_seconds() / 60)
                chunk = min(chunk_min, remaining[task.id], available_min)
                if chunk < 25 and remaining[task.id] >= 25:
                    break
                end = cursor + timedelta(minutes=chunk)
                end = min(end, task.deadline)
                if end <= cursor:
                    break
                blocks.append(PlanBlock(task.id, cursor, end))
                remaining[task.id] -= int((end - cursor).total_seconds() / 60)
                cursor = end
            if cursor < slot.end:
                next_slots.append(BusyBlock(cursor, slot.end))
        available_slots = next_slots
        
    unplaced = [task for task in tasks if remaining.get(task.id, 0) > 0 or task.blocked]
    blocks.sort(key=lambda block: block.start)
    return blocks, unplaced

