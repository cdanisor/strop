"""Constants for the Strop irrigation integration."""
from datetime import timedelta

DOMAIN = "strop"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_HA_URL = "ha_url"
CONF_WEBHOOK_ID = "webhook_id"

CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_EVENTS = "notify_events"
CONF_LANGUAGE = "language"

DEFAULT_URL = "http://192.168.10.17:5000"
TOKEN_NAME = "home-assistant"
WEBHOOK_NAME = "home-assistant"

SCAN_INTERVAL = timedelta(seconds=60)
# Zones used until the controller reports its own list (configured in its config.json)
VALVES = (1, 2)
DEFAULT_MANUAL_MINUTES = 10

EVENT_STROP = "strop_event"

NOTIFY_EVENT_TYPES = [
    "run_started",
    "run_finished",
    "run_skipped",
    "watchdog",
    "weather_stale",
    "controller_started",
]
DEFAULT_NOTIFY_EVENTS = ["run_skipped", "watchdog", "weather_stale", "controller_started"]
