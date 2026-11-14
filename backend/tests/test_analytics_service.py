from app.services.analytics_service import CompletedTask, compute_insights


def test_analytics_calibrates_and_detects_cold_start():
    items = [CompletedTask("study", 60, 90, 9) for _ in range(3)]
    summary = compute_insights(completed=items, planned_blocks=4, completed_blocks=3,
                               overdue_by_category={"study": (1, 4)}, snoozes_by_category={"study": (2, 4)})
    assert summary.calibration_factors["study"] == 1.0
    assert summary.plan_adherence == 0.75
    assert summary.cold_start is True

