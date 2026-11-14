from __future__ import annotations
from typing import Optional


from datetime import datetime
from uuid import UUID

import dateparser
from pydantic import AwareDatetime, BaseModel, Field, field_validator


class CreateTaskCall(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    deadline_iso: Optional[AwareDatetime] = None
    deadline_phrase: Optional[str] = None
    effort_min: Optional[int] = Field(default=None, ge=5, le=600)
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    category: str = "other"
    depends_on: list[UUID] = Field(default_factory=list)
    recurrence_rrule: Optional[str] = None
    confidence: str = "high"
    missing_fields: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value


class ToolCall(BaseModel):
    name: str
    arguments: dict


def validate_create_task(call: CreateTaskCall, *, now: datetime, timezone: str) -> Optional[str]:
    if call.confidence == "low" or call.missing_fields:
        return "Please clarify the missing task details."
    if bool(call.deadline_phrase) != bool(call.deadline_iso):
        return 'Please confirm both the deadline date and the words describing it.'
    if call.deadline_phrase and call.deadline_iso:
        reparsed = dateparser.parse(call.deadline_phrase, settings={
            "RELATIVE_BASE": now,
            "TIMEZONE": timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
        })
        if reparsed is None:
            return 'I could not verify that deadline phrase. Which date and time do you mean?'
        if abs((reparsed - call.deadline_iso).total_seconds()) > 3600:
            return f"Did you mean {call.deadline_iso.isoformat()}?"
    if call.deadline_iso and call.deadline_iso < now:
        return "That deadline is in the past. What future date should I use?"
    return None

