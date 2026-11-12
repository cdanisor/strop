"""
Regression tests for the scheduling / valve safety / weather fixes.
Everything runs in GPIO simulation mode against a temporary database.
"""
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.database import Database
from src.services.cron_utils import (build_trigger, convert_dow, next_run_times,
                                     validate_cron, CronValidationError)
from src.services.gpio_control_service import GPIOControlService, MAX_DURATION_SECONDS
from src.services.valve_cron_scheduler import ValveCronScheduler
from src.services.weather.weather_service import WeatherService

# Thursday 12 Nov 2026, 10:00 local time
THURSDAY = datetime(2026, 11, 12, 10, 0)


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Database(path)
    os.remove(path)


@pytest.fixture
def gpio(db):
    service = GPIOControlService({'gpio': {}}, db)
    assert service.is_simulation_mode
    yield service
    service.cleanup()


class FakeMain:
    """Minimal stand-in for MainService used by the scheduler."""

    def __init__(self, gpio):
        self.gpio = gpio
        self.calls = []

    def activate_valve(self, valve_id, duration=None, meta=None):
        self.calls.append((valve_id, duration))
        return self.gpio.activate_valve(valve_id, duration, meta)

    def get_valve_status(self, valve_id):
        return self.gpio.get_valve_status(valve_id)


@pytest.fixture
def scheduler(db, gpio):
    sched = ValveCronScheduler()
    main = FakeMain(gpio)
    sched.start(db, main)
    yield sched, main
    sched.stop()


# ----------------------------------------------------------------- cron parsing
@pytest.mark.parametrize("dow,expected_day", [
    ("1", "Monday"), ("2", "Tuesday"), ("4", "Thursday"), ("5", "Friday"),
    ("6", "Saturday"), ("0", "Sunday"), ("7", "Sunday"), ("mon", "Monday"),
])
def test_weekday_uses_standard_cron_numbering(dow, expected_day):
    first = next_run_times(f"0 6 * * {dow}", 1, now=THURSDAY)[0]
    assert first.strftime("%A") == expected_day


def test_production_schedules_run_on_the_selected_day():
    # Valve 1 "Thursday 05:35" used to run on Friday, valve 2 "Tuesday" on Wednesday
    assert next_run_times("35 5 * * 4", 1, now=THURSDAY - timedelta(hours=5))[0].strftime("%A") == "Thursday"
    assert next_run_times("15 6 * * 2", 1, now=THURSDAY)[0].strftime("%A") == "Tuesday"


@pytest.mark.parametrize("field,days", [
    ("1-5", {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}),
    ("1,3,5", {"Monday", "Wednesday", "Friday"}),
    ("6-0", {"Saturday", "Sunday"}),
    ("0-6", {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}),
    ("*/2", {"Sunday", "Tuesday", "Thursday", "Saturday"}),
    ("1-7", {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}),
])
def test_weekday_ranges_lists_steps(field, days):
    runs = next_run_times(f"0 6 * * {field}", 14, now=THURSDAY)
    assert {r.strftime("%A") for r in runs} == days


@pytest.mark.parametrize("expr", [
    "", "   ", "6 * * *", " 6 * * *", "0 6 * * * *",      # wrong field count
    "* 6 * * *", "*/5 6 * * *", "0-30 6 * * *",          # would fire every minute
    "0 25 * * *", "61 6 * * *", "0 6 * * 8", "0 6 * * x", "0 6 * * 1,",
])
def test_invalid_expressions_are_rejected(expr):
    with pytest.raises(CronValidationError):
        validate_cron(expr)


def test_trigger_fires_once_per_day_not_every_second():
    runs = next_run_times("30 6 * * *", 3, now=THURSDAY)
    assert [(r - runs[0]).total_seconds() for r in runs] == [0, 86400, 172800]


def test_convert_dow_names_are_unambiguous():
    assert convert_dow("0") == "sun"
    assert convert_dow("1-5") == "mon,tue,wed,thu,fri"
    assert convert_dow("*") == "*"


# ----------------------------------------------------------------- scheduler
def test_disabled_schedule_has_no_job_at_startup(db, gpio):
    # Same state as production: both schedules saved but disabled
    db.update_valve_cron(1, "35 5 * * 4", False)
    db.update_valve_cron_duration(1, 300)
    db.update_valve_cron(2, "15 6 * * 2", False)
    sched = ValveCronScheduler()
    sched.start(db, FakeMain(gpio))
    try:
        assert not sched.has_job(1) and not sched.has_job(2)
        assert db.get_valve_cron(1)['next_run'] is None
    finally:
        sched.stop()


def test_disabling_removes_running_job(scheduler, db):
    sched, _ = scheduler
    db.update_valve_cron(1, "0 6 * * 1", True)
    assert sched.reload_valve(1) is True and sched.has_job(1)

    db.update_valve_cron(1, "0 6 * * 1", False)
    assert sched.reload_valve(1) is False
    assert not sched.has_job(1)


def test_scheduled_run_rechecks_db_and_skips_disabled(scheduler, db, gpio):
    sched, main = scheduler
    db.update_valve_cron(1, "0 6 * * 1", False)
    sched._run_valve_activation(valve_id=1)
    assert main.calls == []
    assert gpio.get_valve_status(1) is False


