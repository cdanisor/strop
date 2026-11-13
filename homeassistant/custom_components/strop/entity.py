"""Base entity for Strop."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_URL, DOMAIN


class StropEntity(CoordinatorEntity):
    """Entity attached to the Strop controller device (or one of its zones)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, key: str, valve_id: int | None = None) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.valve_id = valve_id
        suffix = f"zone{valve_id}_{key}" if valve_id else key
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_translation_key = key
        if valve_id:
            # Zone name set in the Strop UI; the entry is reloaded when it changes
            self._attr_translation_placeholders = {"zone": coordinator.zone_label(valve_id)}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Strop",
            manufacturer="Strop",
            model="Raspberry Pi irrigation controller",
            configuration_url=entry.data[CONF_URL].removesuffix("/api").replace(":5000", ":8000"),
        )

    @property
    def valve(self) -> dict:
        return self.coordinator.valve(self.valve_id) if self.valve_id else {}
