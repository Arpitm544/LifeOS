from __future__ import annotations
from typing import Optional


from datetime import datetime, timedelta


def move_out_of_quiet_hours(moment: datetime, *, quiet_start: tuple[int, int] = (22, 30), quiet_end: tuple[int, int] = (7, 30), deadline: Optional[datetime] = None) -> datetime:
    start = moment.replace(hour=quiet_start[0], minute=quiet_start[1], second=0, microsecond=0)
    end = moment.replace(hour=quiet_end[0], minute=quiet_end[1], second=0, microsecond=0)
    if quiet_start > quiet_end:
        if moment < end:
            start -= timedelta(days=1)
        else:
            end += timedelta(days=1)
    if start <= moment < end:
        if deadline and deadline <= end:
            return start
        return end
    return moment


def task_reminder_times(*, deadline: datetime, effort_min: int, now: datetime,
                        buffer_min: int = 60) -> list[tuple[str, datetime]]:
    return [("start_now", deadline - timedelta(minutes=effort_min + buffer_min)),
            ("due_soon", deadline - timedelta(hours=2)),
            ("overdue", deadline + timedelta(minutes=15))]


def event_reminder_time(*, start: datetime, location: Optional[str] = None) -> datetime:
    return start - timedelta(minutes=45 if location else 15)

