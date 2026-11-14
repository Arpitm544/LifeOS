from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class PlanTaskInput(BaseModel):
    id: str
    effort_min: int = Field(ge=5, le=600)
    deadline: datetime
    priority_score: float = Field(ge=0, le=100)
    blocked: bool = False


class BusyInput(BaseModel):
    start: datetime
    end: datetime


class PlanGenerateRequest(BaseModel):
    window_start: datetime
    window_end: datetime
    working_hours: list[tuple[int, int]] = [(9, 18)]
    busy: list[BusyInput] = Field(default_factory=list)
    tasks: list[PlanTaskInput] = Field(default_factory=list)

