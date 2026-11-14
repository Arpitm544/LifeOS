"""Import events from an iCalendar (.ics) file, exported by Google Calendar, Apple Calendar, Outlook and others.

Parsing never writes: the caller shows the proposals for review first. Saving creates the chosen events as one
batch (one Undo) and skips events that were already imported, matched by the calendar's own UID.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

MAX_ICS_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 500
MAX_EVENT_LENGTH = timedelta(days=14)
PAST_GRACE = timedelta(days=1)
SOURCE = 'ics'

# Windows names that Outlook uses in TZID, mapped to IANA names.
WINDOWS_ZONES = {
    'Eastern Standard Time': 'America/New_York', 'Central Standard Time': 'America/Chicago',
    'Mountain Standard Time': 'America/Denver', 'Pacific Standard Time': 'America/Los_Angeles',
    'GMT Standard Time': 'Europe/London', 'W. Europe Standard Time': 'Europe/Berlin',
    'Romance Standard Time': 'Europe/Paris', 'India Standard Time': 'Asia/Kolkata',
    'China Standard Time': 'Asia/Shanghai', 'Tokyo Standard Time': 'Asia/Tokyo',
    'AUS Eastern Standard Time': 'Australia/Sydney', 'UTC': 'UTC',
}


class IcsInputError(ValueError):
    """The uploaded file cannot be used; the message is safe to show the user."""


@dataclass
class Proposal:
    title: str
    start_at: datetime
    end_at: datetime
    location: Optional[str]
    rrule: Optional[str]
    external_id: str
    all_day: bool = False

    def as_dict(self) -> dict:
        return {'title': self.title, 'start_at': self.start_at.isoformat(), 'end_at': self.end_at.isoformat(),
                'location': self.location, 'rrule': self.rrule, 'external_id': self.external_id,
                'all_day': self.all_day}


def read_source(text: Optional[str]) -> str:
    if not text or not text.strip():
        raise IcsInputError('Choose an .ics calendar file first.')
    if len(text.encode('utf-8', errors='ignore')) > MAX_ICS_BYTES:
        raise IcsInputError('That calendar file is too large (limit 2 MB).')
    if 'BEGIN:VCALENDAR' not in text.upper():
        raise IcsInputError('That does not look like an .ics calendar file.')
    return text


def unfold(text: str) -> list[str]:
    """Join folded lines (a line starting with a space or tab continues the previous one)."""
    lines: list[str] = []
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if raw[:1] in (' ', '\t') and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def unescape(value: str) -> str:
    return re.sub(r'\\([nN,;\\])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), value)


def parse_line(line: str) -> tuple[str, dict[str, str], str]:
    """`NAME;PARAM=x:value` -> (NAME, {PARAM: x}, value). Colons inside quoted params are respected."""
    in_quote, split_at = False, -1
    for index, char in enumerate(line):
        if char == '"':
            in_quote = not in_quote
        elif char == ':' and not in_quote:
            split_at = index
            break
    if split_at < 0:
        return line.upper(), {}, ''
    head, value = line[:split_at], line[split_at + 1:]
    name, *params = head.split(';')
    parsed = {}
    for param in params:
        key, _, val = param.partition('=')
        parsed[key.upper()] = val.strip('"')
    return name.upper(), parsed, value


def _zone(name: Optional[str], fallback: ZoneInfo) -> ZoneInfo:
    if not name:
        return fallback
    try:
        return ZoneInfo(WINDOWS_ZONES.get(name, name))
    except (ZoneInfoNotFoundError, ValueError):
        return fallback


def parse_when(value: str, params: dict[str, str], fallback: ZoneInfo) -> tuple[datetime | date, bool]:
    """Return (moment, is_all_day). Floating times use the user's zone."""
    value = value.strip()
    if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', value):
        return datetime.strptime(value[:8], '%Y%m%d').date(), True
    if value.endswith('Z'):
        return datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc), False
    naive = datetime.strptime(value, '%Y%m%dT%H%M%S')
    return naive.replace(tzinfo=_zone(params.get('TZID'), fallback)), False


