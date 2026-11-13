"""
End-to-end API tests in simulation mode: real MainService (GPIO simulated,
valve scheduler running) against the temporary DB from conftest.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from src.main_service import main_service
from src.api.api_service import api_service


@pytest.fixture(scope="module")
def client():
    with patch('src.services.weather.weather_service.WeatherService.update_weather_data', return_value=True), \
         patch('src.services.weather.cron_scheduler.CronScheduler.start'):
        assert main_service.initialize()
    from conftest import login
    yield login(api_service.app.test_client())
    main_service.cleanup()


@pytest.fixture(autouse=True)
def close_valves(client):
    yield
    for valve_id in (1, 2):
        if main_service.get_valve_status(valve_id):
            main_service.deactivate_valve(valve_id, manual=True)


def test_activate_without_body_uses_default(client):
    r = client.post('/api/valves/1/activate')
    assert r.status_code == 200, r.get_json()
    assert main_service.gpio_service.active_timers[1].interval == 60


def test_activate_zero_duration_rejected(client):
    r = client.post('/api/valves/1/activate', json={'duration': 0})
    assert r.status_code == 400
    assert main_service.get_valve_status(1) is False


def test_activate_duration_capped(client):
    r = client.post('/api/valves/2/activate', json={'duration': 7200})
    assert r.status_code == 200
    assert main_service.gpio_service.active_timers[2].interval == 3600


def test_activate_twice_rejected(client):
    assert client.post('/api/valves/1/activate', json={'duration': 60}).status_code == 200
    assert client.post('/api/valves/1/activate', json={'duration': 60}).status_code == 400


@pytest.mark.parametrize("expr", ["6 * * *", " 6 * * *", "* 6 * * *", "0 6 * * 9", ""])
def test_invalid_cron_rejected(client, expr):
    r = client.post('/api/valves/1/cron', json={'cron_expression': expr, 'duration': 300, 'enabled': True})
    assert r.status_code == 400
    assert not main_service.valve_scheduler.has_job(1)


def test_invalid_cron_duration_rejected(client):
    r = client.post('/api/valves/1/cron', json={'cron_expression': '0 6 * * 1', 'duration': 0, 'enabled': True})
    assert r.status_code == 400


def test_enable_then_disable_schedule(client):
    r = client.post('/api/valves/1/cron', json={'cron_expression': '35 5 * * 4', 'duration': 300, 'enabled': True})
    assert r.status_code == 200
    assert main_service.valve_scheduler.has_job(1)

    runs = client.get('/api/valves/next_run').get_json()['next_runs']
    v1 = next(r for r in runs if r['valve_id'] == 1)['next_runs']
    assert len(v1) == 5
    assert all(datetime.fromisoformat(x).strftime('%A') == 'Thursday' for x in v1)
    job_time = main_service.valve_scheduler._jobs_of_valve(1)[0].next_run_time
    assert datetime.fromisoformat(v1[0]) == job_time

    r = client.post('/api/valves/1/cron', json={'cron_expression': '35 5 * * 4', 'duration': 300, 'enabled': False})
    assert r.status_code == 200
    assert not main_service.valve_scheduler.has_job(1)
    runs = client.get('/api/valves/next_run').get_json()['next_runs']
    assert all(r['valve_id'] != 1 for r in runs)
    cron = client.get('/api/valves/1/cron').get_json()['cron']
    assert cron['enabled'] is False and cron['next_run'] is None


def test_delete_schedule(client):
    client.post('/api/valves/2/cron', json={'cron_expression': '15 6 * * 2', 'duration': 300, 'enabled': True})
    assert main_service.valve_scheduler.has_job(2)
    r = client.delete('/api/valves/2/cron')
    assert r.status_code == 200
    assert not main_service.valve_scheduler.has_job(2)
    # clearing the legacy single schedule deletes the zone's schedules
    assert client.get('/api/valves/2/cron').get_json()['cron'] is None


def test_forecast_endpoint_no_longer_crashes(client):
    from src.database import Database
    db = Database()
    db.insert_weather_data({'date': datetime.now().date().isoformat(), 'temperature_minimum': 5,
                            'temperature_maximum': 12, 'average_humidity': 80,
                            'average_pressure': 1013, 'description': 'clear sky', 'total_rain': 0})
    r = client.get('/api/weather/forecast')
    assert r.status_code == 200
    assert r.get_json()['forecast'][0]['average_humidity'] == 80


def test_dashboard_reports_state_schedule_and_remaining(client):
    client.post('/api/valves/1/cron', json={'cron_expression': '30 7 * * 6', 'duration': 300, 'enabled': True})
    client.post('/api/valves/2/activate', json={'duration': 120})
    d = client.get('/api/dashboard').get_json()
    v1, v2 = d['valves']
    assert v1['id'] == 1 and v1['open'] is False
    assert v1['schedule']['enabled'] is True and len(v1['schedule']['next_runs']) == 5
    assert all(datetime.fromisoformat(r).strftime('%A') == 'Saturday' for r in v1['schedule']['next_runs'])
    assert v2['open'] is True and v2['duration'] == 120 and 115 <= v2['remaining'] <= 120
    assert v2['history'][0]['status'] == 'Opened'
    assert set(d['usage']) == {'1', '2'}
    assert 'weather' in d and 'server_time' in d


def test_dashboard_shows_set_and_adjusted_duration(client):
    from datetime import date, timedelta
    from src.database import Database
    db = Database()
    for o in range(-2, 8):
        d = (date.today() + timedelta(days=o)).isoformat()
        db.insert_weather_data({'date': d, 'temperature_minimum': 9, 'temperature_maximum': 19,
                                'average_humidity': 70, 'average_pressure': 1013,
                                'description': 'clear sky', 'total_rain': 0})
    client.post('/api/valves/1/cron', json={'cron_expression': '30 7 * * *', 'duration': 600, 'enabled': True})
    d = client.get('/api/dashboard').get_json()
    plan = d['valves'][0]['schedule']['planned'][0]
    assert plan['base_duration'] == 600 and plan['percent'] == 56 and plan['duration'] == 340
    assert plan['skip'] is False and plan['reason'] == 'cool, humid'
    assert d['adjustment']['percent'] == 56
    assert d['adjustment']['terms']['temp'] < 0 and d['adjustment']['settings']['base_temp'] == 22.0
