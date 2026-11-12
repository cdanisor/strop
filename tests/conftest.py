"""
Shared pytest setup: run everything against a throw-away database and config
so tests never touch the real irrigation_system.db / config.json.
"""
import json
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="strop-tests-")
os.environ["STROP_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["STROP_CONFIG_PATH"] = os.path.join(_tmp, "config.json")
with open(os.environ["STROP_CONFIG_PATH"], "w") as f:
    json.dump({"weather_api": {"api_key": "test"}, "gpio": {"valve1_pin": 23, "valve2_pin": 24}}, f)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