def parse_duration(value: str) -> Optional[timedelta]:
    match = re.fullmatch(r'([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', value.strip())
    if not match:
        return None
    sign, weeks, days, hours, minutes, seconds = match.groups()
    total = timedelta(weeks=int(weeks or 0), days=int(days or 0), hours=int(hours or 0),
                      minutes=int(minutes or 0), seconds=int(seconds or 0))
    return -total if sign == '-' else total


def _components(lines: list[str]) -> list[list[tuple[str, dict[str, str], str]]]:
    events, current, depth = [], None, 0
    for line in lines:
        name, params, value = parse_line(line)
        if name == 'BEGIN' and value.upper() == 'VEVENT':
            current, depth = [], 0
        elif name == 'BEGIN' and current is not None:
            depth += 1  # nested VALARM etc.: ignore its properties
        elif name == 'END' and value.upper() == 'VEVENT' and current is not None:
            events.append(current)
            current = None
        elif name == 'END' and current is not None:
            depth -= 1
        elif current is not None and depth == 0:
            current.append((name, params, value))
    return events


def _clean_rrule(value: str) -> Optional[str]:
    rule = value.strip()
    if not rule.upper().startswith('FREQ='):
        return None
    # A date-only UNTIL cannot be compared with a timed start; make it the end of that day in UTC.
    return re.sub(r'UNTIL=(\d{8})(?!T|\d)', r'UNTIL=\1T235959Z', rule, flags=re.I)


