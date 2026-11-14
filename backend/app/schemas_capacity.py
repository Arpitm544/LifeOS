from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field


class CapacityTaskInput(BaseModel):
    id: str
    title: str
    effort_min: int = Field(ge=5, le=600)
    deadline: AwareDatetime
    priority_score: float = Field(default=0, ge=0, le=100)
    flexible: bool = True


class HypotheticalTask(BaseModel):
    """"Can I take a 6-hour job due Friday?" checked against the user's real data."""
    title: str = Field(default='New work', min_length=1, max_length=120)
    effort_min: int = Field(ge=5, le=1440)
    deadline: AwareDatetime
    category: str = Field(default='other', pattern='^(study|work|errand|health|social|finance|home|other)$')


class CapacityCheckRequest(BaseModel):
    tasks: list[CapacityTaskInput] = Field(default_factory=list)
    free_minutes_until: dict[AwareDatetime, int] = Field(default_factory=dict)
    hypothetical: Optional[HypotheticalTask] = None

