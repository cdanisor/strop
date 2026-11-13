"""Strop irrigation controller integration.

* Polls GET /api/dashboard (every 60 s) for state, schedules, next runs and
  the weather adjustment.
* Registers a Home Assistant webhook and tells Strop to POST events to it;
  every event refreshes the data, is fired on the HA bus as "strop_event"
  (for automations) and can be sent as a notification.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StropAuthError, StropClient, StropError
from .const import (
    CONF_HA_URL,
    CONF_LANGUAGE,
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_SERVICE,
    CONF_TOKEN,
    CONF_URL,
    CONF_WEBHOOK_ID,
    DEFAULT_NOTIFY_EVENTS,
    DOMAIN,
    EVENT_STROP,
    SCAN_INTERVAL,
    WEBHOOK_NAME,
)
from .messages import event_message, zone_label

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

type StropConfigEntry = ConfigEntry[StropCoordinator]


class StropCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: StropClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client
        # manual-run durations (minutes) set through the number entities
        self.manual_minutes: dict[int, float] = {}
        # zone names the entities were created with (None until the first refresh)
        self._names: dict[int, str | None] | None = None

    @property
    def language(self) -> str:
        lang = self.config_entry.options.get(CONF_LANGUAGE)
        if lang:
            return lang
        return "ro" if (self.hass.config.language or "").startswith("ro") else "en"

    def zone_label(self, valve_id: int) -> str:
        return zone_label(valve_id, self.valve(valve_id).get("name"), self.language)

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.dashboard()
        except StropAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except StropError as err:
            raise UpdateFailed(str(err)) from err
        names = {v.get("id"): v.get("name") for v in data.get("valves", [])}
        if self._names is None:
            self._names = names
        elif names != self._names:
            # Entity names come from the zone names: reload to rename them
            _LOGGER.info("Strop zone names changed, reloading the integration")
            self._names = names
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return data

    def valve(self, valve_id: int) -> dict:
        for v in (self.data or {}).get("valves", []):
            if v.get("id") == valve_id:
                return v
        return {}


async def async_setup_entry(hass: HomeAssistant, entry: StropConfigEntry) -> bool:
    client = StropClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    coordinator = StropCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Webhook for push events from Strop
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = webhook.async_generate_id()
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id})

    async def handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        try:
            payload: dict[str, Any] = await request.json()
        except ValueError:
            return web.Response(status=400)
        await _handle_event(hass, entry, payload)
        return web.Response(status=200)

    webhook.async_register(hass, DOMAIN, "Strop", webhook_id, handle_webhook,
                           local_only=True, allowed_methods=["POST"])
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    ha_url = entry.data.get(CONF_HA_URL, "").rstrip("/")
    if ha_url:
        try:
            await client.set_webhook(WEBHOOK_NAME, ha_url + webhook.async_generate_path(webhook_id))
        except StropError as err:
            _LOGGER.warning("Could not register webhook on Strop (events will not be pushed): %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: StropConfigEntry) -> None:
    """The language also sets the default zone names ("Zona N" / "Zone N")."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: StropConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: StropConfigEntry) -> None:
    """Stop Strop from sending events to a webhook that no longer exists."""
    client = StropClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        await client.remove_webhook(WEBHOOK_NAME)
    except StropError:
        pass


async def _handle_event(hass: HomeAssistant, entry: StropConfigEntry, payload: dict[str, Any]) -> None:
    event = payload.get("event")
    if not event:
        return
    # A valve stopped by the watchdog is reported as its own event type
    kind = "watchdog" if event == "run_finished" and payload.get("status") == "watchdog" else event

    coordinator: StropCoordinator = entry.runtime_data
    if payload.get("valve_id") is not None and not payload.get("zone_name"):
        payload = {**payload, "zone_name": coordinator.valve(payload["valve_id"]).get("name")}
    hass.bus.async_fire(EVENT_STROP, {**payload, "type": kind})
    await coordinator.async_request_refresh()

    service = entry.options.get(CONF_NOTIFY_SERVICE) or ""
    events = entry.options.get(CONF_NOTIFY_EVENTS, DEFAULT_NOTIFY_EVENTS)
    if not service or kind not in events or "." not in service:
        return
    title, message = event_message(kind, payload, coordinator.language)
    domain, name = service.split(".", 1)
    try:
        await hass.services.async_call(domain, name, {"title": title, "message": message}, blocking=False)
    except Exception as err:  # noqa: BLE001 - a bad notify target must not break event handling
        _LOGGER.warning("Could not send Strop notification via %s: %s", service, err)
