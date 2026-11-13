"""
Tests for integration tokens, webhooks/notifications and the Home Assistant
message texts.
"""
import importlib.util
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conftest import login
from src.database import Database
from src.services.auth_service import AuthService
from src.services.config_service import ConfigService
from src.services.gpio_control_service import GPIOControlService
from src.services.notifier import Notifier


# ----------------------------------------------------------------- helpers
class Receiver:
    """Tiny HTTP server collecting webhook POSTs."""

    def __init__(self):
        received = self.received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                received.append(json.loads(self.rfile.read(length)))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/hook'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def cfg():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w') as f:
        json.dump({'gpio': {}}, f)
    yield ConfigService(path)
    os.remove(path)


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.close()


# ----------------------------------------------------------------- integration tokens
def test_integration_token_lifecycle(cfg):
    auth = AuthService(cfg)
    auth.set_password('password-1')
    token = auth.create_integration_token('home-assistant')
    assert token.startswith('strop_it_') and auth.verify_token(token)
    with open(cfg.config_path) as f:
        assert token not in f.read()                 # only the hash is stored
    auth.set_password('password-2')                   # password change keeps integrations working
    assert auth.verify_token(token)
    assert [t['name'] for t in auth.list_integration_tokens()] == ['home-assistant']
    assert auth.revoke_integration_token('home-assistant')
    assert not auth.verify_token(token)


def test_recreating_token_replaces_old_one(cfg):
    auth = AuthService(cfg)
    first = auth.create_integration_token('home-assistant')
    second = auth.create_integration_token('home-assistant')
    assert not auth.verify_token(first) and auth.verify_token(second)
    assert not auth.verify_token('strop_it_forged')


def test_token_lifetime_is_90_days(cfg):
    assert AuthService(cfg).token_max_age == 90 * 86400


# ----------------------------------------------------------------- notifier
def test_notifier_delivers_events(cfg, receiver):
    notifier = Notifier(cfg)
    notifier.set_webhook('home-assistant', receiver.url)
    notifier.emit('controller_started')
    notifier.valve_event('opened', 1, duration=300, meta={'base_duration': 600, 'adjust_percent': 50})
    notifier.valve_event('closed', 1, duration=300, status='Watchdog Stopped')
    notifier.flush()
    events = [e['event'] for e in receiver.received]
    assert events == ['controller_started', 'run_started', 'run_finished']
    started = receiver.received[1]
    assert started['source'] == 'schedule' and started['percent'] == 50 and started['base_duration'] == 600
    assert receiver.received[2]['status'] == 'watchdog'
    assert 'time' in receiver.received[0]


def test_notifier_without_webhooks_is_silent(cfg):
    Notifier(cfg).emit('controller_started')     # nothing registered: no error


def test_unreachable_webhook_does_not_raise(cfg):
    notifier = Notifier(cfg)
    notifier.set_webhook('dead', 'http://127.0.0.1:9/nowhere')
    notifier.emit('controller_started')
    notifier.flush()


def test_invalid_webhook_url_rejected(cfg):
    with pytest.raises(ValueError):
        Notifier(cfg).set_webhook('x', 'ftp://example')


def test_gpio_emits_open_and_close(cfg):
    events = []
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    gpio = GPIOControlService({'gpio': {}}, Database(path), on_event=lambda k, v, **d: events.append((k, v, d)))
    try:
        gpio.activate_valve(2, 120)
        gpio.deactivate_valve(2, manual=True)
    finally:
        gpio.cleanup()
        os.remove(path)
    assert events[0][0] == 'opened' and events[0][2]['duration'] == 120 and events[0][2]['meta'] is None
    assert events[1][0] == 'closed' and events[1][2]['status'] == 'Manually Stopped'


def test_weather_stale_notified_once():
    from src.services.weather import cron_scheduler as cs
    with patch.object(cs, 'WeatherService'):
        notifier = SimpleNamespace(events=[])
        notifier.emit = lambda e, **d: notifier.events.append((e, d))
        sched = cs.CronScheduler(notifier=notifier)
    sched.last_success = time.time() - 13 * 3600
    sched._track(False)
    sched._track(False)
    assert notifier.events == [('weather_stale', {'hours': 13})]
    sched._track(True)
    assert sched.stale_notified is False


