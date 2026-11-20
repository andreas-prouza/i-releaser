"""
Filters of the templates (docs/features/web-ui-layout.md#components):

    {{ deployment.create_time | datetime }}   2026-11-16 18:56:47
    {{ seconds | duration }}                  1.2 s, 42 s, 3 min 10 s, 2 h 5 min
    {{ stage.remote_dir | or_dash }}          – instead of None
"""
from datetime import date, datetime, timedelta


DASH = '–'



def is_empty(value) -> bool:
    return value is None or (isinstance(value, (str, list, tuple, dict, set)) and len(value) == 0) or (isinstance(value, str) and value.strip() == '')



def or_dash(value):
    return DASH if is_empty(value) else value



def format_datetime(value) -> str:
    """Date and time to the second, without microseconds and time zone. Text which is not a time stays as it is."""

    if is_empty(value):
        return DASH

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip())
        except ValueError:
            return value

    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(value, date):
        return value.isoformat()

    return str(value)



def format_duration(value) -> str:
    """Seconds (or a timedelta) as short text"""

    if value is None or value == '':
        return DASH

    try:
        seconds = value.total_seconds() if isinstance(value, timedelta) else float(value)
    except (TypeError, ValueError):
        return str(value)

    if seconds < 0:
        return DASH

    if seconds < 10:
        return f"{seconds:.1f} s"

    if seconds < 60:
        return f"{int(seconds)} s"

    seconds = int(seconds)

    if seconds < 3600:
        minutes, rest = divmod(seconds, 60)
        return f"{minutes} min" if rest == 0 else f"{minutes} min {rest} s"

    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours} h" if minutes == 0 else f"{hours} h {minutes} min"



FILTERS = {
    'datetime': format_datetime,
    'duration': format_duration,
    'or_dash': or_dash,
}
