from datetime import datetime, timedelta, timezone

from app.services.reminder_service import event_reminder_time, task_reminder_times


def test_task_reminder_rules():
    deadline = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    reminders = dict(task_reminder_times(deadline=deadline, effort_min=120, now=deadline - timedelta(days=1)))
    assert reminders["start_now"] == deadline - timedelta(minutes=180)
    assert reminders["due_soon"] == deadline - timedelta(hours=2)
    assert reminders["overdue"] == deadline + timedelta(minutes=15)


def test_event_location_adds_travel_lead():
    start = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    assert event_reminder_time(start=start) == start - timedelta(minutes=15)
    assert event_reminder_time(start=start, location="Office") == start - timedelta(minutes=45)

