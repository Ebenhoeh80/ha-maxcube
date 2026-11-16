"""Sensor platform for eQ-3 MAX! Cube (valve position)."""

from __future__ import annotations

from maxcube.device import MaxDevice

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up valve-position sensors for radiator thermostats."""
    coordinator = entry.runtime_data
    cube = coordinator.cube
    async_add_entities(
        MaxCubeValve(coordinator, device)
        for device in cube.devices
        if cube.is_thermostat(device)
    )


class MaxCubeValve(MaxCubeEntity, SensorEntity):
    """Valve opening percentage of a radiator thermostat."""

    _attr_translation_key = "valve_position"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the valve-position sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.rf_address}_valve"

    @property
    def native_value(self) -> int | None:
        """Return the valve opening in percent."""
        return getattr(self._device, "valve_position", None)
