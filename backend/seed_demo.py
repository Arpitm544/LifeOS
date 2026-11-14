"""Priya's labelled demo fixtures. Dry-run requires only Python's standard library."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

MARKER = "lifeos-demo-v1"


def build_demo(user_id: str, anchor: date, tz_name: str = "Asia/Kolkata") -> dict:
    tz = ZoneInfo(tz_name)
    namespace = uuid5(NAMESPACE_URL, str(user_id))
    rows = {name: [] for name in ("tasks", "events", "preferences", "routines", "plan_blocks", "activity_events", "reminders")}

    def row_id(label: str) -> UUID:
        return uuid5(namespace, f"{MARKER}:{anchor}:{label}")

    def at(day: date, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(timezone.utc)

    def add(table: str, label: str, **values) -> UUID:
        identity = row_id(label)
        rows[table].append(dict(id=identity, user_id=str(user_id), **values))
        return identity

    # Fixed instances label the demo calendar independently of routines.
    for offset in range(7):
        day = anchor + timedelta(days=offset)
        if day.weekday() < 5:
            add("events", f"class:{day}", title="[Demo] Classes", start_at=at(day, 10), end_at=at(day, 13), source="manual", external_id=MARKER)
        if day.weekday() in (1, 3):
            add("events", f"shift:{day}", title="[Demo] Café shift", start_at=at(day, 17), end_at=at(day, 21), source="manual", external_id=MARKER)

    add("routines", "gym", title="[Demo] Gym", rrule="FREQ=WEEKLY;BYDAY=MO,WE,FR", start_time="07:00", duration_min=60, movable=True, anchor_date=anchor.isoformat())
    settings = {
        "timezone": {"name": tz_name},
        "work_hours": {"start": "09:00", "end": "18:00"},
        "quiet_hours": {"start": "22:30", "end": "07:30"},
        "focus_windows": {"windows": [["08:00", "10:00"]]},
        "demo_data": {"label": "Priya — synthetic demo history", "version": MARKER},
    }
    for key, value in settings.items():
        add("preferences", f"preference:{key}", key=key, value=value, source="default", confidence=1.0, status="active")

    # Fourteen days, two completions per day; study ratio is exactly 1.6.
    for offset in range(14, 0, -1):
        day = anchor - timedelta(days=offset)
        for category, estimate, actual, hour in (("study", 60, 96, 9), ("errand", 30, 30, 16)):
            finish = at(day, hour)
            label = f"history:{day}:{category}"
            task_id = add("tasks", label, title=f"[Demo] {category.title()} session {day}", notes=MARKER,
                          category=category, effort_est_min=estimate, effort_actual_min=actual,
                          importance=3, status="done", deadline_at=at(day, 18),
                          created_at=at(day - timedelta(days=1), 8), completed_at=finish)
            add("plan_blocks", f"block:{label}", task_id=task_id, start_at=finish - timedelta(minutes=actual),
                end_at=finish, status="done", plan_date=at(day, 0))
            add("activity_events", f"activity:{label}", type="task_completed", entity_id=task_id,
                occurred_at=finish, payload={"demo": True, "category": category, "estimated_min": estimate, "actual_min": actual})

    # Raw estimates: the planner multiplies them by the measured 1.6 study factor
    # (3 h report -> 4.8 h planned), matching the demo script.
    # Upcoming Thursday stays in the future even when seeded late in the week.
    thursday = anchor + timedelta(days=(3 - anchor.weekday()) % 7 or 7)
    report = add("tasks", "report", title="[Demo] Finish DBMS report", notes=MARKER, category="study",
                 deadline_at=at(thursday, 9), effort_est_min=180, importance=4, status="open", created_at=at(anchor, 0))
    add("tasks", "quiz", title="[Demo] Study for ML quiz", notes=MARKER, category="study",
        deadline_at=at(thursday, 9), effort_est_min=120, importance=4, status="open", created_at=at(anchor, 0))
    add("tasks", "mom", title="[Demo] Call mom", notes=MARKER, category="social",
        deadline_at=at(anchor + timedelta(days=6), 18), effort_est_min=15, importance=3, status="open", created_at=at(anchor, 0))
    # No immediately due pushes: sample reminders are in-app only until a worker is configured.
    add("reminders", "report-reminder", item_type="task", item_id=report, kind="due_soon",
        fire_at=at(thursday, 7), status="pending", message="[Demo] DBMS report is due soon.")
    return rows


async def load_demo(rows: dict) -> dict[str, int]:
    from sqlalchemy import select
    from app.db import SessionFactory, engine
    from app.models import User, ActivityEvent, Event, PlanBlock, Preference, Reminder, Routine, Task

    models = {"tasks": Task, "events": Event, "preferences": Preference, "routines": Routine,
              "plan_blocks": PlanBlock, "activity_events": ActivityEvent, "reminders": Reminder}
    counts = {name: 0 for name in rows}
    try:
        async with SessionFactory() as session, session.begin():
            # Serialize repeat seed runs for this account in PostgreSQL.
            from sqlalchemy import text
            owner = next(iter(rows["preferences"]))["user_id"]
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:owner))"), {"owner": str(owner)})
            from sqlalchemy.dialects.postgresql import insert
            await session.execute(insert(User).values(id=owner).on_conflict_do_nothing(index_elements=['id']))
            for table, fixtures in rows.items():
                model = models[table]
                for values in fixtures:
                    existing = await session.get(model, values["id"])
                    if existing is not None:
                        continue
                    if table == "preferences":
                        existing = (await session.execute(select(Preference.id).where(
                            Preference.user_id == values["user_id"], Preference.key == values["key"]))).scalar_one_or_none()
                        if existing is not None:
                            continue
                    session.add(model(**values))
                    counts[table] += 1
                # Parent fixture tables are listed before their FK dependents.
                await session.flush()
            await session.flush()
    finally:
        await engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an existing dedicated demo user's database rows.")
    parser.add_argument("--user-id", required=True, type=str, help="Existing demo Clerk subject (user_...)")
    parser.add_argument("--date", type=date.fromisoformat, help="Local reference day (YYYY-MM-DD)")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--dry-run", action="store_true", help="Print fixtures without connecting to the database")
    args = parser.parse_args()
    anchor = args.date or datetime.now(ZoneInfo(args.timezone)).date()
    rows = build_demo(args.user_id, anchor, args.timezone)
    if args.dry_run:
        print(json.dumps(rows, default=str, indent=2))
    else:
        print(json.dumps({"inserted": asyncio.run(load_demo(rows)), "demo_date": str(anchor)}))


if __name__ == "__main__":
    main()
