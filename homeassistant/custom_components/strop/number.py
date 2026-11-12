"""Number: duration used when a zone is switched on from Home Assistant."""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MANUAL_MINUTES, VALVES
from .entity import StropEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(StropManualDuration(coordinator, v) for v in VALVES)


class StropManualDuration(StropEntity, RestoreNumber):
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "manual_duration", valve_id)
        self._attr_native_value = DEFAULT_MANUAL_MINUTES

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.coordinator.manual_minutes[self.valve_id] = self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.coordinator.manual_minutes[self.valve_id] = value
        self.async_write_ha_state()
