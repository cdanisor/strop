"""
Cron helpers shared by the valve scheduler and the API.

The UI and the database store standard 5-field crontab expressions
(minute hour day month day_of_week) where day_of_week uses the standard
crontab convention: 0 or 7 = Sunday, 1 = Monday ... 6 = Saturday.

APScheduler 3.x numbers weekdays differently (0 = Monday), and
CronTrigger.from_crontab() does NOT convert, so "1" (Monday) silently
becomes Tuesday. Every place that turns an expression into a trigger must
go through build_trigger() so execution and the next-run display agree.
"""
from datetime import datetime, timedelta
from typing import List, Optional
import re

from apscheduler.triggers.cron import CronTrigger

# Standard crontab weekday numbers -> APScheduler weekday names
_DOW_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
_NAME_TO_NUM = {name: i for i, name in enumerate(_DOW_NAMES)}

# Minute must be a fixed value or a list of fixed values (e.g. "0", "15,45").
# Wildcards or steps in the minute field would open the valve every minute.
_MINUTE_RE = re.compile(r'^\d{1,2}(,\d{1,2})*$')


class CronValidationError(ValueError):
    """Raised when a cron expression cannot be used for a valve schedule."""


def _dow_value(token: str) -> int:
    token = token.strip().lower()
    if token in _NAME_TO_NUM:
        return _NAME_TO_NUM[token]
    if not token.isdigit():
        raise CronValidationError(f"Invalid day of week: '{token}'")
    value = int(token)
    if value < 0 or value > 7:
        raise CronValidationError(f"Day of week out of range (0-7): {value}")
    return value % 7  # 7 is also Sunday


def convert_dow(dow_field: str) -> str:
    """
    Convert a standard crontab day-of-week field to an APScheduler
    day_of_week value, expressed with weekday names so there is no
    numbering ambiguity. Supports *, lists, ranges, steps and names.
    """
    dow_field = dow_field.strip()
    if dow_field in ('*', '?'):
        return '*'

    days = set()
    for part in dow_field.split(','):
        part = part.strip()
        if not part:
            raise CronValidationError("Empty day-of-week entry")
        step = 1
        if '/' in part:
            part, step_str = part.split('/', 1)
            if not step_str.isdigit() or int(step_str) < 1:
                raise CronValidationError(f"Invalid day-of-week step: '{step_str}'")
            step = int(step_str)
        if part == '*':
            start, end = 0, 6
        elif '-' in part:
            start_str, end_str = part.split('-', 1)
            start, end = _dow_value(start_str), _dow_value(end_str)
            if end_str.strip() == '7':
                end = 7  # allow "1-7" meaning Monday..Sunday
        else:
            start = _dow_value(part)
            end = start if step == 1 else 6
        if end < start:
            # Wrap-around range such as "5-1" (Fri..Mon)
            values = list(range(start, 7)) + list(range(0, end + 1))
        else:
            values = list(range(start, end + 1))
        days.update(v % 7 for v in values[::step])

    if not days:
        raise CronValidationError("No days selected")
    # Order Monday..Sunday for readability
    ordered = sorted(days, key=lambda d: (d - 1) % 7)
    return ','.join(_DOW_NAMES[d] for d in ordered)


def build_trigger(cron_expression: str, timezone=None) -> CronTrigger:
    """
    Validate a standard crontab expression and build the APScheduler trigger.

    Raises:
        CronValidationError: if the expression is not usable.
    """
    if not cron_expression or not cron_expression.strip():
        raise CronValidationError("Cron expression is empty")

    parts = cron_expression.split()
    if len(parts) != 5:
        raise CronValidationError(
            f"Cron expression must have 5 fields (minute hour day month day_of_week), got {len(parts)}")

    minute, hour, day, month, dow = parts
    if not _MINUTE_RE.match(minute):
        raise CronValidationError(
            f"Minute must be a fixed value such as 0 or 15,45 (got '{minute}')")

    try:
        kwargs = dict(second=0, minute=minute, hour=hour, day=day, month=month,
                      day_of_week=convert_dow(dow))
        if timezone is not None:
            kwargs['timezone'] = timezone
        return CronTrigger(**kwargs)
    except CronValidationError:
        raise
    except Exception as e:  # APScheduler raises ValueError for bad fields
        raise CronValidationError(f"Invalid cron expression '{cron_expression}': {e}")


def validate_cron(cron_expression: str) -> None:
    """Raise CronValidationError if the expression is invalid."""
    build_trigger(cron_expression)


def next_run_times(cron_expression: str, count: int = 5,
                   now: Optional[datetime] = None, timezone=None) -> List[datetime]:
    """Return the next `count` fire times for the expression."""
    trigger = build_trigger(cron_expression, timezone)
    if now is None:
        now = datetime.now(trigger.timezone)
    elif now.tzinfo is None:
        # Naive datetimes are interpreted as local system time
        now = now.astimezone(trigger.timezone)
    results = []
    previous = None
    current = now
    for _ in range(count):
        fire = trigger.get_next_fire_time(previous, current)
        if fire is None:
            break
        results.append(fire)
        previous = fire
        current = fire + timedelta(seconds=1)
    return results


