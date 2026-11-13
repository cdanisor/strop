"""
Several schedules per zone, with validation that runs of a zone never overlap.
"""
import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

from conftest import login
from src.database import Database
from src.services.cron_utils import CronValidationError, find_overlap, validate_schedule_fields
from src.services.valve_cron_scheduler import ValveCronScheduler, find_schedule_conflict


# ----------------------------------------------------------------- overlap detection
@pytest.mark.parametrize('a, a_sec, b, b_sec, expected', [
    ('0 6 * * 1,3,5', 1800, '0 18 * * 1,3,5', 1800, None),          # morning / evening
    ('0 6 * * 1,3,5', 1800, '20 6 * * 5', 600, (4, '06:20')),       # Friday 06:20
    ('0 6 * * 1', 1800, '20 6 * * 2', 600, None),                    # different days
    ('0 6 * * *', 1800, '30 6 * * *', 600, None),                    # back to back is fine
    ('0 6 * * *', 1801, '30 6 * * *', 600, (None, '06:30')),         # one second too long
    ('50 23 * * 1', 1800, '5 0 * * 2', 600, (1, '00:05')),           # spills past midnight
    ('50 23 * * 1', 1800, '5 0 * * 1', 600, None),                   # ... but not backwards
    ('0 6 * * 0', 1800, '0 6 * * 7', 600, (6, '06:00')),             # 0 and 7 are Sunday
    ('0 6 1 * *', 1800, '10 6 * * 1', 600, (0, '06:10')),            # only a Monday the 1st
    ('0 6 * 1-3 *', 1800, '0 6 * 4-12 *', 1800, None),               # different months
])
def test_find_overlap(a, a_sec, b, b_sec, expected):
    at = find_overlap(a, a_sec, b, b_sec)
    if expected is None:
        assert at is None
    else:
        weekday, hhmm = expected
        assert at.strftime('%H:%M') == hhmm
        if weekday is not None:
            assert at.weekday() == weekday
    # symmetric
    assert (find_overlap(b, b_sec, a, a_sec) is None) == (expected is None)


def test_schedule_overlapping_itself():
    assert find_overlap('0 6,7 * * *', 3600) is None
    assert find_overlap('0 6,7 * * *', 3601).strftime('%H:%M') == '07:00'
    assert find_overlap('0,30 6 * * *', 1800) is None
    assert find_overlap('0 */1 * * *', 3600) is None


def test_unsupported_syntax_rejected():
    with pytest.raises(CronValidationError):
        validate_schedule_fields('0 6 L * *')
    validate_schedule_fields('0 6-8/2 1-15 */2 mon-fri')


# ----------------------------------------------------------------- database + scheduler
@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield Database(path)
    os.remove(path)


def test_migration_drops_empty_rows(db):
    conn = sqlite3.connect(db.db_path)
    conn.execute("INSERT INTO valve_cron (valve_id, cron_expression, enabled, duration) VALUES (1, '', 0, 300)")
    conn.execute("INSERT INTO valve_cron (valve_id, cron_expression, enabled, duration) VALUES (2, '0 6 * * 1', 1, 300)")
    conn.execute("INSERT INTO valve_cron (valve_id, cron_expression, enabled, duration) VALUES (2, '0 6 * * 1', 1, 300)")
    conn.execute('PRAGMA user_version = 1')
    conn.commit()
    conn.close()
    Database(db.db_path)
    assert [(s['valve_id'], s['cron_expression']) for s in db.list_schedules()] == [(2, '0 6 * * 1')]


def test_conflict_ignores_disabled_and_self(db):
    first = db.create_schedule(1, '0 6 * * *', 1800, True)
    db.create_schedule(1, '10 6 * * *', 600, False)          # disabled: ignored
    db.create_schedule(2, '10 6 * * *', 600, True)           # other zone: ignored
    assert find_schedule_conflict(db, 1, '0 6 * * *', 1800, exclude_id=first) is None
    conflict = find_schedule_conflict(db, 1, '15 6 * * 3', 300)
    assert conflict['schedule_id'] == first and conflict['weekday'] == 2 and conflict['time'] == '06:15'


