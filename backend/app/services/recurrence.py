from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from dateutil.rrule import rrulestr


def expand_routine(rule, start_time, duration_min, anchor, window_start, window_end, timezone_name, overrides=None):
    if window_end <= window_start or window_end - window_start > timedelta(days=31):
        raise ValueError('Expansion window must be positive and at most 31 days')
    tz = ZoneInfo(timezone_name)
    clock = time.fromisoformat(start_time)
    base = datetime.combine(anchor, clock, tzinfo=tz)
    recurrence = rrulestr(rule, dtstart=base)
    output = []
    for start in recurrence.xafter(window_start.astimezone(tz), count=501, inc=True):
        if start >= window_end:
            break
        if len(output) >= 500:
            raise ValueError('Too many instances in expansion window')
        # Skip nonexistent wall times in DST transitions.
        if start.astimezone(timezone.utc).astimezone(tz).replace(fold=start.fold) != start:
            continue
        key = start.astimezone(timezone.utc).isoformat()
        change = (overrides or {}).get(key, {})
        if change.get('cancelled'):
            continue
        begin = datetime.fromisoformat(change['start_at']) if change.get('start_at') else start
        end = begin.astimezone(timezone.utc) + timedelta(minutes=change.get('duration_min', duration_min))
        output.append({'original_start': key, 'start_at': begin.astimezone(timezone.utc),
                       'end_at': end.astimezone(timezone.utc)})
    return output
