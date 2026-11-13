"""
Zones are configured in config.json ("gpio.zones": [{"id", "pin"}, ...]),
any number of them; the old valve1_pin / valve2_pin keys are still read.
"""
from unittest.mock import patch

import pytest

from src.services.config_service import ConfigService, ZoneConfigError, parse_zones
from src.services.gpio_control_service import GPIOControlService


THREE = {'gpio': {'zones': [{'id': 1, 'pin': 23}, {'id': 2, 'pin': 24}, {'id': 3, 'pin': 25}]}}


def test_parse_new_format_sorted_by_id():
    cfg = {'gpio': {'zones': [{'id': 3, 'pin': 25}, {'id': 1, 'pin': 23}, {'id': 2, 'pin': '24'}]}}
    assert parse_zones(cfg) == {1: 23, 2: 24, 3: 25}
    assert list(parse_zones(cfg)) == [1, 2, 3]


def test_parse_legacy_format_and_defaults():
    assert parse_zones({'gpio': {'valve1_pin': 17, 'valve2_pin': 27}}) == {1: 17, 2: 27}
    assert parse_zones({'gpio': {'valve1_pin': 23, 'valve2_pin': 24, 'valve3_pin': 25}}) == {1: 23, 2: 24, 3: 25}
    assert parse_zones({}) == {1: 23, 2: 24}
    assert parse_zones({'gpio': {}}) == {1: 23, 2: 24}


@pytest.mark.parametrize('zones', [
    [],                                                  # empty list
    'nope',                                              # not a list
    [{'id': 1}],                                         # no pin
    [{'id': 1, 'pin': 23}, {'id': 1, 'pin': 24}],        # duplicate id
    [{'id': 1, 'pin': 23}, {'id': 2, 'pin': 23}],        # duplicate pin
    [{'id': 1, 'pin': 40}],                              # not a BCM GPIO
    [{'id': 1, 'pin': 1}],                               # ID_SC, reserved
    [{'id': 0, 'pin': 23}],                              # id below 1
    [{'id': 100, 'pin': 23}],                            # id above 99
    [{'id': True, 'pin': 23}],                           # bool is not a number
    [{'id': 1, 'pin': 'x'}],
    [{'id': i, 'pin': i + 1} for i in range(1, 18)],     # more than 16 zones
])
def test_parse_rejects_bad_zones(zones):
    with pytest.raises(ZoneConfigError):
        parse_zones({'gpio': {'zones': zones}})


def test_config_service_zone_helpers(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"gpio": {"zones": [{"id": 1, "pin": 5}, {"id": 4, "pin": 6}]}}')
    cs = ConfigService(str(path))
    assert cs.zones() == {1: 5, 4: 6}
    assert cs.zone_ids() == [1, 4]
    assert cs.has_zone(4) and not cs.has_zone(2)


def test_default_config_uses_zone_list(tmp_path):
    cs = ConfigService(str(tmp_path / 'new.json'))
    assert cs.get('gpio') == {'zones': [{'id': 1, 'pin': 23}, {'id': 2, 'pin': 24}]}


def test_gpio_service_drives_any_number_of_zones(tmp_path):
    from src.database import Database
    gpio = GPIOControlService(THREE, Database(str(tmp_path / 'z.db')))
    assert gpio.valve_ids == (1, 2, 3) and gpio.pins[3] == 25
    assert gpio.activate_valve(3, 30)
    assert gpio.get_valve_status(3) is True
    assert gpio.activate_valve(4, 30) is False
    assert gpio.deactivate_valve(3)
    assert gpio.get_all_valve_status() == {1: False, 2: False, 3: False}
    gpio.cleanup()


def test_gpio_service_refuses_bad_config(tmp_path):
    from src.database import Database
    with pytest.raises(ZoneConfigError):
        GPIOControlService({'gpio': {'zones': [{'id': 1, 'pin': 23}, {'id': 2, 'pin': 23}]}},
                           Database(str(tmp_path / 'z.db')))


