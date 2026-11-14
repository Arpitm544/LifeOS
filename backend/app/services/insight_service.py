"""Productivity insights (PRD F4). Code computes every number; the LLM only words them."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..models import ActivityEvent, PlanBlock, Preference, Reminder, Suggestion as StoredSuggestion, Task
from .analytics_service import CompletedTask, compute_insights


ALLOWED_SUGGESTION_TYPES = {"pad_estimates", "move_focus_window", "adjust_reminder_lead", "protect_routine"}
HISTORY_DAYS = 14


@dataclass(frozen=True)
class Suggestion:
    type: str
    text: str
    cited_values: list[str]


def _numbers(stats: dict) -> set[str]:
    values = set()
    for value in stats.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.add(str(value))
            if isinstance(value, float) and value.is_integer():
                values.add(str(int(value)))
    return values


def validate_suggestions(raw: list[dict], stats: dict) -> list[Suggestion]:
    allowed_numbers = _numbers(stats)
    valid: list[Suggestion] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            continue
        kind, text = item.get("type"), item['text'].strip()
        if kind not in ALLOWED_SUGGESTION_TYPES or not text or len(text) > 500:
            continue
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        if any(number not in allowed_numbers for number in numbers):
            continue
        valid.append(Suggestion(kind, text, numbers))
        if len(valid) == 3:
            break
    return valid


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def compute_user_insights(session, user_id, *, now: datetime | None = None) -> dict:
    now = _utc(now or datetime.now(timezone.utc))
    prefs = {row.key: row.value for row in (await session.execute(select(Preference).where(
        Preference.user_id == user_id, Preference.status == 'active'))).scalars()}
    zone = ZoneInfo(prefs.get('timezone', {}).get('name', 'UTC'))
    since = now - timedelta(days=HISTORY_DAYS)
    done = list((await session.execute(select(Task).where(Task.user_id == user_id, Task.status == 'done',
        Task.completed_at.is_not(None)).order_by(Task.completed_at))).scalars())
    samples = [CompletedTask(task.category, task.effort_est_min, task.effort_actual_min,
                             _utc(task.completed_at).astimezone(zone).hour)
               for task in done if task.effort_actual_min is not None]
    recent_done = [task for task in done if _utc(task.completed_at) >= since]
    # Focus windows: completions per local hour over the last 14 days.
    recent_samples = [CompletedTask(task.category, task.effort_est_min, task.effort_actual_min or task.effort_est_min,
                                    _utc(task.completed_at).astimezone(zone).hour) for task in recent_done]
    blocks = list((await session.execute(select(PlanBlock).where(PlanBlock.user_id == user_id,
        PlanBlock.end_at >= since, PlanBlock.end_at <= now))).scalars())
    # Blocks carry no completion time, so every done block counts (including
    # ones that cross local midnight).
    planned = len(blocks)
    completed_blocks = sum(1 for block in blocks if block.status == 'done')
    deadline_tasks = list((await session.execute(select(Task).where(Task.user_id == user_id,
        Task.deadline_at.is_not(None), Task.deadline_at >= since, Task.deadline_at <= now,
        Task.status != 'dropped'))).scalars())
    overdue: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for task in deadline_tasks:
        overdue[task.category][1] += 1
        if task.status != 'done' or (task.completed_at and _utc(task.completed_at) > _utc(task.deadline_at)):
            overdue[task.category][0] += 1
    reminders = list((await session.execute(select(Reminder, Task.category).join(Task, Task.id == Reminder.item_id)
        .where(Reminder.user_id == user_id, Reminder.item_type == 'task', Reminder.status.in_(['sent', 'acted']),
               Reminder.fire_at >= since))).all())
    snoozes: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for reminder, category in reminders:
        snoozes[category][1] += 1
    snooze_events = list((await session.execute(select(ActivityEvent).where(ActivityEvent.user_id == user_id,
        ActivityEvent.type == 'reminder_snoozed', ActivityEvent.occurred_at >= since))).scalars())
    for event in snooze_events:
        payload = event.payload or {}
        if payload.get('kind') == 'event' or not payload.get('category'):
            continue  # only task reminders are in the denominator
        category = payload['category']
        snoozes[category][0] += 1
        snoozes[category][1] = max(snoozes[category][1], snoozes[category][0])
    summary = compute_insights(completed=samples, planned_blocks=planned, completed_blocks=completed_blocks,
                               overdue_by_category={k: tuple(v) for k, v in overdue.items()},
                               snoozes_by_category={k: tuple(v) for k, v in snoozes.items()})
    focus = compute_insights(completed=recent_samples, planned_blocks=0, completed_blocks=0,
                             overdue_by_category={}, snoozes_by_category={}).focus_windows if recent_samples else []
    if not focus and prefs.get('focus_windows', {}).get('windows'):
        # Cold start: onboarding answer seeds focus windows.
        focus = [(int(start[:2]), int(end[:2])) for start, end in prefs['focus_windows']['windows']]
    today = now.astimezone(zone).date()
    chart = []
    for offset in range(HISTORY_DAYS - 1, -1, -1):
        day = today - timedelta(days=offset)
        count = sum(1 for task in recent_done if _utc(task.completed_at).astimezone(zone).date() == day)
        chart.append({'date': day.isoformat(), 'completed': count})
    due_recent = sum(v[1] for v in overdue.values())
    completion_rate = round(1 - sum(v[0] for v in overdue.values()) / due_recent, 2) if due_recent else None
    return {
        'calibration_factors': summary.calibration_factors,
        'focus_windows': focus,
        'plan_adherence': summary.plan_adherence if planned else 0.0,
        'overdue_rates': summary.overdue_rates,
        'snooze_rates': summary.snooze_rates,
        'cold_start': summary.cold_start,
        'completed_14d': len(recent_done),
        'completion_rate': completion_rate,
        'planned_blocks_14d': planned,
        'completion_chart': chart,
        'samples': len(samples),
    }


def flat_stats(insights: dict) -> dict:
    """Flat numeric view handed to the LLM; suggestion numbers must come from here."""
    stats: dict = {'plan_adherence_pct': round(insights['plan_adherence'] * 100),
                   'completed_14d': insights['completed_14d'], 'samples': insights['samples']}
    for category, factor in insights['calibration_factors'].items():
        stats[f'{category}_factor'] = factor
    for category, rate in insights['snooze_rates'].items():
        stats[f'{category}_snooze_pct'] = round(rate * 100)
    for category, rate in insights['overdue_rates'].items():
        stats[f'{category}_overdue_pct'] = round(rate * 100)
    if insights['focus_windows']:
        start, end = insights['focus_windows'][0]
        stats['focus_window_hours'] = end - start
    return stats


def template_suggestions(insights: dict, stats: dict) -> list[dict]:
    """Deterministic suggestions used when the LLM is off or its output is rejected."""
    output = []
    for category, factor in sorted(insights['calibration_factors'].items(), key=lambda item: -item[1]):
        if factor >= 1.2:
            output.append({'type': 'pad_estimates', 'text': f'Your {category} tasks take {factor}x your estimates. '
                           'I can pad new ones automatically.', 'payload': {'category': category, 'factor': factor}})
            break
    for category, rate in insights['snooze_rates'].items():
        pct = round(rate * 100)
        if pct >= 50:
            output.append({'type': 'adjust_reminder_lead', 'text': f'You snooze {pct}% of {category} reminders. '
                           'Want them 15 minutes later?', 'payload': {'category': category, 'add_minutes': 15}})
            break
    if insights['focus_windows']:
        start, end = insights['focus_windows'][0]
        output.append({'type': 'move_focus_window', 'text': 'You finish the most work in your top focus window. '
                       'Protect it for deep work?', 'payload': {'windows': [[f'{start:02d}:00', '23:59' if end >= 24 else f'{end:02d}:00']]}})
    return output[:3]


async def generate_suggestions(insights: dict, llm=None) -> list[dict]:
    stats = flat_stats(insights)
    templates = template_suggestions(insights, stats)
    payload_by_type = {item['type']: item['payload'] for item in templates}
    # The LLM may only reword suggestions code can back; with none, skip the call.
    if templates and llm is not None and hasattr(llm, 'write'):
        from .llm_client import INSIGHT_PROMPT
        try:
            text = await llm.write(system=INSIGHT_PROMPT, payload=stats)
            match = re.search(r'\{.*\}', text, re.S)
            raw = json.loads(match.group(0)).get('suggestions', []) if match else []
            # Only types the backend can apply, and only with a matching computed payload.
            checked = [item for item in validate_suggestions(raw, stats) if item.type in payload_by_type]
            if checked:
                return [{'type': item.type, 'text': item.text, 'payload': payload_by_type[item.type]} for item in checked]
        except Exception:  # wording is optional; numbers stay template-driven
            pass
    return templates


async def todays_suggestions(session, user_id, *, now: datetime) -> list[StoredSuggestion] | None:
    """Suggestions generated in the last 24 h, or None when none were generated."""
    rows = list((await session.execute(select(StoredSuggestion).where(StoredSuggestion.user_id == user_id,
        StoredSuggestion.created_at >= now - timedelta(hours=24)).order_by(StoredSuggestion.created_at))).scalars())
    return [row for row in rows if row.status == 'active'] if rows else None


async def store_suggestions(session, user_id, items: list[dict], *, now: datetime) -> list[StoredSuggestion]:
    created = []
    for item in items:
        row = StoredSuggestion(user_id=user_id, type=item['type'], text=item['text'], payload=item['payload'],
                               status='active', created_at=now)
        session.add(row)
        created.append(row)
    await session.flush()
    return created


async def latest_suggestions(session, user_id, insights: dict, *, now: datetime, llm=None) -> list[StoredSuggestion]:
    """Reuse today's suggestions; generate at most once per day (or on demand)."""
    cached = await todays_suggestions(session, user_id, now=now)
    if cached is not None:
        return cached
    created = []
    for item in await generate_suggestions(insights, llm):
        row = StoredSuggestion(user_id=user_id, type=item['type'], text=item['text'], payload=item['payload'],
                               status='active', created_at=now)
        session.add(row)
        created.append(row)
    await session.flush()
    return created


