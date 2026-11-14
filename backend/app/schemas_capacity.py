from __future__ import annotations

from datetime import datetime
from pydantic import AwareDatetime, BaseModel, Field


class CapacityTaskInput(BaseModel):
    id: str
    title: str
    effort_min: int = Field(ge=5, le=600)
    deadline: AwareDatetime
    priority_score: float = Field(default=0, ge=0, le=100)
    flexible: bool = True


class CapacityCheckRequest(BaseModel):
    tasks: list[CapacityTaskInput] = Field(default_factory=list)
    free_minutes_until: dict[AwareDatetime, int] = Field(default_factory=dict)

