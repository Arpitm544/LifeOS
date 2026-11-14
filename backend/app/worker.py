"""Reminder worker and scheduled jobs: `python -m app.worker`.

Runs as a separate process with an administrative database connection (it reads
due reminders for every user). Reminders are rows in PostgreSQL, so a restarted
worker picks up anything it missed (PRD NFR-R4).
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, distinct, select, text, update

from .config import get_settings
from .models import (ActivityEvent, IdempotencyRecord, Message, Preference, PushSubscription, Reminder, Task,
                     WorkerStatus)
from .services.push_service import notification_payload, send_to_subscriptions

log = logging.getLogger('lifeos.worker')
MISSED_AFTER = timedelta(hours=2)
RATE_WINDOW = timedelta(minutes=10)
STUCK_SENDING = timedelta(minutes=5)
MESSAGE_RETENTION = timedelta(days=90)
ACTIVITY_RETENTION = timedelta(days=180)
IDEMPOTENCY_RETENTION = timedelta(days=2)
DEFAULT_PLAN_TIME = time(8, 0)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _lock_user(session, user_id: str) -> None:
    # Serializes claims for one user across worker processes (F3.3 rate limit).
    if session.get_bind().dialect.name == 'postgresql':
        await session.execute(text('SELECT pg_advisory_xact_lock(7303, hashtext(:owner))'), {'owner': user_id})


@dataclass
class Claim:
    user_id: str
    reminder_ids: list[UUID]
    payload: dict
    subscriptions: list[PushSubscription]


async def claim_due(session, *, now: datetime, batch_size: int = 100) -> tuple[list[Claim], dict]:
    """Short transaction: mark due reminders 'sending' (one push per user)."""
    recovered = await session.execute(update(Reminder).where(Reminder.status == 'sending',
        Reminder.sent_at < now - STUCK_SENDING).values(status='pending', sent_at=None))
    missed = await session.execute(update(Reminder).where(Reminder.status == 'pending',
        Reminder.fire_at < now - MISSED_AFTER).values(status='missed'))
    due = list((await session.execute(select(Reminder).where(Reminder.status == 'pending', Reminder.fire_at <= now)
        .order_by(Reminder.fire_at).limit(batch_size).with_for_update(skip_locked=True))).scalars())
    by_user: dict[str, list[Reminder]] = defaultdict(list)
    for reminder in due:
        by_user[reminder.user_id].append(reminder)
    claims, deferred = [], 0
    for user_id, items in by_user.items():
        await _lock_user(session, user_id)
        last = (await session.execute(select(Reminder.sent_at).where(Reminder.user_id == user_id,
            Reminder.sent_at.is_not(None)).order_by(Reminder.sent_at.desc()).limit(1))).scalar_one_or_none()
        if last is not None and now - _utc(last) < RATE_WINDOW:
            deferred += len(items)  # wait, then send these as one summary
            continue
        for reminder in items:
            reminder.status, reminder.sent_at = 'sending', now
        subscriptions = list((await session.execute(select(PushSubscription).where(
            PushSubscription.user_id == user_id))).scalars())
        claims.append(Claim(user_id, [item.id for item in items],
                            notification_payload(items[-1], summary_count=len(items)), subscriptions))
    await session.flush()
    return claims, {'deferred': deferred, 'missed': missed.rowcount or 0, 'recovered': recovered.rowcount or 0}


async def deliver_due(factory, settings, *, now: datetime, batch_size: int = 100) -> dict:
    """Claim, send with no transaction open, then record the outcome."""
    async with factory() as session, session.begin():
        claims, report = await claim_due(session, now=now, batch_size=batch_size)
    outcomes = []
    for claim in claims:
        result = await send_to_subscriptions(claim.subscriptions, claim.payload, settings)
        outcomes.append((claim, result))
    sent = retry = 0
    for claim, result in outcomes:
        # One transaction per claim: a failure cannot roll back other users' 'sent'.
        try:
            async with factory() as session, session.begin():
                sent_now, retry_now = await _record_outcome(session, claim, result)
            sent, retry = sent + sent_now, retry + retry_now
        except Exception:
            log.exception('recording a push outcome failed; recovery retries it later')
    return {'sent': sent, 'retry': retry, **report}


async def _record_outcome(session, claim, result) -> tuple[int, int]:
    """Returns (sent, retried) reminder counts for one claim."""
    if result.gone_endpoints:
        await session.execute(delete(PushSubscription).where(PushSubscription.user_id == claim.user_id,
            PushSubscription.endpoint.in_(result.gone_endpoints)))
    if result.failed and not result.sent:
        # Transient push failure: retry on a later cycle (still visible in-app).
        await session.execute(update(Reminder).where(Reminder.id.in_(claim.reminder_ids),
            Reminder.status == 'sending').values(status='pending', sent_at=None))
        return 0, len(claim.reminder_ids)
    # Delivered, or no push possible: shown in the notification centre and Today (F3.5).
    await session.execute(update(Reminder).where(Reminder.id.in_(claim.reminder_ids),
        Reminder.status == 'sending').values(status='sent'))
    return len(claim.reminder_ids), 0


async def _users_with_open_tasks(factory) -> list[str]:
    async with factory() as session:
        return list((await session.execute(select(distinct(Task.user_id)).where(
            Task.status.in_(['open', 'blocked'])))).scalars())


async def _per_user(factory, job: str, users: list[str], function) -> dict:
    """One transaction per user, so one bad record cannot block other tenants."""
    done = failed = 0
    for user_id in users:
        try:
            async with factory() as session, session.begin():
                done += bool(await function(session, user_id))
        except Exception:
            failed += 1
            log.exception('%s failed for one user', job)  # no ids or text beyond the job name
    return {'users': len(users), 'done': done, 'failed': failed}


async def rescore_all(factory, *, now: datetime) -> dict:
    from .services.planning_service import recalculate_priorities

    async def rescore(session, user_id):
        await recalculate_priorities(session, user_id, now)
        return True
    return await _per_user(factory, 'rescore', await _users_with_open_tasks(factory), rescore)


async def plan_today(session, user_id: str, *, now: datetime) -> bool:
    """At the user's start time, build today's plan once and queue a 'plan ready' push."""
    from .services.planning_service import rebuild_plan
    prefs = {row.key: row.value for row in (await session.execute(select(Preference).where(
        Preference.user_id == user_id, Preference.status == 'active'))).scalars()}
    zone = ZoneInfo(prefs.get('timezone', {}).get('name', 'UTC'))
    local = now.astimezone(zone)
    start = time.fromisoformat(prefs['work_hours']['start']) if prefs.get('work_hours') else DEFAULT_PLAN_TIME
    if local.time() < min(start, DEFAULT_PLAN_TIME):
        return False
    midnight = datetime.combine(local.date(), time.min, tzinfo=zone).astimezone(timezone.utc)
    attempted = (await session.execute(select(ActivityEvent.id).where(ActivityEvent.user_id == user_id,
        ActivityEvent.type == 'daily_plan_built', ActivityEvent.occurred_at >= midnight))).first()
    if attempted:
        return False  # once per local day, even when nothing needed planning
    session.add(ActivityEvent(user_id=user_id, type='daily_plan_built', occurred_at=now,
                              payload={'date': local.date().isoformat()}))
    result = await rebuild_plan(session, user_id, now=now)
    await session.flush()
    today = [b for b in result['blocks'] if _utc(b.start_at) < midnight + timedelta(days=1)]
    # The push is the morning brief: what is planned, plus any deadline at risk (proactive, no LLM).
    from .services.brief_service import compose, load_brief_data, push_message
    brief = compose(await load_brief_data(session, user_id, now=now))
    target = today[0].task_id if today else next(
        (row.id for row in (await session.execute(select(Task).where(Task.user_id == user_id,
            Task.status.in_(['open', 'blocked'])).order_by(Task.priority_score.desc()).limit(1))).scalars()), None)
    if not today and not brief['counts']['at_risk'] and not brief['counts']['overdue']:
        return False
    if target is None:
        return False
    session.add(Reminder(user_id=user_id, item_type='task', item_id=target, kind='daily_plan',
        fire_at=now, status='pending', message=push_message(brief)[:300]))
    return True


async def daily_plans(factory, *, now: datetime) -> dict:
    async def plan(session, user_id):
        return await plan_today(session, user_id, now=now)
    return await _per_user(factory, 'daily_plan', await _users_with_open_tasks(factory), plan)


async def retention(factory, *, now: datetime) -> dict:
    async with factory() as session, session.begin():
        messages = await session.execute(delete(Message).where(Message.created_at < now - MESSAGE_RETENTION))
        activity = await session.execute(delete(ActivityEvent).where(ActivityEvent.occurred_at < now - ACTIVITY_RETENTION))
        keys = await session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < now - IDEMPOTENCY_RETENTION))
    return {'messages': messages.rowcount or 0, 'activity_events': activity.rowcount or 0,
            'idempotency_records': keys.rowcount or 0}


JOBS = {'rescore': (timedelta(hours=1), rescore_all), 'daily_plan': (timedelta(minutes=15), daily_plans),
        'retention': (timedelta(hours=24), retention)}


async def heartbeat(session, name: str, *, now: datetime, jobs: dict) -> None:
    row = await session.get(WorkerStatus, name)
    if row is None:
        session.add(WorkerStatus(worker_name=name, last_seen_at=now, last_jobs=jobs))
    else:
        row.last_seen_at, row.last_jobs = now, jobs


async def run_cycle(factory, settings, *, name: str, now: datetime | None = None, last_runs: dict | None = None) -> dict:
    now = _utc(now or datetime.now(timezone.utc))
    last_runs = last_runs if last_runs is not None else {}
    report: dict = {}
    steps = [('delivery', lambda: deliver_due(factory, settings, now=now))]
    for job, (interval, function) in JOBS.items():
        previous = last_runs.get(job)
        if previous is None or now - previous >= interval:
            steps.append((job, lambda function=function: function(factory, now=now)))
    for job, step in steps:
        # Each job is isolated: one failing job does not skip the rest or the heartbeat.
        try:
            report[job] = await step()
            if job in JOBS:
                last_runs[job] = now
        except Exception:
            log.exception('worker job %s failed', job)
            report[job] = 'failed'
    async with factory() as session, session.begin():
        await heartbeat(session, name, now=now, jobs={job: value.isoformat() for job, value in last_runs.items()})
    return report


async def main() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from .database_tls import database_ssl_context
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    settings = get_settings()
    url = settings.worker_database_url or settings.database_url
    engine = create_async_engine(url, pool_pre_ping=True,
        connect_args={"ssl": database_ssl_context()} if settings.database_ssl else {"ssl": False})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    name = os.environ.get('WORKER_NAME') or f'worker-{socket.gethostname()}'
    last_runs: dict = {}
    log.info('LifeOS worker %s polling every %ss', name, settings.worker_poll_seconds)
    try:
        while True:
            try:
                report = await run_cycle(factory, settings, name=name, last_runs=last_runs)
                # Ids and counts only: no message text or titles in logs.
                log.info('cycle %s', report)
            except Exception:
                log.exception('worker cycle failed; retrying next poll')
            await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
