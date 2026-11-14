from datetime import date, datetime, timezone
import pytest
from pydantic import ValidationError
from app.schemas_preferences import PreferenceUpdate
from app.services.recurrence import expand_routine


@pytest.mark.parametrize('key,value', [('unknown', {}), ('work_hours', {'start':'18:00','end':'09:00'}),
    ('reminder_lead', {'minutes':-1}), ('timezone', {'name':'invalid'})])
def test_invalid_preferences(key, value):
    with pytest.raises(ValidationError):
        PreferenceUpdate(key=key, value=value)


def test_inferred_preference_cannot_activate_silently():
    with pytest.raises(ValidationError):
        PreferenceUpdate(key='reminder_lead', value={'minutes':30}, source='inferred', confidence=.8)


def test_instance_override_does_not_change_series():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    end = datetime(2026, 1, 8, tzinfo=timezone.utc)
    rows = expand_routine('FREQ=DAILY', '07:00', 60, date(2026,1,5), start, end, 'UTC')
    changed = expand_routine('FREQ=DAILY', '07:00', 60, date(2026,1,5), start, end, 'UTC',
        {rows[0]['original_start']: {'start_at':'2026-01-05T09:00:00+00:00'}})
    assert changed[0]['start_at'].hour == 9
    assert changed[1:] == rows[1:]