def test_scheduled_run_uses_current_duration_from_db(scheduler, db, gpio):
    sched, main = scheduler
    db.update_valve_cron(2, "0 6 * * 1", True)
    db.update_valve_cron_duration(2, 1800)
    sched.reload_valve(2)
    db.update_valve_cron_duration(2, 300)  # changed after the job was created
    sched._run_valve_activation(valve_id=2)
    assert main.calls == [(2, 300)]
    assert db.get_valve_cron(2)['last_run'] is not None
    assert db.get_valve_cron(2)['next_run'] is not None


def test_scheduled_run_skips_valve_already_open(scheduler, db, gpio):
    sched, main = scheduler
    db.update_valve_cron(1, "0 6 * * 1", True)
    sched.reload_valve(1)
    gpio.activate_valve(1, 600)
    sched._run_valve_activation(valve_id=1)
    assert main.calls == []
    opened = [l for l in db.get_valve_logs(1) if l['status'] == 'Opened']
    assert len(opened) == 1


def test_invalid_expression_in_db_is_not_scheduled(scheduler, db):
    sched, _ = scheduler
    db.update_valve_cron(1, "6 * * *", True)  # 4 fields: used to fire every second
    assert sched.reload_valve(1) is False
    assert not sched.has_job(1)


def test_scheduler_job_and_display_agree_on_day(scheduler, db):
    sched, _ = scheduler
    db.update_valve_cron(1, "35 5 * * 4", True)
    sched.reload_valve(1)
    job_day = sched.scheduler.get_job("valve_1_cron").next_run_time.strftime("%A")
    shown_day = next_run_times("35 5 * * 4", 1)[0].strftime("%A")
    assert job_day == shown_day == "Thursday"


# ----------------------------------------------------------------- GPIO safety
def test_zero_or_missing_duration_still_gets_a_timer(gpio):
    assert gpio.activate_valve(1, 0)
    assert gpio.active_timers[1].interval == MAX_DURATION_SECONDS
    gpio.deactivate_valve(1, manual=True)
    assert gpio.activate_valve(2, None)
    assert gpio.active_timers[2].interval == MAX_DURATION_SECONDS


def test_duration_is_capped(gpio):
    gpio.activate_valve(1, 99999)
    assert gpio.active_timers[1].interval == MAX_DURATION_SECONDS


def test_second_activation_is_refused(gpio, db):
    assert gpio.activate_valve(1, 60) is True
    assert gpio.activate_valve(1, 60) is False
    assert sum(1 for l in db.get_valve_logs(1) if l['status'] == 'Opened') == 1


def test_timer_closes_valve_and_finishes_log(gpio, db):
    gpio.activate_valve(1, 1)
    time.sleep(1.6)
    assert gpio.get_valve_status(1) is False
    log = db.get_valve_logs(1)[0]
    assert log['status'] == 'Finished' and log['duration'] in (1, 2)


def test_manual_stop_updates_same_log(gpio, db):
    gpio.activate_valve(2, 600)
    gpio.deactivate_valve(2, manual=True)
    logs = db.get_valve_logs(2)
    assert len(logs) == 1 and logs[0]['status'] == 'Manually Stopped'
    assert 2 not in gpio.active_timers


def test_cleanup_closes_open_valves(db):
    service = GPIOControlService({'gpio': {}}, db)
    service.activate_valve(1, 600)
    service.cleanup()
    assert db.get_valve_logs(1)[0]['status'] == 'Terminated'


# ----------------------------------------------------------------- database
def test_terminated_duration_is_capped_after_crash(db):
    start = datetime.now() - timedelta(days=2)
    db.insert_valve_log(1, 'Opened', None, start)
    assert db.check_and_terminate_opened_records() == 1
    log = db.get_valve_logs(1)[0]
    assert log['status'] == 'Terminated' and log['duration'] == 3600


def test_insert_valve_log_returns_id(db):
    first = db.insert_valve_log(1, 'Opened')
    second = db.insert_valve_log(1, 'Opened')
    assert first and second == first + 1


# ----------------------------------------------------------------- weather
def test_weather_averages_are_not_halved():
    base = int(datetime(2026, 11, 12, 9, 0).timestamp())
    data = {'list': [
        {'dt': base + i * 10800,
         'main': {'temp': 10 + i, 'temp_min': 9 + i, 'temp_max': 11 + i, 'humidity': 80, 'pressure': 1013},
         'weather': [{'description': 'light rain'}], 'rain': {'3h': 0.5}}
        for i in range(4)
    ]}
    with patch.object(WeatherService, '__init__', lambda self: None):
        day = WeatherService()._group_forecast_by_day(data)[0]
    assert day['average_humidity'] == 80
    assert day['average_pressure'] == 1013
    assert day['total_rain'] == pytest.approx(2.0)
    assert day['temperature_minimum'] == 9 and day['temperature_maximum'] == 14


def test_halved_weather_rows_are_corrected_once():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        Database(path)
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO weather_data (timestamp, date, average_humidity, average_pressure) "
                     "VALUES ('2026-11-01', '2026-11-01', 41, 506), ('2026-11-02', '2026-11-02', 80, 1013)")
        conn.commit()
        conn.close()
        Database(path)
        Database(path)  # second init must not double again
        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT date, average_humidity, average_pressure FROM weather_data ORDER BY date").fetchall()
        conn.close()
        assert rows == [('2026-11-01', 82, 1012), ('2026-11-02', 80, 1013)]
    finally:
        os.remove(path)