def test_skipped_run_emits_event():
    from datetime import date, timedelta
    from src.services.valve_cron_scheduler import ValveCronScheduler
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = Database(path)
    for o in range(-2, 3):
        d = (date.today() + timedelta(days=o)).isoformat()
        db.insert_weather_data({'date': d, 'temperature_minimum': 0, 'temperature_maximum': 6,
                                'average_humidity': 90, 'average_pressure': 1013,
                                'description': 'snow', 'total_rain': 0})
    events = []
    main = SimpleNamespace(notifier=SimpleNamespace(emit=lambda e, **d: events.append((e, d))),
                           get_valve_status=lambda v: False, activate_valve=lambda *a: True)
    sched = ValveCronScheduler()
    sched.start(db, main)
    try:
        db.update_valve_cron(1, '0 6 * * *', True)
        db.update_valve_cron_duration(1, 600)
        sched._run_valve_activation(valve_id=1)
    finally:
        sched.stop()
        os.remove(path)
    assert events[0][0] == 'run_skipped'
    assert events[0][1]['reason_key'] == 'frost' and events[0][1]['base_duration'] == 600


# ----------------------------------------------------------------- API endpoints
@pytest.fixture(scope='module')
def client():
    from src.main_service import main_service
    from src.api.api_service import api_service
    with patch('src.services.weather.weather_service.WeatherService.update_weather_data', return_value=True), \
         patch('src.services.weather.cron_scheduler.CronScheduler.start'):
        if not main_service.is_running:
            assert main_service.initialize()
    yield login(api_service.app.test_client())


def test_api_integration_token_and_webhook(client, receiver):
    from src.api.api_service import api_service
    r = client.post('/api/auth/integration-tokens', json={'name': 'home-assistant'})
    assert r.status_code == 200
    token = r.get_json()['token']

    ha = api_service.app.test_client()
    ha.environ_base['HTTP_AUTHORIZATION'] = 'Bearer ' + token
    assert ha.get('/api/dashboard').status_code == 200
    assert ha.post('/api/integrations/webhooks', json={'name': 'home-assistant', 'url': receiver.url}).status_code == 200
    assert ha.get('/api/integrations/webhooks').get_json() == {'webhooks': [{'name': 'home-assistant'}]}

    # a manual run from HA is pushed back as events
    assert ha.post('/api/valves/2/activate', json={'duration': 60}).status_code == 200
    assert ha.post('/api/valves/2/deactivate').status_code == 200
    from src.main_service import main_service
    main_service.notifier.flush()
    kinds = [(e['event'], e.get('source') or e.get('status')) for e in receiver.received]
    assert ('run_started', 'manual') in kinds and ('run_finished', 'stopped') in kinds

    assert ha.delete('/api/integrations/webhooks/home-assistant').status_code == 200
    assert client.delete('/api/auth/integration-tokens/home-assistant').status_code == 200
    assert ha.get('/api/dashboard').status_code == 401


def test_api_integration_token_requires_auth():
    from src.api.api_service import api_service
    anon = api_service.app.test_client()
    assert anon.post('/api/auth/integration-tokens', json={'name': 'x'}).status_code == 401
    assert anon.post('/api/integrations/webhooks', json={'name': 'x', 'url': 'http://a'}).status_code == 401


