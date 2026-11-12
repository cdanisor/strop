"""
Tests for API authentication and the valve/process watchdog.
"""
import json
import os
import socket
import sys
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conftest import TEST_PASSWORD
from src.services.auth_service import AuthService, MAX_FAILURES
from src.services.config_service import ConfigService


# ----------------------------------------------------------------- auth (unit)
@pytest.fixture
def auth_cfg():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w') as f:
        json.dump({'gpio': {}}, f)
    yield ConfigService(path)
    os.remove(path)


def test_fails_closed_without_password(auth_cfg):
    auth = AuthService(auth_cfg)
    assert not auth.is_configured()
    assert not auth.check_password('anything')
    assert not auth.verify_token(auth.issue_token())


def test_secret_is_generated_and_persisted(auth_cfg):
    AuthService(auth_cfg)
    with open(auth_cfg.config_path) as f:
        assert len(json.load(f)['auth']['secret']) == 64


def test_password_hash_only_and_tokens(auth_cfg):
    auth = AuthService(auth_cfg)
    auth.set_password('correct horse')
    with open(auth_cfg.config_path) as f:
        stored = json.load(f)['auth']
    assert 'correct horse' not in json.dumps(stored)
    assert auth.check_password('correct horse') and not auth.check_password('wrong')
    token = auth.issue_token()
    assert auth.verify_token(token)
    assert not auth.verify_token(token + 'x')
    assert not auth.verify_token('')


def test_changing_password_logs_out_everyone(auth_cfg):
    auth = AuthService(auth_cfg)
    auth.set_password('first-password')
    old = auth.issue_token()
    auth.set_password('second-password')
    assert not auth.verify_token(old)
    assert auth.verify_token(auth.issue_token())


def test_password_change_from_cli_is_picked_up_without_restart(auth_cfg):
    running = AuthService(auth_cfg)
    running.set_password('first-password')
    token = running.issue_token()
    # another process (scripts/set_password.py) changes the file
    other = AuthService(ConfigService(auth_cfg.config_path))
    os.utime(auth_cfg.config_path, None)
    other.set_password('second-password')
    st = os.stat(auth_cfg.config_path)
    os.utime(auth_cfg.config_path, (st.st_atime, st.st_mtime + 5))
    assert not running.verify_token(token)
    assert running.check_password('second-password')


def test_expired_token_rejected(auth_cfg):
    auth = AuthService(auth_cfg)
    auth.set_password('password-1')
    token = auth.issue_token()
    auth.token_days = 0
    with patch('time.time', return_value=__import__('time').time() + 5):
        assert not auth.verify_token(token)


def test_short_password_rejected(auth_cfg):
    with pytest.raises(ValueError):
        AuthService(auth_cfg).set_password('short')


def test_rate_limit_per_client(auth_cfg):
    auth = AuthService(auth_cfg)
    for _ in range(MAX_FAILURES):
        assert auth.retry_after('1.2.3.4') == 0
        auth.record_failure('1.2.3.4')
    assert auth.retry_after('1.2.3.4') > 0
    assert auth.retry_after('5.6.7.8') == 0


def test_forwarded_for_trusted_only_from_proxy(auth_cfg):
    auth_cfg.update('auth.trusted_proxies', ['192.168.10.14'])
    auth = AuthService(auth_cfg)
    assert auth.client_key('192.168.10.14', '81.2.3.4, 10.0.0.1') == '81.2.3.4'
    assert auth.client_key('192.168.10.99', '81.2.3.4') == '192.168.10.99'


# ----------------------------------------------------------------- auth (API)
@pytest.fixture(scope='module')
def anon():
    from src.api.api_service import api_service
    return api_service.app.test_client()


@pytest.mark.parametrize('method,path', [
    ('get', '/api/dashboard'), ('get', '/api/valves/status'), ('post', '/api/valves/1/activate'),
    ('post', '/api/valves/1/deactivate'), ('post', '/api/valves/1/cron'), ('delete', '/api/valves/1/cron'),
    ('get', '/api/valves/history'), ('get', '/api/weather/daily'), ('get', '/api/auth/check'),
])
def test_protected_endpoints_need_token(anon, method, path):
    r = getattr(anon, method)(path, json={})
    assert r.status_code == 401
    assert r.get_json()['auth_required'] is True
    r = getattr(anon, method)(path, json={}, headers={'Authorization': 'Bearer forged'})
    assert r.status_code == 401


def test_public_endpoints(anon):
    assert anon.get('/api/health').status_code == 200
    assert anon.get('/api/auth/status').get_json() == {'configured': True}


