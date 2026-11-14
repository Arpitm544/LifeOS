from datetime import date, time
from zoneinfo import ZoneInfo


def validate_preference(key, value):
    if key == 'timezone':
        ZoneInfo(value['name'])
    elif key in {'work_hours', 'quiet_hours'}:
        for field in ('start', 'end'):
            parsed = time.fromisoformat(value[field])
            if parsed.tzinfo or parsed.second or len(value[field]) != 5:
                raise ValueError('Use HH:MM local times')
        if value['start'] == value['end']:
            raise ValueError('Time range must have positive duration')
        if key == 'work_hours' and value['start'] >= value['end']:
            raise ValueError('Working hours must end after they start')
    elif key == 'focus_windows':
        if not isinstance(value['windows'], list) or len(value['windows']) > 4:
            raise ValueError('Provide at most four focus windows')
        for start, end in value['windows']:
            validate_preference('work_hours', {'start': start, 'end': end})
    elif key == 'reminder_lead':
        if type(value['minutes']) is not int or not 0 <= value['minutes'] <= 1440:
            raise ValueError('Lead must be 0–1440 minutes')
    elif key == 'estimate_padding':
        # Plan with calibrated effort (estimate x measured factor) when enabled.
        if type(value['enabled']) is not bool:
            raise ValueError('enabled must be true or false')
    elif key == 'work_hours_overrides':
        # Per local date working hours, e.g. one evening extended by Capacity Guard.
        dates = value['dates']
        if not isinstance(dates, dict) or len(dates) > 31:
            raise ValueError('Provide at most 31 dated overrides')
        for day, hours in dates.items():
            date.fromisoformat(day)
            validate_preference('work_hours', hours)
    elif key == 'demo_data':
        raise ValueError('Demo metadata is set only by the seed script')
    else:
        raise ValueError('Unknown preference key')
    return value
