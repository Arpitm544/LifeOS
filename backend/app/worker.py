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
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, distinct, select, update

from .config import get_settings
from .models import (ActivityEvent, IdempotencyRecord, Message, PlanBlock, Preference, PushSubscription,
                     Reminder, Task, WorkerStatus)
from .services.push_service import notification_payload, send_to_subscriptions

log = logging.getLogger('lifeos.worker')
MISSED_AFTER = timedelta(hours=2)
RATE_WINDOW = timedelta(minutes=10)
MESSAGE_RETENTION = timedelta(days=90)
ACTIVITY_RETENTION = timedelta(days=180)
IDEMPOTENCY_RETENTION = timedelta(days=2)
DEFAULT_PLAN_TIME = time(8, 0)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def deliver_due(session, settings, *, now: datetime, batch_size: int = 100) -> dict:
    """One delivery pass. Must run inside a transaction (rows stay locked until commit)."""
    missed = await session.execute(update(Reminder).where(Reminder.status == 'pending',
        Reminder.fire_at < now - MISSED_AFTER).values(status='missed'))
    due = list((await session.execute(select(Reminder).where(Reminder.status == 'pending', Reminder.fire_at <= now)
        .order_by(Reminder.fire_at).limit(batch_size).with_for_update(skip_locked=True))).scalars())
    by_user: dict[str, list[Reminder]] = defaultdict(list)
    for reminder in due:
        by_user[reminder.user_id].append(reminder)
    sent = deferred = 0
    for user_id, items in by_user.items():
        last = (await session.execute(select(Reminder.sent_at).where(Reminder.user_id == user_id,
            Reminder.sent_at.is_not(None)).order_by(Reminder.sent_at.desc()).limit(1))).scalar_one_or_none()
        if last is not None and now - _utc(last) < RATE_WINDOW:
            deferred += len(items)  # F3.3: wait, then send these as one summary
            continue
        subscriptions = list((await session.execute(select(PushSubscription).where(
            PushSubscription.user_id == user_id))).scalars())
        newest = items[-1]
        result = await send_to_subscriptions(subscriptions, notification_payload(newest, summary_count=len(items)), settings)
        if result.gone_endpoints:
            await session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id,
                PushSubscription.endpoint.in_(result.gone_endpoints)))
        # In-app fallback (F3.5): a sent reminder shows in the notification centre
        # and on Today even when no push subscription exists.
        for reminder in items:
            reminder.status, reminder.sent_at = 'sent', now
        sent += len(items)
    await session.flush()
    return {'sent': sent, 'deferred': deferred, 'missed': missed.rowcount or 0}


async def rescore_all(session, *, now: datetime) -> int:
    from .services.planning_service import recalculate_priorities
    users = list((await session.execute(select(distinct(Task.user_id)).where(
        Task.status.in_(['open', 'blocked'])))).scalars())
    for user_id in users:
        await recalculate_priorities(session, user_id, now)
    return len(users)


async def daily_plans(session, *, now: datetime) -> int:
    """At each user's start time, build today's plan and queue a 'plan ready' push."""
    from .services.planning_service import rebuild_plan
    created = 0
    users = list((await session.execute(select(distinct(Task.user_id)).where(
        Task.status.in_(['open', 'blocked'])))).scalars())
    for user_id in users:
        prefs = {row.key: row.value for row in (await session.execute(select(Preference).where(
            Preference.user_id == user_id, Preference.status == 'active'))).scalars()}
        zone = ZoneInfo(prefs.get('timezone', {}).get('name', 'UTC'))
        local = now.astimezone(zone)
        start = time.fromisoformat(prefs.get('work_hours', {}).get('start', '')) if prefs.get('work_hours') else DEFAULT_PLAN_TIME
        plan_time = min(start, DEFAULT_PLAN_TIME)
        if local.time() < plan_time:
            continue
        midnight = datetime.combine(local.date(), time.min, tzinfo=zone).astimezone(timezone.utc)
        exists = (await session.execute(select(Reminder.id).where(Reminder.user_id == user_id,
            Reminder.kind == 'daily_plan', Reminder.fire_at >= midnight))).first()
        if exists:
            continue
        result = await rebuild_plan(session, user_id, now=now)
        today = [b for b in result['blocks'] if _utc(b.start_at) < midnight + timedelta(days=1)]
        if not today:
            continue
        hours = sum((_utc(b.end_at) - _utc(b.start_at)).total_seconds() for b in today) / 3600
        session.add(Reminder(user_id=user_id, item_type='task', item_id=today[0].task_id, kind='daily_plan',
            fire_at=now, status='pending',
            message=f'Your plan for today is ready: {len({b.task_id for b in today})} tasks, {hours:.1f} h of focus.'))
        created += 1
    await session.flush()
    return created


async def retention(session, *, now: datetime) -> dict:
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
    async with factory() as session, session.begin():
        report['delivery'] = await deliver_due(session, settings, now=now)
    for job, (interval, function) in JOBS.items():
        previous = last_runs.get(job)
        if previous is None or now - previous >= interval:
            async with factory() as session, session.begin():
                report[job] = await function(session, now=now)
            last_runs[job] = now
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