def test_login_flow(anon):
    assert anon.post('/api/auth/login', json={'password': 'nope'}).status_code == 401
    r = anon.post('/api/auth/login', json={'password': TEST_PASSWORD})
    assert r.status_code == 200
    token = r.get_json()['token']
    assert anon.get('/api/auth/check', headers={'Authorization': 'Bearer ' + token}).status_code == 200


def test_cors_allows_authorization_header(anon):
    r = anon.options('/api/dashboard', headers={
        'Origin': 'http://localhost:8000', 'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization'})
    assert 'authorization' in r.headers.get('Access-Control-Allow-Headers', '').lower()


# ----------------------------------------------------------------- watchdog
from src.database import Database  # noqa: E402
from src.services.gpio_control_service import GPIOControlService  # noqa: E402
from src.services.watchdog import Watchdog, watchdog_interval, sd_notify  # noqa: E402


@pytest.fixture
def gpio():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    service = GPIOControlService({'gpio': {}}, Database(path))
    yield service
    service.cleanup()
    os.remove(path)


def test_guard_force_closes_overdue_valve(gpio):
    gpio.activate_valve(1, 600)
    gpio.valve_start_times[1] -= timedelta(seconds=700)   # timer "lost"
    wd = Watchdog(SimpleNamespace(gpio_service=gpio))
    assert wd.guard_valves() == [1]
    assert gpio.get_valve_status(1) is False
    assert gpio.db.get_valve_logs(1)[0]['status'] == 'Watchdog Stopped'


def test_guard_leaves_valve_within_planned_time(gpio):
    gpio.activate_valve(2, 600)
    gpio.valve_start_times[2] -= timedelta(seconds=500)
    assert Watchdog(SimpleNamespace(gpio_service=gpio)).guard_valves() == []
    assert gpio.get_valve_status(2) is True


class FakeGPIO:
    HIGH, LOW = 1, 0

    def __init__(self):
        self.levels = {23: 0, 24: 0}

    def input(self, pin):
        return self.levels[pin]

    def output(self, pin, level):
        self.levels[pin] = level

    def cleanup(self):
        pass


def test_stray_high_pin_is_forced_low(gpio):
    fake = FakeGPIO()
    gpio.is_simulation_mode, gpio._gpio = False, fake
    fake.levels[24] = 1                      # relay on although valve 2 is closed
    assert gpio.verify_outputs() == [2]
    assert fake.levels[24] == 0


def test_open_valve_with_low_pin_is_closed_in_software(gpio):
    fake = FakeGPIO()
    gpio.is_simulation_mode, gpio._gpio = False, fake
    gpio.activate_valve(1, 600)
    fake.levels[23] = 0                      # pin dropped
    assert gpio.verify_outputs() == [1]
    assert gpio.get_valve_status(1) is False


def test_unhealthy_when_scheduler_stopped():
    ms = SimpleNamespace(is_running=True, gpio_service=None,
                         valve_scheduler=SimpleNamespace(is_running=False, scheduler=SimpleNamespace(running=False)))
    assert Watchdog(ms).check_health() is False


def test_health_failures_stop_watchdog_pings():
    ms = SimpleNamespace(is_running=True, gpio_service=None,
                         valve_scheduler=SimpleNamespace(is_running=True, scheduler=SimpleNamespace(running=True)))
    wd = Watchdog(ms, health_url='http://127.0.0.1:9/api/health')
    wd._started_at = -10_000          # past the startup grace period
    with patch('src.services.watchdog.sd_notify') as notify:
        results = [wd.tick() for _ in range(3)]
    assert results == [True, True, False]
    assert notify.call_count == 2


def test_watchdog_interval_from_systemd(monkeypatch):
    monkeypatch.setenv('WATCHDOG_USEC', '60000000')
    assert watchdog_interval() == 30
    monkeypatch.delenv('WATCHDOG_USEC')
    assert watchdog_interval() == 10


@pytest.mark.skipif(not hasattr(socket, 'AF_UNIX') or sys.platform == 'win32', reason='needs unix datagram sockets')
def test_sd_notify_sends_message(monkeypatch, tmp_path):
    path = str(tmp_path / 'notify.sock')
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(path)
    monkeypatch.setenv('NOTIFY_SOCKET', path)
    assert sd_notify('WATCHDOG=1')
    assert server.recv(64) == b'WATCHDOG=1'
    server.close()


def test_sd_notify_noop_outside_systemd(monkeypatch):
    monkeypatch.delenv('NOTIFY_SOCKET', raising=False)
    assert sd_notify('READY=1') is False


def test_gpio_safe_off_runs_without_hardware():
    from src import gpio_safe_off
    assert gpio_safe_off.main() == 0