def test_gpio_service_real_pins_are_set_up(tmp_path):
    """On the Pi every configured pin is set up as an output and driven LOW."""
    import sys
    from unittest.mock import MagicMock
    from src.database import Database
    fake = MagicMock()
    rpi = MagicMock(GPIO=fake)
    with patch.dict(sys.modules, {'RPi': rpi, 'RPi.GPIO': fake}):
        gpio = GPIOControlService(THREE, Database(str(tmp_path / 'z.db')))
        assert not gpio.is_simulation_mode
        assert [c.args[0] for c in fake.setup.call_args_list] == [23, 24, 25]
        gpio.activate_valve(3, 30)
        fake.output.assert_called_with(25, fake.HIGH)
        gpio.deactivate_valve(3)
        fake.output.assert_called_with(25, fake.LOW)
        gpio.cleanup()


def test_safe_off_pins(tmp_path, monkeypatch):
    from src import gpio_safe_off
    path = tmp_path / 'c.json'
    monkeypatch.setattr('src.services.config_service.DEFAULT_CONFIG_PATH', str(path))

    def pins_for(text):
        path.write_text(text)
        with patch('src.services.config_service.ConfigService.__init__.__defaults__', (str(path),)):
            return gpio_safe_off.collect_pins()

    assert pins_for('{"gpio": {"zones": [{"id": 1, "pin": 5}, {"id": 2, "pin": 6}, {"id": 3, "pin": 13}]}}') == [5, 6, 13]
    # broken config (duplicate pin): still switch off everything that can be read, plus the defaults
    assert pins_for('{"gpio": {"zones": [{"id": 1, "pin": 5}, {"id": 2, "pin": 5}, {"id": 3, "pin": 99}]}}') == [5, 23, 24]
    assert pins_for('{"gpio": {"valve1_pin": 17, "valve2_pin": 27}}') == [17, 27]


# ------------------------------------------------------------------ API with three zones
@pytest.fixture(scope='module')
def client():
    from src.main_service import main_service
    from src.api.api_service import api_service
    with patch('src.services.weather.weather_service.WeatherService.update_weather_data', return_value=True), \
         patch('src.services.weather.cron_scheduler.CronScheduler.start'):
        if not main_service.is_running:
            assert main_service.initialize()
    from conftest import login
    yield login(api_service.app.test_client())


@pytest.fixture
def three_zones(client):
    """Swap in a GPIO service with a third zone (as if config.json had three)."""
    from src.main_service import main_service
    old = main_service.gpio_service
    main_service.gpio_service = GPIOControlService(THREE, old.db)
    yield main_service
    main_service.gpio_service.cleanup()
    main_service.gpio_service = old
    main_service.valve_scheduler.reload_all()


def test_api_serves_configured_zones(client, three_zones):
    d = client.get('/api/dashboard').get_json()
    assert [v['id'] for v in d['valves']] == [1, 2, 3]
    assert set(d['usage']) == {'1', '2', '3'}

    assert client.post('/api/valves/3/activate', json={'duration': 30}).status_code == 200
    assert client.get('/api/valves/status').get_json()['valves']['3'] is True
    assert client.post('/api/valves/3/deactivate').status_code == 200

    r = client.post('/api/valves/3/schedules', json={'cron_expression': '0 5 * * 1', 'duration': 60, 'enabled': True})
    assert r.status_code == 201, r.get_json()
    assert three_zones.valve_scheduler.has_job(3)
    assert client.delete(f"/api/schedules/{r.get_json()['schedule']['id']}").status_code == 200

    r = client.post('/api/valves/4/activate', json={'duration': 30})
    assert r.status_code == 400 and r.get_json()['code'] == 'invalid_zone'
    assert client.put('/api/valves/4/name', json={'name': 'x'}).status_code == 400