def test_scheduler_runs_each_schedule(db):
    calls = []
    main = type('M', (), {'get_valve_status': lambda self, v: False,
                          'activate_valve': lambda self, v, d, meta=None: calls.append((v, d)) or True})()
    sched = ValveCronScheduler()
    sched.start(db, main)
    try:
        morning = db.create_schedule(1, '0 6 * * *', 600, True)
        evening = db.create_schedule(1, '0 19 * * *', 300, True)
        db.create_schedule(1, '0 12 * * *', 900, False)
        sched.reload_valve(1)
        assert sorted(j.kwargs['schedule_id'] for j in sched._jobs_of_valve(1)) == [morning, evening]
        with patch.object(sched.adjuster, 'plan', side_effect=lambda base, day: {
                'skip': False, 'duration': base, 'percent': 100, 'reason': '', 'reason_key': 'normal',
                'reason_args': {}}):
            sched._run_valve_activation(valve_id=1, schedule_id=evening)
            sched._run_valve_activation(valve_id=1, schedule_id=morning)
            # a job left for a deleted schedule does nothing
            db.delete_schedule(morning)
            sched._run_valve_activation(valve_id=1, schedule_id=morning)
        assert calls == [(1, 300), (1, 600)]
        assert db.get_schedule(evening)['last_run'] is not None
        sched.reload_valve(1)
        assert [j.kwargs['schedule_id'] for j in sched._jobs_of_valve(1)] == [evening]
    finally:
        sched.stop()


# ----------------------------------------------------------------- API
@pytest.fixture(scope='module')
def client():
    from src.main_service import main_service
    from src.api.api_service import api_service
    with patch('src.services.weather.weather_service.WeatherService.update_weather_data', return_value=True), \
         patch('src.services.weather.cron_scheduler.CronScheduler.start'):
        if not main_service.is_running:
            assert main_service.initialize()
    yield login(api_service.app.test_client())


@pytest.fixture
def zone(client):
    """Zone 2 without schedules before and after each test."""
    client.delete('/api/valves/2/cron')
    yield 2
    client.delete('/api/valves/2/cron')


def test_api_multiple_schedules(client, zone):
    from src.main_service import main_service
    r = client.post(f'/api/valves/{zone}/schedules',
                    json={'cron_expression': '0 6 * * 1,3,5', 'duration': 900})
    assert r.status_code == 201
    morning = r.get_json()['schedule']
    assert morning['enabled'] is True and morning['duration'] == 900
    r = client.post(f'/api/valves/{zone}/schedules',
                    json={'cron_expression': '0 19 * * 1,3,5', 'duration': 600})
    assert r.status_code == 201
    evening = r.get_json()['schedule']

    listed = client.get(f'/api/valves/{zone}/schedules').get_json()['schedules']
    assert [s['id'] for s in listed] == [morning['id'], evening['id']]
    assert len(main_service.valve_scheduler._jobs_of_valve(zone)) == 2

    v = next(v for v in client.get('/api/dashboard').get_json()['valves'] if v['id'] == zone)
    assert [s['id'] for s in v['schedules']] == [morning['id'], evening['id']]
    assert v['schedule']['enabled'] is True and v['schedule']['count'] == 2
    planned = v['schedule']['planned']
    assert planned == sorted(planned, key=lambda p: p['at'])
    assert {p['schedule_id'] for p in planned} == {morning['id'], evening['id']}
    hours = {datetime.fromisoformat(p['at']).hour for p in planned}
    assert hours == {6, 19}


def test_api_rejects_overlap(client, zone):
    first = client.post(f'/api/valves/{zone}/schedules',
                        json={'cron_expression': '0 6 * * 1,3,5', 'duration': 1800}).get_json()['schedule']
    r = client.post(f'/api/valves/{zone}/schedules', json={'cron_expression': '15 6 * * 3', 'duration': 600})
    assert r.status_code == 400
    body = r.get_json()
    assert body['code'] == 'schedule_overlap'
    assert body['conflict']['schedule_id'] == first['id'] and body['conflict']['time'] == '06:15'
    assert body['conflict']['weekday'] == 2

    # disabled schedules may overlap, but cannot be turned on
    r = client.post(f'/api/valves/{zone}/schedules',
                    json={'cron_expression': '15 6 * * 3', 'duration': 600, 'enabled': False})
    assert r.status_code == 201
    other = r.get_json()['schedule']
    r = client.put(f"/api/schedules/{other['id']}", json={'enabled': True})
    assert r.status_code == 400 and r.get_json()['code'] == 'schedule_overlap'

    # moving it away makes it valid
    r = client.put(f"/api/schedules/{other['id']}", json={'cron_expression': '0 20 * * 3', 'enabled': True})
    assert r.status_code == 200 and r.get_json()['schedule']['enabled'] is True

    # editing a schedule is not compared with itself
    r = client.put(f"/api/schedules/{first['id']}", json={'duration': 1500})
    assert r.status_code == 200

    # a schedule overlapping itself
    r = client.post(f'/api/valves/{zone}/schedules', json={'cron_expression': '0 9,10 * * 6', 'duration': 3600})
    assert r.status_code == 201
    r = client.post(f'/api/valves/{zone}/schedules', json={'cron_expression': '0 11,12 * * 6', 'duration': 3601})
    assert r.status_code == 400