# ----------------------------------------------------------------- HA message texts
def _messages():
    path = os.path.join(os.path.dirname(__file__), '..', 'homeassistant', 'custom_components', 'strop', 'messages.py')
    spec = importlib.util.spec_from_file_location('strop_messages', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notification_texts():
    m = _messages()
    title, msg = m.event_message('run_skipped', {'valve_id': 1, 'reason_key': 'not_needed',
                                                 'reason_args': {'factor': 'rain', 'rain': 13}}, 'ro')
    assert title == 'Strop' and msg == 'Udarea programată pentru Zona 1 a fost sărită: nu e necesar: ploaie (13 mm).'
    _, msg = m.event_message('run_started', {'valve_id': 2, 'duration': 340, 'base_duration': 600,
                                             'percent': 56, 'source': 'schedule'}, 'en')
    assert msg == 'Zone 2 watering for 5 min 40 s (56% of 10 min, weather adjusted).'
    _, msg = m.event_message('watchdog', {'valve_id': 1, 'duration': 3630}, 'ro')
    assert 'închisă forțat' in msg
    _, msg = m.event_message('run_skipped', {'valve_id': 1, 'reason_key': 'frost', 'reason_args': {'min': 1}}, 'en')
    assert msg.endswith('frost risk (min 1°C).')


def test_next_run_text():
    from datetime import date, datetime
    m = _messages()
    today = date(2026, 11, 12)  # Thursday
    plan = {'at': '', 'duration': 360, 'base_duration': 1800, 'percent': 20, 'skip': False}
    on = {'cron_expression': '35 5 * * 2', 'enabled': True, 'planned': [plan]}
    assert m.next_run_text({'cron_expression': '', 'enabled': False}, None, today, 'ro') == 'Fără program'
    assert m.next_run_text(dict(on, enabled=False), None, today, 'ro') == 'Program oprit'
    assert m.next_run_text(on, datetime(2026, 11, 17, 5, 35), today, 'ro') == 'marți 17 nov., 05:35 · 6 min'
    assert m.next_run_text(on, datetime(2026, 11, 13, 5, 35), today, 'en') == 'tomorrow, 05:35 · 6 min'
    skipped = dict(on, planned=[dict(plan, skip=True, reason_key='not_needed', reason_args={'factor': 'rain'})])
    assert m.next_run_text(skipped, datetime(2026, 11, 12, 6, 0), today, 'ro') == 'azi, 06:00 · sărită (ploaie)'


# ----------------------------------------------------------------- zone names
def test_zone_names_in_config(cfg):
    assert cfg.zone_name(1) is None
    assert cfg.set_zone_name(1, '  Grădina   din  față ') == 'Grădina din față'
    assert cfg.zone_name(1) == 'Grădina din față'
    assert cfg.set_zone_name(2, 'x' * 50) == 'x' * 32
    assert cfg.set_zone_name(1, '') is None and cfg.zone_name(1) is None
    assert ConfigService(cfg.config_path).zone_names() == {'2': 'x' * 32}


def test_events_carry_zone_name(cfg, receiver):
    cfg.set_zone_name(1, 'Gazon')
    notifier = Notifier(cfg)
    notifier.set_webhook('home-assistant', receiver.url)
    notifier.valve_event('opened', 1, duration=60)
    notifier.valve_event('opened', 2, duration=60)
    notifier.flush()
    assert [e.get('zone_name') for e in receiver.received] == ['Gazon', None]


def test_api_rename_zone(client):
    r = client.put('/api/valves/1/name', json={'name': 'Grădina'})
    assert r.status_code == 200 and r.get_json()['name'] == 'Grădina'
    valves = {v['id']: v for v in client.get('/api/dashboard').get_json()['valves']}
    assert valves[1]['name'] == 'Grădina' and valves[2]['name'] is None
    assert client.put('/api/valves/3/name', json={'name': 'x'}).status_code == 400
    assert client.put('/api/valves/1/name', json={'name': 5}).status_code == 400
    assert client.put('/api/valves/1/name', json={'name': ''}).get_json()['name'] is None
    from src.api.api_service import api_service
    assert api_service.app.test_client().put('/api/valves/1/name', json={'name': 'x'}).status_code == 401


def test_ha_zone_label():
    m = _messages()
    assert m.zone_label(1, None, 'ro') == 'Zona 1' and m.zone_label(2, None, 'en') == 'Zone 2'
    assert m.zone_label(1, 'Gazon', 'ro') == 'Gazon'
    _, msg = m.event_message('run_finished', {'valve_id': 1, 'zone_name': 'Gazon', 'duration': 300}, 'ro')
    assert msg == 'Gazon a terminat de udat (5 min).'
