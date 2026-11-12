"""Switches: open/close a zone, enable/disable its schedule."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import StropError
from .const import DEFAULT_MANUAL_MINUTES, VALVES
from .entity import StropEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for valve_id in VALVES:
        entities.append(StropValveSwitch(coordinator, valve_id))
        entities.append(StropScheduleSwitch(coordinator, valve_id))
    async_add_entities(entities)


class StropValveSwitch(StropEntity, SwitchEntity):
    """On = water now for the duration set in the matching number entity."""

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "valve", valve_id)

    @property
    def is_on(self) -> bool:
        return bool(self.valve.get("open"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.valve
        return {"remaining": v.get("remaining"), "duration": v.get("duration"), "started_at": v.get("started_at")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        minutes = self.coordinator.manual_minutes.get(self.valve_id, DEFAULT_MANUAL_MINUTES)
        try:
            await self.coordinator.client.activate(self.valve_id, int(minutes * 60))
        except StropError as err:
            raise HomeAssistantError(f"Strop: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.deactivate(self.valve_id)
        except StropError as err:
            raise HomeAssistantError(f"Strop: {err}") from err
        await self.coordinator.async_request_refresh()


class StropScheduleSwitch(StropEntity, SwitchEntity):
    """Enable / disable the zone's automatic schedule."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "schedule", valve_id)

    @property
    def schedule(self) -> dict:
        return self.valve.get("schedule") or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self.schedule.get("cron_expression"))

    @property
    def is_on(self) -> bool:
        return bool(self.schedule.get("enabled"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.schedule
        return {"cron": s.get("cron_expression"), "duration": s.get("duration"), "last_run": s.get("last_run")}

    async def _set(self, enabled: bool) -> None:
        s = self.schedule
        if not s.get("cron_expression"):
            raise HomeAssistantError("Strop: no schedule configured for this zone")
        try:
            await self.coordinator.client.set_schedule(self.valve_id, s["cron_expression"], s.get("duration") or 300, enabled)
        except StropError as err:
            raise HomeAssistantError(f"Strop: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