# ---------------------------------------------------------------------------
# Overlap detection between schedules of the same zone
# ---------------------------------------------------------------------------
_FIELD_RANGES = {'hour': (0, 23), 'day': (1, 31), 'month': (1, 12)}


def _expand_field(text: str, name: str) -> frozenset:
    """Expand a standard crontab field (*, a, a-b, */n, a-b/n, lists) into a set."""
    lo, hi = _FIELD_RANGES[name]
    values = set()
    for part in text.split(','):
        part = part.strip()
        step = 1
        if '/' in part:
            part, step_str = part.split('/', 1)
            if not step_str.isdigit() or int(step_str) < 1:
                raise CronValidationError(f"Invalid {name} step: '{step_str}'")
            step = int(step_str)
        if part in ('*', '?'):
            start, end = lo, hi
        elif re.fullmatch(r'\d{1,2}-\d{1,2}', part):
            start, end = (int(x) for x in part.split('-'))
        elif re.fullmatch(r'\d{1,2}', part):
            start = int(part)
            end = start if step == 1 else hi
        else:
            raise CronValidationError(f"Unsupported {name} value: '{part}'")
        if not (lo <= start <= hi and lo <= end <= hi) or end < start:
            raise CronValidationError(f"{name.capitalize()} out of range ({lo}-{hi}): '{part}'")
        values.update(range(start, end + 1, step))
    return frozenset(values)


class _Pattern:
    """A crontab expression expanded to sets, to test which days/times it fires."""

    def __init__(self, cron_expression: str):
        build_trigger(cron_expression)  # full validation
        minute, hour, day, month, dow = cron_expression.split()
        minutes = sorted(int(m) for m in minute.split(','))
        if any(m > 59 for m in minutes):
            raise CronValidationError("Minute out of range (0-59)")
        self.times = sorted(h * 60 + m for h in _expand_field(hour, 'hour') for m in minutes)
        self.days = _expand_field(day, 'day')
        self.months = _expand_field(month, 'month')
        names = convert_dow(dow)
        # Python weekday(): Monday = 0
        self.weekdays = frozenset(range(7)) if names == '*' else frozenset(
            (_NAME_TO_NUM[n] - 1) % 7 for n in names.split(','))

    def fires_on(self, d) -> bool:
        # APScheduler requires day, month AND weekday to match
        return d.month in self.months and d.day in self.days and d.weekday() in self.weekdays


def validate_schedule_fields(cron_expression: str) -> None:
    """Raise CronValidationError if the expression uses syntax the overlap check can't read."""
    _Pattern(cron_expression)


def find_overlap(first: str, first_seconds: int, second: Optional[str] = None,
                 second_seconds: Optional[int] = None) -> Optional[datetime]:
    """
    First moment where a run of `first` (lasting first_seconds) overlaps a run
    of `second`, or None. Without `second`, checks `first` against itself
    (two start times closer than the duration). Durations are below one day,
    so a run can spill only into the next day.

    The weekday/day/month combination repeats over a 4-year span (with a
    leap day), so checking every distinct combination of "fires yesterday /
    fires today" over that span covers every date.
    """
    from datetime import date as _date
    a = _Pattern(first)
    b = a if second is None else _Pattern(second)
    a_len = max(1, -(-int(first_seconds) // 60))
    b_len = a_len if second is None else max(1, -(-int(second_seconds or 0) // 60))
    same = second is None

    seen = set()
    start = _date(2023, 12, 31)  # so the first day checked is Monday 2024-01-01
    for offset in range(1, 4 * 366 + 1):
        today = start + timedelta(days=offset)
        yesterday = today - timedelta(days=1)
        key = (a.fires_on(yesterday), a.fires_on(today), b.fires_on(yesterday), b.fires_on(today))
        if key in seen:
            continue
        seen.add(key)
        # runs as minute intervals relative to today's midnight
        runs_a = [(t - 1440, t - 1440 + a_len) for t in a.times if key[0]] + \
                 [(t, t + a_len) for t in a.times if key[1]]
        runs_b = [(t - 1440, t - 1440 + b_len) for t in b.times if key[2]] + \
                 [(t, t + b_len) for t in b.times if key[3]]
        for i, (s1, e1) in enumerate(runs_a):
            for j, (s2, e2) in enumerate(runs_b):
                if same and i == j:
                    continue
                if s1 < e2 and s2 < e1 and (s1 >= 0 or s2 >= 0):
                    at = max(s1, s2)
                    return datetime.combine(today, datetime.min.time()) + timedelta(minutes=at)
    return None
