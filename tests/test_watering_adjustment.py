"""
Tests for the weather-based watering adjustment (formula, skips, scheduler
integration and slot-based daily weather aggregation).
"""
import os
import tempfile
from datetime import date, datetime, timedelta

import pytest

from src.database import Database
from src.services.gpio_control_service import GPIOControlService
from src.services.valve_cron_scheduler import ValveCronScheduler
from src.services.watering_adjustment import compute_adjustment, adjusted_seconds, WateringAdjuster, decode_note
from src.services.weather.weather_service import WeatherService

RUN = date(2026, 7, 15)


def weather(days):
    """days: {offset: (tmin, tmax, humidity, rain)} relative to RUN."""
    out = {}
    for offset, (tmin, tmax, hum, rain) in days.items():
        d = (RUN + timedelta(days=offset)).isoformat()
        out[d] = {'date': d, 'temperature_minimum': tmin, 'temperature_maximum': tmax,
                  'average_humidity': hum, 'total_rain': rain}
    return out


def dry(tmin, tmax, hum):
    return weather({o: (tmin, tmax, hum, 0) for o in range(-2, 3)})


def test_baseline_day_is_full_duration():
    adj = compute_adjustment(dry(16, 28, 55), RUN)  # mean 22 C, 55 %
    assert adj['percent'] == 100 and not adj['skip']
    assert adj['reason'] == 'Normal conditions'


def test_hot_dry_summer_never_exceeds_programmed_time():
    adj = compute_adjustment(dry(22, 34, 40), RUN)
    assert adj['percent'] == 100
    assert adjusted_seconds(1800, adj) == 1800


def test_mild_humid_spring_day_reduces():
    adj = compute_adjustment(dry(9, 19, 70), RUN)  # mean 14 C, 70 %
    # 100 + (14-22)*3.6 + (55-70) = 56.2
    assert adj['percent'] == 56
    assert adjusted_seconds(1800, adj) == 1010
    assert adj['reason'] == 'cool, humid'


def test_rain_yesterday_reduces_proportionally():
    w = dry(16, 28, 55)
    w[(RUN - timedelta(days=1)).isoformat()]['total_rain'] = 5.0
    adj = compute_adjustment(w, RUN)
    assert adj['percent'] == round(100 - 5 * 7.87)  # 61
    assert 'rain 5 mm' in adj['reason']


def test_forecast_rain_counts_less_than_past_rain():
    past = dry(16, 28, 55)
    past[(RUN - timedelta(days=1)).isoformat()]['total_rain'] = 4.0
    future = dry(16, 28, 55)
    future[(RUN + timedelta(days=1)).isoformat()]['total_rain'] = 4.0
    assert compute_adjustment(future, RUN)['percent'] > compute_adjustment(past, RUN)['percent']


def test_half_inch_of_rain_skips():
    w = dry(16, 28, 55)
    w[RUN.isoformat()]['total_rain'] = 12.7
    adj = compute_adjustment(w, RUN)
    assert adj['skip'] and adj['percent'] == 0
    assert adj['reason'].startswith('Not needed: rain')


def test_frost_skips_even_when_dry():
    adj = compute_adjustment(dry(1, 15, 40), RUN)
    assert adj['skip'] and adj['reason'].startswith('Frost risk')


def test_cold_dormant_grass_skips():
    adj = compute_adjustment(dry(4, 10, 60), RUN)  # mean 7 C
    assert adj['skip'] and adj['reason'].startswith('Too cold')


def test_tiny_result_is_skipped():
    adj = compute_adjustment(dry(8, 18, 85), RUN)  # mean 13 C, 85 %
    # 100 - 32.4 - 30 = 37.6 -> still runs; add a little rain to push below 20 %
    assert not adj['skip']
    w = dry(8, 18, 85)
    w[RUN.isoformat()]['total_rain'] = 3
    assert compute_adjustment(w, RUN)['skip']


