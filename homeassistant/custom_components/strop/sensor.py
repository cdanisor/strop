"""Sensors: remaining time, next run, adjusted duration, weather adjustment, usage."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import VALVES
from .entity import StropEntity


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(str(value).replace(" ", "T"))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = dt_util.as_local(parsed.replace(tzinfo=dt_util.get_default_time_zone()))
    return parsed


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for v in VALVES:
        entities += [StropRemaining(coordinator, v), StropNextRun(coordinator, v), StropNextDuration(coordinator, v)]
    entities += [StropAdjustment(coordinator), StropWateredToday(coordinator), StropWeatherUpdated(coordinator)]
    async_add_entities(entities)


def _first_plan(entity: StropEntity) -> dict | None:
    schedule = entity.valve.get("schedule") or {}
    planned = schedule.get("planned") or []
    return planned[0] if schedule.get("enabled") and planned else None


class StropRemaining(StropEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "remaining", valve_id)

    @property
    def native_value(self) -> int:
        v = self.valve
        return int(v.get("remaining") or 0) if v.get("open") else 0


class StropNextRun(StropEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "next_run", valve_id)

    @property
    def native_value(self) -> datetime | None:
        plan = _first_plan(self)
        return _parse(plan["at"]) if plan else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = _first_plan(self) or {}
        return {
            "programmed_minutes": round((plan.get("base_duration") or 0) / 60, 1) if plan else None,
            "adjusted_minutes": round((plan.get("duration") or 0) / 60, 1) if plan else None,
            "percent": plan.get("percent"),
            "skipped": plan.get("skip"),
            "reason": plan.get("reason"),
        }


class StropNextDuration(StropEntity, SensorEntity):
    """Weather-adjusted duration of the next scheduled run (0 = skipped)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, coordinator, valve_id: int) -> None:
        super().__init__(coordinator, "next_duration", valve_id)

    @property
    def native_value(self) -> int | None:
        plan = _first_plan(self)
        return int(plan.get("duration") or 0) if plan else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = _first_plan(self) or {}
        return {"programmed_seconds": plan.get("base_duration"), "percent": plan.get("percent"),
                "reason": plan.get("reason")}


class StropAdjustment(StropEntity, SensorEntity):
    """Weather adjustment (percent of programmed time) for the next run day."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:weather-partly-rainy"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "adjustment")

    @property
    def native_value(self) -> int | None:
        adj = (self.coordinator.data or {}).get("adjustment") or {}
        return adj.get("percent")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        adj = (self.coordinator.data or {}).get("adjustment") or {}
        inputs = adj.get("inputs") or {}
        terms = adj.get("terms") or {}
        return {
            "date": adj.get("date"),
            "skipped": adj.get("skip"),
            "reason": adj.get("reason"),
            "temperature": inputs.get("temp"),
            "humidity": inputs.get("humidity"),
            "rain_mm": inputs.get("rain"),
            "temperature_effect": terms.get("temp"),
            "humidity_effect": terms.get("humidity"),
            "rain_effect": terms.get("rain"),
        }


class StropWateredToday(StropEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-check"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "watered_today")

    @property
    def native_value(self) -> int:
        usage = (self.coordinator.data or {}).get("usage") or {}
        today = dt_util.now().date().isoformat()
        return int(sum((usage.get(str(v)) or {}).get(today, 0) for v in VALVES))


class StropWeatherUpdated(StropEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-refresh"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "weather_updated")

    @property
    def native_value(self) -> datetime | None:
        return _parse((self.coordinator.data or {}).get("weather_updated"))
