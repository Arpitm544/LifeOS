from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ConflictCreate(BaseModel):
    deadline_at: datetime
    needed_min: int = Field(ge=0)
    free_min: int = Field(ge=0)
    task_ids: list[str] = Field(default_factory=list)
    options: list[dict] = Field(default_factory=list)


class ConflictResolve(BaseModel):
    option_type: str = Field(min_length=1, max_length=40)

