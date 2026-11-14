from __future__ import annotations
from typing import Optional


from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, model_validator


class PlanBlockCreate(BaseModel):
    task_id: UUID
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class PlanBlockPatch(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: Optional[Literal['planned', 'done', 'missed', 'moved']] = None

