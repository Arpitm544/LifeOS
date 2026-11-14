from __future__ import annotations
from typing import Optional

from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class Category(str, Enum):
    study = "study"
    work = "work"
    errand = "errand"
    health = "health"
    social = "social"
    finance = "finance"
    home = "home"
    other = "other"

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    deadline_at: Optional[AwareDatetime] = None
    effort_est_min: int = Field(default=30, ge=5, le=600)
    importance: int = Field(default=3, ge=1, le=5)
    category: Category = Category.other
    depends_on: list[UUID] = Field(default_factory=list)
    recurrence_rrule: Optional[str] = None

class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    deadline_at: Optional[datetime]
    effort_est_min: int
    importance: int
    category: str
    status: str
    priority_score: float
    priority_band: str
    pinned: bool

class TaskPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    deadline_at: Optional[AwareDatetime] = None
    effort_est_min: Optional[int] = Field(default=None, ge=5, le=600)
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    category: Optional[Category] = None
    pinned: Optional[bool] = None

    @field_validator('title', 'effort_est_min', 'importance', 'category', 'pinned')
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError('This field cannot be null')
        return value

class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="text", pattern="^(text|voice)$")
    client_tz: str = "UTC"

    @field_validator('client_tz')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('client_tz must be an IANA timezone') from exc
        return value

