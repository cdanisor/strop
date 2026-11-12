"""
Shared pytest setup: run everything against a throw-away database and config
so tests never touch the real irrigation_system.db / config.json.
"""
import json
import os
import sys
import tempfile

from werkzeug.security import generate_password_hash

TEST_PASSWORD = "test-password-123"

_tmp = tempfile.mkdtemp(prefix="strop-tests-")
os.environ["STROP_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["STROP_CONFIG_PATH"] = os.path.join(_tmp, "config.json")
with open(os.environ["STROP_CONFIG_PATH"], "w") as f:
    json.dump({"weather_api": {"api_key": "test"}, "gpio": {"valve1_pin": 23, "valve2_pin": 24},
               "auth": {"password_hash": generate_password_hash(TEST_PASSWORD),
                        "secret": "test-secret", "token_version": 1}}, f)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def login(test_client):
    """Log a Flask test client in: every later request carries the bearer token."""
    resp = test_client.post('/api/auth/login', json={'password': TEST_PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    test_client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer ' + resp.get_json()['token']
    return test_client
