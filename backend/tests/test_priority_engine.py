from datetime import datetime, timedelta, timezone
from app.services.priority_engine import calculate_priority

def test_priority_is_deterministic_and_banded():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = calculate_priority(now=now, deadline=now + timedelta(hours=2), effort_min=180, importance=5, blocking_count=2, created_at=now, free_working_hours=2)
    assert result.score == 85.0
    assert result.band == "P1"
    assert result.why == "Due in 2 h, needs 3 h"

