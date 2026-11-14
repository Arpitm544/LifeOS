from datetime import datetime, timedelta, timezone

from app.services.capacity_guard import CapacityTask, check_capacity


def test_capacity_guard_reports_shortfall_and_options():
    deadline = datetime(2026, 1, 5, 17, tzinfo=timezone.utc)
    conflicts = check_capacity(
        tasks=[CapacityTask("a", "Report", 180, deadline, 80), CapacityTask("b", "Quiz", 120, deadline, 40)],
        free_minutes_until={deadline: 240},
    )
    assert len(conflicts) == 1
    assert conflicts[0].shortfall_min == 60
    assert [option["type"] for option in conflicts[0].options] == ["extend_hours", "move_flexible", "renegotiate"]