def test_api_other_zone_may_overlap(client, zone):
    client.delete('/api/valves/1/cron')
    try:
        assert client.post('/api/valves/1/schedules',
                           json={'cron_expression': '0 6 * * *', 'duration': 600, 'enabled': False}).status_code == 201
        assert client.post(f'/api/valves/{zone}/schedules',
                           json={'cron_expression': '0 6 * * *', 'duration': 600}).status_code == 201
    finally:
        client.delete('/api/valves/1/cron')


def test_api_zone_toggle_and_delete(client, zone):
    from src.main_service import main_service
    a = client.post(f'/api/valves/{zone}/schedules',
                    json={'cron_expression': '0 6 * * *', 'duration': 600}).get_json()['schedule']
    b = client.post(f'/api/valves/{zone}/schedules',
                    json={'cron_expression': '0 20 * * *', 'duration': 600}).get_json()['schedule']
    assert client.post(f'/api/valves/{zone}/schedules/enabled', json={'enabled': False}).status_code == 200
    assert not main_service.valve_scheduler.has_job(zone)
    assert client.post(f'/api/valves/{zone}/schedules/enabled', json={'enabled': True}).status_code == 200
    assert len(main_service.valve_scheduler._jobs_of_valve(zone)) == 2

    assert client.delete(f"/api/schedules/{a['id']}").status_code == 200
    assert client.delete(f"/api/schedules/{a['id']}").status_code == 404
    assert [j.kwargs['schedule_id'] for j in main_service.valve_scheduler._jobs_of_valve(zone)] == [b['id']]

    # turning everything on stops at the first overlap
    client.post(f'/api/valves/{zone}/schedules/enabled', json={'enabled': False})
    client.post(f'/api/valves/{zone}/schedules',
                json={'cron_expression': '5 20 * * *', 'duration': 600, 'enabled': False})
    r = client.post(f'/api/valves/{zone}/schedules/enabled', json={'enabled': True})
    assert r.status_code == 400 and r.get_json()['code'] == 'schedule_overlap'


@pytest.mark.parametrize('body', [
    {'cron_expression': '* 6 * * *', 'duration': 600},        # every minute
    {'cron_expression': '0 6 L * *', 'duration': 600},        # unsupported syntax
    {'cron_expression': '0 6 * * *', 'duration': 0},
    {'cron_expression': '0 6 * * *', 'duration': 3601},
    {'cron_expression': '0 6 * * *', 'duration': '600'},
    {'cron_expression': '0 6 * * *', 'duration': 600, 'enabled': 'yes'},
    {'duration': 600},
])
def test_api_schedule_validation(client, zone, body):
    assert client.post(f'/api/valves/{zone}/schedules', json=body).status_code == 400


def test_api_schedule_limit(client, zone):
    for h in range(8):
        assert client.post(f'/api/valves/{zone}/schedules',
                           json={'cron_expression': f'0 {h * 2} * * *', 'duration': 60}).status_code == 201
    r = client.post(f'/api/valves/{zone}/schedules', json={'cron_expression': '0 23 * * *', 'duration': 60})
    assert r.status_code == 400 and r.get_json()['code'] == 'too_many_schedules'


def test_api_schedules_require_auth():
    from src.api.api_service import api_service
    anon = api_service.app.test_client()
    assert anon.get('/api/valves/1/schedules').status_code == 401
    assert anon.post('/api/valves/1/schedules', json={'cron_expression': '0 6 * * *', 'duration': 60}).status_code == 401
    assert anon.put('/api/schedules/1', json={'enabled': True}).status_code == 401
    assert anon.delete('/api/schedules/1').status_code == 401
