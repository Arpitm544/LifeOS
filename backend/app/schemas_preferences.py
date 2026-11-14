from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional
from .services.preference_values import validate_preference
from datetime import date, datetime, timezone
import re
from dateutil.rrule import rrulestr


class PreferenceUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    key: str = Field(min_length=1, max_length=80)
    value: dict
    source: Literal['stated', 'inferred', 'default'] = "stated"
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: Literal['active', 'suggested'] = "active"

    @model_validator(mode='after')
    def validate_value(self):
        try:
            validate_preference(self.key, self.value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Invalid preference value: ' + str(exc)) from exc
        if self.source == 'inferred' and (self.status != 'suggested' or self.confidence >= 1):
            raise ValueError('Inferred preferences require acceptance and confidence below one')
        return self


class RoutineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    rrule: str = Field(min_length=1, max_length=512)
    start_time: str
    duration_min: int = Field(ge=5, le=600)
    movable: bool = True
    anchor_date: Optional[date] = None

    @field_validator('start_time')
    @classmethod
    def valid_time(cls, value):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
            raise ValueError('start_time must use HH:MM in 24-hour local time')
        return value

    @field_validator('rrule')
    @classmethod
    def valid_rrule(cls, value):
        # Store a single rule; expanding instances belongs to the scheduling step.
        if '\n' in value or '\r' in value:
            raise ValueError('Provide one RFC 5545 RRULE string')
        rule = value.removeprefix('RRULE:')
        parts = dict(part.split('=', 1) for part in rule.split(';') if '=' in part)
        if parts.get('FREQ') not in {'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'}:
            raise ValueError('Use daily, weekly, monthly or yearly recurrence')
        try:
            if any(int(parts[key]) <= 0 for key in ('COUNT', 'INTERVAL') if key in parts):
                raise ValueError('COUNT and INTERVAL must be positive')
            if 'COUNT' in parts and 'UNTIL' in parts:
                raise ValueError('COUNT and UNTIL cannot be combined')
            rrulestr(rule, dtstart=datetime(2026, 1, 1, tzinfo=timezone.utc))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError('Invalid RFC 5545 recurrence rule') from exc
        return rule

