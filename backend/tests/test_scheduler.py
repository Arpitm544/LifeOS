from datetime import datetime, timedelta, timezone

from app.services.scheduler import BusyBlock, SchedulableTask, build_free_slots, generate_plan


def test_scheduler_never_overlaps_and_respects_deadline():
    start = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 18, tzinfo=timezone.utc)
    slots = build_free_slots(window_start=start, window_end=end, working_hours=[(9, 18)],
                             busy=[BusyBlock(start + timedelta(hours=2), start + timedelta(hours=3))])
    blocks, unplaced = generate_plan(tasks=[SchedulableTask("a", 120, end, 90)], slots=slots)
    assert not unplaced
    assert sum(int((block.end - block.start).total_seconds() / 60) for block in blocks) == 120
    assert all(block.end <= end for block in blocks)
    assert all(left.end <= right.start for left, right in zip(blocks, blocks[1:]))

