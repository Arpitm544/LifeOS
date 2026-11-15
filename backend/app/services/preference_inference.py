"""Inferred preferences (PRD F6). Rules over logged behaviour propose a preference.

Nothing is learned silently: a proposal is stored as its own row
(`inferred.<key>`, source 'inferred', status 'suggested', confidence < 1) next to
the preference it would change, and only takes effect when the user accepts it
on the Profile screen. A dismissed proposal is not offered again for 30 days.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..models import ActivityEvent, Preference, Reminder

PREFIX = 'inferred.'
SNOOZE_SENDS = 5          # look at the last 5 sends of a reminder type ...
SNOOZE_THRESHOLD = 4      # ... and propose a change when 4 of them were snoozed
LEAD_STEP_MIN = 15
DEFAULT_LEAD_MIN = 60
MOVE_THRESHOLD = 3        # a block moved to the same hour 3 times
MOVE_LOOKBACK = timedelta(days=14)
FOCUS_LENGTH_H = 2
DISMISS_COOLDOWN = timedelta(days=30)
MAX_CONFIDENCE = 0.9      # inferred rows always stay below 1 until accepted


@dataclass(frozen=True)
class Proposal:
    key: str
    value: dict
    confidence: float
    reason: str


def target_key(key: str) -> str:
    return key[len(PREFIX):] if key.startswith(PREFIX) else key


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _active(session, user_id) -> dict:
    return {row.key: row.value for row in (await session.execute(select(Preference).where(
        Preference.user_id == user_id, Preference.status == 'active'))).scalars()}


def local_hour(moment: datetime, values: dict) -> int:
    zone = ZoneInfo(values.get('timezone', {}).get('name', 'UTC'))
    return _utc(moment).astimezone(zone).hour


async def snooze_rule(session, user_id, values: dict) -> Proposal | None:
    """'Start now' reminders snoozed in 4 of the last 5 sends -> remind 15 minutes later."""
    sent = list((await session.execute(select(Reminder.id).where(Reminder.user_id == user_id,
        Reminder.item_type == 'task', Reminder.kind == 'start_now', Reminder.sent_at.is_not(None))
        .order_by(Reminder.sent_at.desc()).limit(SNOOZE_SENDS))).scalars())
    if len(sent) < SNOOZE_SENDS:
        return None
    snoozed = set((await session.execute(select(ActivityEvent.entity_id).where(ActivityEvent.user_id == user_id,
        ActivityEvent.type == 'reminder_snoozed', ActivityEvent.entity_id.in_(sent)))).scalars())
    count = sum(1 for identity in sent if identity in snoozed)
    if count < SNOOZE_THRESHOLD:
        return None
    current = int(values.get('reminder_lead', {}).get('minutes', DEFAULT_LEAD_MIN))
    if current <= 0:
        return None
    # The lead is the buffer before the latest start, so a smaller lead means a later reminder.
    return Proposal('reminder_lead', {'minutes': max(0, current - LEAD_STEP_MIN)},
                    min(MAX_CONFIDENCE, count / SNOOZE_SENDS),
                    f'You snoozed {count} of your last {SNOOZE_SENDS} start reminders.')


async def move_rule(session, user_id, values: dict, *, now: datetime) -> Proposal | None:
    """A focus block moved to the same local hour 3 times in 14 days -> propose that hour as a focus window."""
    moves = list((await session.execute(select(ActivityEvent.payload).where(ActivityEvent.user_id == user_id,
        ActivityEvent.type == 'block_moved', ActivityEvent.occurred_at >= now - MOVE_LOOKBACK))).scalars())
    hours = Counter(payload['hour'] for payload in moves
                    if isinstance(payload, dict) and isinstance(payload.get('hour'), int) and 0 <= payload['hour'] <= 23)
    if not hours:
        return None
    # Most moves first; ties go to the earlier hour so the result is deterministic.
    hour, count = sorted(hours.items(), key=lambda item: (-item[1], item[0]))[0]
    if count < MOVE_THRESHOLD:
        return None
    start = f'{hour:02d}:00'
    windows = values.get('focus_windows', {}).get('windows') or []
    if any(existing[0] == start for existing in windows):
        return None
    end = '23:59' if hour + FOCUS_LENGTH_H >= 24 else f'{hour + FOCUS_LENGTH_H:02d}:00'
    return Proposal('focus_windows', {'windows': [[start, end]]}, min(MAX_CONFIDENCE, count / 5),
                    f'You moved focus blocks to {start} {count} times.')


async def _dismissed_recently(session, user_id, proposal: Proposal, *, now: datetime) -> bool:
    rows = (await session.execute(select(ActivityEvent.payload).where(ActivityEvent.user_id == user_id,
        ActivityEvent.type == 'preference_dismissed', ActivityEvent.occurred_at >= now - DISMISS_COOLDOWN))).scalars()
    return any(isinstance(row, dict) and row.get('key') == proposal.key and row.get('value') == proposal.value
               for row in rows)


async def run_inference(session, user_id, *, now: datetime | None = None) -> list[Preference]:
    """Apply every rule; store new or changed proposals. Returns the rows written."""
    now = _utc(now or datetime.now(timezone.utc))
    values = await _active(session, user_id)
    proposals = [p for p in (await snooze_rule(session, user_id, values),
                             await move_rule(session, user_id, values, now=now)) if p is not None]
    written = []
    for proposal in proposals:
        if values.get(proposal.key) == proposal.value or await _dismissed_recently(session, user_id, proposal, now=now):
            continue
        key = PREFIX + proposal.key
        row = (await session.execute(select(Preference).where(Preference.user_id == user_id,
            Preference.key == key).with_for_update())).scalar_one_or_none()
        if row is not None and row.value == proposal.value:
            continue
        if row is None:
            row = Preference(user_id=user_id, key=key)
            session.add(row)
        row.value, row.source, row.status, row.confidence = proposal.value, 'inferred', 'suggested', proposal.confidence
        session.add(ActivityEvent(user_id=user_id, type='preference_inferred', occurred_at=now,
                                  payload={'key': proposal.key, 'value': proposal.value, 'reason': proposal.reason}))
        written.append(row)
    await session.flush()
    return written


async def accept_inferred(session, user_id, row: Preference):
    """Copy an accepted proposal into the preference it targets, then remove the proposal row."""
    from .domain_service import audit, snapshot
    from ..models import ActionLog
    key = target_key(row.key)
    target = (await session.execute(select(Preference).where(Preference.user_id == user_id,
        Preference.key == key).with_for_update())).scalar_one_or_none()
    before = snapshot(target) if target else None
    if target is None:
        target = Preference(user_id=user_id, key=key)
        session.add(target)
    # Accepted: active now, still marked as learned so the Profile list shows where it came from.
    target.value, target.source, target.status, target.confidence = row.value, 'inferred', 'active', row.confidence
    await session.flush()
    action = await audit(session, user_id, target, before, 'create' if before is None else 'accept')
    session.add(ActionLog(user_id=user_id, entity='preferences', entity_id=row.id,
                          action_type='delete', before=snapshot(row), after=None))
    await session.delete(row)
    await session.flush()
    return target, action


def record_dismissal(session, user_id, row: Preference) -> None:
    if row.key.startswith(PREFIX):
        session.add(ActivityEvent(user_id=user_id, type='preference_dismissed', occurred_at=datetime.now(timezone.utc),
                                  payload={'key': target_key(row.key), 'value': row.value}))
