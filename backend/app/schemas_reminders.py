from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class ReminderAction(str, Enum):
    done = "done"
    snooze_15 = "snooze_15"
    snooze_60 = "snooze_60"
    reschedule = "reschedule"


class ReminderActionRequest(BaseModel):
    action: ReminderAction


class ReminderPreviewRequest(BaseModel):
    deadline: datetime
    effort_min: int
    now: datetime