def _with_exdates(rule: str, exdates: list, start: datetime, all_day: bool, fallback: ZoneInfo) -> str:
    """Append skipped occurrences as EXDATE lines (UTC); the planner's rule parser understands them."""
    stamps: list[str] = []
    for params, value in exdates:
        for part in value.split(','):
            try:
                moment, is_date = parse_when(part, params, fallback)
            except ValueError:
                continue
            if is_date:  # a skipped day: the occurrence starts at this event's own local time that day
                local = start.astimezone(fallback)
                moment = datetime.combine(moment, local.timetz().replace(tzinfo=None), tzinfo=fallback)
            stamps.append(moment.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    text = rule
    for stamp in sorted(set(stamps)):
        line = f'\nEXDATE:{stamp}'
        if len(text) + len(line) > 512:  # the column limit; keep the rule valid rather than truncating
            break
        text += line
    return text


def parse_calendar(text: str, tz_name: str, now: datetime) -> dict:
    """Parse an .ics file into reviewable event proposals."""
    fallback = ZoneInfo(tz_name)
    proposals: list[Proposal] = []
    skipped = {'past': 0, 'cancelled': 0, 'invalid': 0, 'duplicate': 0}
    seen: set[str] = set()
    for props in _components(unfold(text)):
        fields: dict[str, tuple[dict[str, str], str]] = {}
        rules, exdates = [], []
        for name, params, value in props:
            if name == 'RRULE':
                rules.append(value)
            elif name == 'EXDATE':
                exdates.append((params, value))
            fields.setdefault(name, (params, value))
        if fields.get('STATUS', ({}, ''))[1].upper() == 'CANCELLED':
            skipped['cancelled'] += 1
            continue
        try:
            if 'DTSTART' not in fields:
                raise ValueError('no start')
            start, all_day = parse_when(fields['DTSTART'][1], fields['DTSTART'][0], fallback)
            if 'DTEND' in fields:
                end, _ = parse_when(fields['DTEND'][1], fields['DTEND'][0], fallback)
            elif 'DURATION' in fields and parse_duration(fields['DURATION'][1]):
                length = parse_duration(fields['DURATION'][1])
                end = start + length
            else:
                end = start + (timedelta(days=1) if all_day else timedelta())
            if all_day:
                # All-day events are busy for the whole local day(s).
                start = datetime.combine(start, time.min, tzinfo=fallback)
                end = datetime.combine(end, time.min, tzinfo=fallback) if isinstance(end, date) and not isinstance(end, datetime) else end
            if end <= start:
                raise ValueError('bad range')
            if end - start > MAX_EVENT_LENGTH:
                raise ValueError('too long')
        except (ValueError, KeyError, OverflowError):
            skipped['invalid'] += 1
            continue
        rrule = _clean_rrule(rules[0]) if rules else None
        if rules and rrule is None:
            skipped['invalid'] += 1
            continue
        if rrule:
            rrule = _with_exdates(rrule, exdates, start, all_day, fallback)
            # The planner expands this rule later, so reject any rule it could not expand.
            try:
                upcoming = next(iter(rrulestr(rrule, dtstart=start).xafter(now - PAST_GRACE, count=1, inc=True)), None)
            except (TypeError, ValueError, OverflowError):
                skipped['invalid'] += 1
                continue
            if upcoming is None:
                skipped['past'] += 1
                continue
        elif end < now - PAST_GRACE:
            skipped['past'] += 1
            continue
        title = unescape(fields.get('SUMMARY', ({}, ''))[1]).strip() or 'Busy'
        location = unescape(fields.get('LOCATION', ({}, ''))[1]).strip() or None
        uid = fields.get('UID', ({}, ''))[1].strip()
        recurrence_id = fields.get('RECURRENCE-ID', ({}, ''))[1].strip()
        external_id = (uid + ('|' + recurrence_id if recurrence_id else '')) if uid else f'{title}|{start.isoformat()}'
        external_id = external_id[:200]
        if external_id in seen:
            skipped['duplicate'] += 1
            continue
        seen.add(external_id)
        proposals.append(Proposal(title=title[:120], start_at=start.astimezone(timezone.utc),
                                  end_at=end.astimezone(timezone.utc), location=location[:200] if location else None,
                                  rrule=rrule[:512] if rrule else None, external_id=external_id, all_day=all_day))
    proposals.sort(key=lambda item: item.start_at)
    capped = len(proposals) > MAX_EVENTS
    return {'proposals': [item.as_dict() for item in proposals[:MAX_EVENTS]], 'capped': capped,
            'skipped_past': skipped['past'], 'skipped_cancelled': skipped['cancelled'],
            'skipped_invalid': skipped['invalid'], 'skipped_duplicate': skipped['duplicate']}


async def save_events(session, user_id, items: list) -> dict:
    """Create the reviewed events as one batch; events already imported (same UID) are skipped."""
    from sqlalchemy import select
    from ..models import Event
    from .domain_service import audit, lock_owner
    await lock_owner(session, user_id)
    existing = set((await session.execute(select(Event.external_id).where(
        Event.user_id == user_id, Event.source == SOURCE, Event.cancelled == False,
        Event.external_id.is_not(None)))).scalars())
    batch_id, created, skipped = uuid4(), [], 0
    for item in items:
        if item.external_id in existing:
            skipped += 1
            continue
        existing.add(item.external_id)
        event = Event(user_id=user_id, title=item.title, start_at=item.start_at, end_at=item.end_at,
                      location=item.location, rrule=item.rrule, source=SOURCE, external_id=item.external_id)
        session.add(event)
        log = await audit(session, user_id, event, None, 'create')
        log.batch_id = batch_id
        created.append(event)
    await session.flush()
    plan_note = None
    if created:
        from .planning_service import rebuild_plan
        try:
            await rebuild_plan(session, user_id, days=14)
        except Exception:  # a plan problem must not lose the import
            plan_note = 'Events were added, but the plan could not be rebuilt yet.'
    return {'batch_id': str(batch_id), 'event_ids': [str(event.id) for event in created],
            'created': len(created), 'skipped_existing': skipped, 'note': plan_note}


async def undo_import(session, user_id, batch_id) -> dict:
    """Remove every event created by one import batch."""
    from fastapi import HTTPException
    from sqlalchemy import select
    from ..models import ActionLog, Event
    from .domain_service import lock_owner
    await lock_owner(session, user_id)
    rows = list((await session.execute(select(ActionLog).where(ActionLog.user_id == user_id,
        ActionLog.batch_id == batch_id))).scalars())
    if not rows or any(row.entity != 'events' or row.action_type != 'create' for row in rows):
        raise HTTPException(status_code=404, detail='Import not found')
    if any(row.undone_at for row in rows):
        raise HTTPException(status_code=409, detail='Import already undone')
    from datetime import datetime as _dt
    events = (await session.execute(select(Event).where(Event.user_id == user_id,
        Event.id.in_([row.entity_id for row in rows])))).scalars().all()
    for event in events:
        event.cancelled = True
    for row in rows:
        row.undone_at = _dt.now(timezone.utc)
    from .planning_service import rebuild_plan
    await rebuild_plan(session, user_id, days=14)
    return {'undone': True, 'count': len(events)}
