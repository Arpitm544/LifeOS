from app.services.insight_service import validate_suggestions


def test_invalid_numbers_and_types_are_rejected():
    stats = {"study_factor": 1.6, "adherence": 0.75}
    suggestions = validate_suggestions([
        {"type": "pad_estimates", "text": "Your study tasks take 1.6x longer."},
        {"type": "unknown", "text": "Try 1.6."},
        {"type": "move_focus_window", "text": "Your focus is 9 hours."},
    ], stats)
    assert len(suggestions) == 1
    assert suggestions[0].type == "pad_estimates"