def test_short_adjusted_runs_are_skipped():
    adj = compute_adjustment(dry(9, 19, 70), RUN)  # 56 %
    assert adjusted_seconds(90, adj) == 0      # 50 s < 60 s minimum
    assert adjusted_seconds(600, adj) == 340


def test_missing_weather_keeps_full_duration():
    adj = compute_adjustment({}, RUN)
    assert adj['percent'] == 100 and not adj['skip']
    assert 'No weather data' in adj['reason']


def test_disabled_in_config():
    adj = compute_adjustment(dry(1, 5, 95), RUN, {'enabled': False})
    assert adj['percent'] == 100 and not adj['skip']


def test_config_overrides_baseline():
    adj = compute_adjustment(dry(9, 19, 70), RUN, {'base_temp': 14, 'base_humidity': 70})
    assert adj['percent'] == 100


def test_current_november_weather_skips():
    # Real values around 12-14 Nov 2026 in Bucharest
    w = {
        '2026-11-12': {'date': '2026-11-12', 'temperature_minimum': 9.0, 'temperature_maximum': 15.0,
                       'average_humidity': 87, 'total_rain': 0.0},
        '2026-11-13': {'date': '2026-11-13', 'temperature_minimum': 10.0, 'temperature_maximum': 22.6,
                       'average_humidity': 73, 'total_rain': 3.8},
        '2026-11-14': {'date': '2026-11-14', 'temperature_minimum': 3.3, 'temperature_maximum': 14.2,
                       'average_humidity': 92, 'total_rain': 16.4},
    }
    assert compute_adjustment(w, date(2026, 11, 13))['skip']


# ----------------------------------------------------------------- scheduler integration
@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Database(path)
    os.remove(path)


class FakeMain:
    def __init__(self, gpio):
        self.gpio = gpio
        self.calls = []

    def activate_valve(self, valve_id, duration=None, meta=None):
        self.calls.append((valve_id, duration, meta))
        return self.gpio.activate_valve(valve_id, duration, meta)

    def get_valve_status(self, valve_id):
        return self.gpio.get_valve_status(valve_id)


def store_days(db, days):
    for d in days.values():
        db.insert_weather_data(dict(d, average_pressure=1013, description='clear sky'))


def today_weather(offsets):
    today = date.today()
    out = {}
    for o, (tmin, tmax, hum, rain) in offsets.items():
        d = (today + timedelta(days=o)).isoformat()
        out[d] = {'date': d, 'temperature_minimum': tmin, 'temperature_maximum': tmax,
                  'average_humidity': hum, 'total_rain': rain}
    return out


def test_scheduled_run_uses_adjusted_duration_and_logs_it(db):
    store_days(db, today_weather({o: (9, 19, 70, 0) for o in range(-2, 3)}))  # 56 %
    gpio = GPIOControlService({'gpio': {}}, db)
    main = FakeMain(gpio)
    sched = ValveCronScheduler()
    sched.start(db, main)
    try:
        db.update_valve_cron(1, "0 6 * * *", True)
        db.update_valve_cron_duration(1, 600)
        sched._run_valve_activation(valve_id=1)
        assert main.calls[0][1] == 340
        gpio.deactivate_valve(1)
        log = db.get_valve_logs(1)[0]
        assert log['base_duration'] == 600 and log['adjust_percent'] == 56
        note = decode_note(log['adjust_note'])
        assert note['text'] == 'cool, humid' and note['key'] == 'reduced'
        assert note['args']['factors'] == ['temp', 'humidity']
    finally:
        sched.stop()
        gpio.cleanup()