async def apply_suggestion(session, user_id, row: StoredSuggestion) -> dict:
    """Turn an accepted suggestion into a stated preference the planner reads."""
    from .domain_service import audit, snapshot
    key, value = None, None
    if row.type == 'pad_estimates':
        key, value = 'estimate_padding', {'enabled': True}
    elif row.type == 'move_focus_window':
        key, value = 'focus_windows', {'windows': row.payload['windows']}
    elif row.type == 'adjust_reminder_lead':
        current = (await session.execute(select(Preference).where(Preference.user_id == user_id,
            Preference.key == 'reminder_lead'))).scalar_one_or_none()
        # Lead = buffer before "start now"; snoozed often -> remind later (smaller lead).
        minutes = (current.value.get('minutes', 60) if current else 60) - int(row.payload.get('add_minutes', 15))
        key, value = 'reminder_lead', {'minutes': max(0, minutes)}
    if key is not None:
        pref = (await session.execute(select(Preference).where(Preference.user_id == user_id,
            Preference.key == key).with_for_update())).scalar_one_or_none()
        before = snapshot(pref) if pref else None
        if pref is None:
            pref = Preference(user_id=user_id, key=key, value=value, source='stated', confidence=1.0, status='active')
            session.add(pref)
        else:
            pref.value, pref.source, pref.status, pref.confidence = value, 'stated', 'active', 1.0
        await session.flush()
        await audit(session, user_id, pref, before, 'create' if before is None else 'update')
    row.status = 'applied'
    await session.flush()
    return {'id': str(row.id), 'status': row.status, 'preference': {'key': key, 'value': value} if key else None}
