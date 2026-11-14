"""Schemas for every LLM tool call (PRD 4.2 / Appendix C) and deterministic checks."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

import dateparser
from ..schemas import Category
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


Confidence = Literal['high', 'medium', 'low']


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra='ignore')
    confidence: Confidence = 'high'
    missing_fields: list[str] = Field(default_factory=list)


class CreateTaskCall(ToolArgs):
    title: str = Field(min_length=1, max_length=120, pattern=r"\S")
    deadline_iso: Optional[AwareDatetime] = None
    deadline_phrase: Optional[str] = Field(default=None, max_length=120)
    effort_min: Optional[int] = Field(default=None, ge=5, le=600)
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    category: Category = Category.other
    depends_on: list[UUID] = Field(default_factory=list)
    recurrence_rrule: Optional[str] = Field(default=None, max_length=512)
    remind_at_iso: Optional[AwareDatetime] = Field(default=None, description='Exact reminder time the user asked for')
    remind_at_phrase: Optional[str] = Field(default=None, max_length=120)

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value


class TaskRefArgs(ToolArgs):
    task_id: Optional[UUID] = Field(default=None, description='Id from the open task list, when known')
    task_ref: Optional[str] = Field(default=None, max_length=120, description="The user's words for the task, e.g. 'the report' or 'it'")


class UpdateTaskCall(TaskRefArgs):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=r"\S")
    deadline_iso: Optional[AwareDatetime] = None
    deadline_phrase: Optional[str] = Field(default=None, max_length=120)
    effort_min: Optional[int] = Field(default=None, ge=5, le=600)
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    category: Optional[Category] = None
    pinned: Optional[bool] = None
    remind_at_iso: Optional[AwareDatetime] = None
    remind_at_phrase: Optional[str] = Field(default=None, max_length=120)


class CompleteTaskCall(TaskRefArgs):
    actual_effort_min: Optional[int] = Field(default=None, ge=0, le=1440)


class DeleteTaskCall(TaskRefArgs):
    pass


class CreateEventCall(ToolArgs):
    title: str = Field(min_length=1, max_length=120, pattern=r"\S")
    start_iso: AwareDatetime
    start_phrase: Optional[str] = Field(default=None, max_length=120)
    end_iso: Optional[AwareDatetime] = None
    duration_min: Optional[int] = Field(default=None, ge=5, le=1440)
    location: Optional[str] = Field(default=None, max_length=200)
    recurrence_rrule: Optional[str] = Field(default=None, max_length=512)


class QueryScheduleCall(ToolArgs):
    range_start_iso: Optional[AwareDatetime] = None
    range_end_iso: Optional[AwareDatetime] = None
    filter: Literal['due', 'free', 'plan', 'next', 'all'] = 'all'


class PlanDayCall(ToolArgs):
    date: Optional[str] = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$', description='Local date YYYY-MM-DD; default today')
    not_after: Optional[str] = Field(default=None, pattern=r'^\d{2}:\d{2}$', description="Local HH:MM the user stops for the day, e.g. 'leaving at 5' -> 17:00")


class CheckCapacityCall(ToolArgs):
    title: str = Field(min_length=1, max_length=120)
    effort_min: int = Field(ge=5, le=1440)
    deadline_iso: AwareDatetime
    deadline_phrase: Optional[str] = Field(default=None, max_length=120)


class SetPreferenceCall(ToolArgs):
    key: Literal['work_hours', 'quiet_hours', 'focus_windows', 'reminder_lead', 'timezone', 'estimate_padding']
    value: dict = Field(description="work_hours/quiet_hours: {start:'HH:MM', end:'HH:MM'}; focus_windows: {windows:[['HH:MM','HH:MM']]}; reminder_lead: {minutes:int}; timezone: {name}; estimate_padding: {enabled:bool}")


TOOL_SCHEMAS: dict[str, type[ToolArgs]] = {
    'create_task': CreateTaskCall,
    'update_task': UpdateTaskCall,
    'complete_task': CompleteTaskCall,
    'delete_task': DeleteTaskCall,
    'create_event': CreateEventCall,
    'query_schedule': QueryScheduleCall,
    'plan_day': PlanDayCall,
    'check_capacity': CheckCapacityCall,
    'set_preference': SetPreferenceCall,
}

TOOL_DESCRIPTIONS = {
    'create_task': 'Create one task the user must do. One call per task.',
    'update_task': 'Change an existing task (deadline, effort, title, importance, pin, reminder time).',
    'complete_task': 'Mark an existing task done.',
    'delete_task': 'Delete (drop) an existing task. Needs user confirmation.',
    'create_event': 'Create a fixed calendar event with a start time.',
    'query_schedule': "Answer questions such as what's due, what's next or whether the user is free.",
    'plan_day': 'Build a time-blocked plan for a day, optionally stopping at a time.',
    'check_capacity': "Hypothetical check: can a new piece of work fit before its deadline? Never saves.",
    'set_preference': 'Store a lasting preference the user states (working hours, quiet hours, focus time...).',
}

WRITE_TOOLS = {'create_task', 'update_task', 'complete_task', 'delete_task', 'create_event', 'set_preference', 'plan_day'}


class ToolCall(BaseModel):
    name: str
    arguments: dict


def tool_definitions() -> list[dict]:
    definitions = []
    for name, model in TOOL_SCHEMAS.items():
        schema = model.model_json_schema()
        schema.pop('title', None)
        definitions.append({'name': name, 'description': TOOL_DESCRIPTIONS[name], 'input_schema': schema})
    return definitions


def check_phrase(iso: Optional[datetime], phrase: Optional[str], *, now: datetime, timezone: str) -> Optional[str]:
    """Dual date parse: the LLM's ISO value must agree with dateparser within 1 h."""
    if not phrase or iso is None:
        return None
    import re
    from zoneinfo import ZoneInfo
    cleaned = re.sub(r'^(?:by|before|on|at|until|due|for|no later than)\s+', '', phrase.strip(), flags=re.IGNORECASE)
    has_clock = re.search(r'\b(\d{1,2}(:\d{2})?\s*(am|pm)|\d{1,2}:\d{2}|noon|midnight)\b', cleaned, re.IGNORECASE)
    if not has_clock:
        # "by Friday", "Friday evening": only the calendar date can be cross-checked;
        # the time comes from rules (23:59 default) or the part of day.
        cleaned = re.sub(r'\btonight\b', 'today', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(morning|afternoon|evening|night|eod|end of (the )?day)\b', '', cleaned, flags=re.IGNORECASE).strip() or 'today'
    reparsed = None
    for candidate in dict.fromkeys([cleaned, phrase]):
        reparsed = dateparser.parse(candidate, settings={
            "RELATIVE_BASE": now,
            "TIMEZONE": timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        })
        if reparsed is not None:
            break
    if reparsed is None:
        return 'I could not verify that date. Which date and time do you mean?'
    if not has_clock:
        zone = ZoneInfo(timezone)
        if reparsed.astimezone(zone).date() != iso.astimezone(zone).date():
            return f"Did you mean {format_local(iso, timezone)} or {reparsed.astimezone(zone).strftime('%a %d %b')}?"
        return None
    if abs((reparsed - iso).total_seconds()) > 3600:
        return f"Did you mean {format_local(iso, timezone)} or {format_local(reparsed, timezone)}?"
    return None


def format_local(moment: datetime, timezone: str) -> str:
    from zoneinfo import ZoneInfo
    local = moment.astimezone(ZoneInfo(timezone))
    return local.strftime('%a %d %b %H:%M')


# Phrase shapes dateparser reads reliably ("in 5 minutes", "6 pm", "18:30").
_RELIABLE_REMINDER = re.compile(r'\bin\s+(\d+|a|an|one|two|three|four|five|ten|fifteen|twenty|thirty)\s+(minute|min|hour|day)s?\b'
                                r'|\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b', re.IGNORECASE)


def validate_deadline(iso: Optional[datetime], phrase: Optional[str], *, now: datetime, timezone: str) -> Optional[str]:
    """PRD F1 step 3: the LLM must return both the ISO value and the user's words."""
    if bool(phrase) != bool(iso):
        return 'Please confirm both the deadline date and the words describing it.'
    problem = check_phrase(iso, phrase, now=now, timezone=timezone)
    if problem:
        return problem
    if iso and iso < now:
        return "That deadline is in the past. What future date should I use?"
    return None


def validate_reminder(iso: Optional[datetime], phrase: Optional[str], *, now: datetime, timezone: str) -> Optional[str]:
    """A reminder needs an exact time; the pair is cross-checked where parsing is reliable."""
    if phrase and iso is None:
        return 'When exactly should I remind you?'
    if iso is None:
        return None
    if iso < now:
        return "That reminder time has passed. When should I remind you?"
    if phrase and _RELIABLE_REMINDER.search(phrase):
        return check_phrase(iso, phrase, now=now, timezone=timezone)
    return None  # e.g. "at 6": the reply and card show the exact time instead


def validate_create_task(call: CreateTaskCall, *, now: datetime, timezone: str) -> Optional[str]:
    if call.confidence == "low" or call.missing_fields:
        return "Please clarify the missing task details."
    return (validate_deadline(call.deadline_iso, call.deadline_phrase, now=now, timezone=timezone)
            or validate_reminder(call.remind_at_iso, call.remind_at_phrase, now=now, timezone=timezone))