def test_scheduled_run_skipped_by_weather_is_logged(db):
    store_days(db, today_weather({o: (0, 6, 90, 0) for o in range(-2, 3)}))
    gpio = GPIOControlService({'gpio': {}}, db)
    main = FakeMain(gpio)
    sched = ValveCronScheduler()
    sched.start(db, main)
    try:
        db.update_valve_cron(2, "0 6 * * *", True)
        db.update_valve_cron_duration(2, 600)
        sched._run_valve_activation(valve_id=2)
        assert main.calls == []
        assert gpio.get_valve_status(2) is False
        log = db.get_valve_logs(2)[0]
        assert log['status'] == 'Skipped' and log['base_duration'] == 600
        note = decode_note(log['adjust_note'])
        assert note['key'] == 'frost' and note['text'].startswith('Frost risk')
        assert db.get_valve_cron(2)['last_run'] is not None
    finally:
        sched.stop()
        gpio.cleanup()


def test_adjuster_plan_reports_both_durations(db):
    store_days(db, today_weather({o: (9, 19, 70, 0) for o in range(-2, 3)}))
    plan = WateringAdjuster(db).plan(300, date.today())
    assert plan['base_duration'] == 300 and plan['duration'] == 170 and plan['percent'] == 56


# ----------------------------------------------------------------- weather slots
def _item(dt, temp, rain=0.0):
    return {'dt': int(dt.timestamp()), 'main': {'temp': temp, 'temp_min': temp, 'temp_max': temp,
                                                 'humidity': 70, 'pressure': 1010},
            'weather': [{'description': 'light rain' if rain else 'clear sky'}], 'rain': {'3h': rain}}


def test_daily_totals_keep_slots_from_earlier_updates(db):
    service = WeatherService.__new__(WeatherService)
    service.db = db
    day = datetime.combine(date.today(), datetime.min.time())
    # Morning update: rainy morning slots + afternoon forecast
    service.store_weather_data({'list': [_item(day + timedelta(hours=h), 5 + h, 2.0 if h < 9 else 0)
                                         for h in (0, 3, 6, 9, 12, 15, 18, 21)]})
    # Evening update: only the remaining slots of the day are in the API response
    service.store_weather_data({'list': [_item(day + timedelta(hours=21), 6),
                                         _item(day + timedelta(hours=24), 4)]})
    row = {r['date']: r for r in db.get_all_daily_weather_data()}[date.today().isoformat()]
    assert row['total_rain'] == pytest.approx(6.0)        # morning rain kept
    assert row['temperature_minimum'] == 5                  # 00:00 slot kept
    assert row['temperature_maximum'] == 23                 # 18:00 slot kept


def test_reason_keys_for_translation():
    assert compute_adjustment(dry(1, 15, 40), RUN)['reason_key'] == 'frost'
    assert compute_adjustment(dry(4, 10, 60), RUN)['reason_args'] == {'temp': 7}
    w = dry(16, 28, 55)
    w[RUN.isoformat()]['total_rain'] = 12.7
    adj = compute_adjustment(w, RUN)
    assert adj['reason_key'] == 'not_needed' and adj['reason_args'] == {'factor': 'rain', 'rain': 13}
    assert compute_adjustment({}, RUN)['reason_key'] == 'no_data'


def test_decode_note_accepts_plain_text():
    assert decode_note('old free text') == {'key': None, 'args': {}, 'text': 'old free text'}
    assert decode_note(None)['text'] == ''


def test_run_beyond_forecast_is_pending_not_no_data():
    """A run further away than the forecast reaches is 'pending', not 'no data'."""
    from datetime import date, timedelta
    from src.services.watering_adjustment import compute_adjustment
    today = date(2026, 11, 12)
    weather = {(today + timedelta(days=o)).isoformat(): {
        'temperature_minimum': 10, 'temperature_maximum': 20, 'average_humidity': 60, 'total_rain': 0}
        for o in range(-3, 6)}
    far = compute_adjustment(weather, today + timedelta(days=7))
    assert far['reason_key'] == 'pending' and far['pending'] and far['percent'] == 100 and not far['skip']
    assert far['reason_args'] == {'until': '2026-11-17'}
    near = compute_adjustment(weather, today + timedelta(days=5))
    assert near['reason_key'] != 'pending' and not near['pending']
    assert compute_adjustment({}, today)['reason_key'] == 'no_data'
