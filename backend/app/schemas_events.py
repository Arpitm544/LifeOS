from __future__ import annotations
from typing import Optional


from datetime import datetime
from pydantic import AwareDatetime, BaseModel, Field, model_validator


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_at: AwareDatetime
    end_at: AwareDatetime
    location: Optional[str] = None
    rrule: Optional[str] = None
    source: str = "manual"

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class EventRead(EventCreate):
    id: str


class EventPatch(BaseModel):
    model_config = {'extra': 'forbid'}
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    start_at: Optional[AwareDatetime] = None
    end_at: Optional[AwareDatetime] = None
    location: Optional[str] = None
    rrule: Optional[str] = None

