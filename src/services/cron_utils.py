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
