"""Binary sensors: zone watering state."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import VALVES
from .entity import StropEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(StropWatering(coordinator, v) for v in VALVES)


class StropWatering(StropEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "watering", valve_id)

    @property
    def is_on(self) -> bool:
        return bool(self.valve.get("open"))
