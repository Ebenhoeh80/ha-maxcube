"""Sensor platform for eQ-3 MAX! Cube (valve position, temperature)."""

from __future__ import annotations

from maxcube.device import MaxDevice

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up valve-position and temperature sensors."""
    coordinator = entry.runtime_data
    cube = coordinator.cube
    entities: list[SensorEntity] = []
    for device in cube.devices:
        if device.is_thermostat():
            entities.append(MaxCubeValve(coordinator, device))
        if device.is_thermostat() or device.is_wallthermostat():
            entities.append(MaxCubeTemperature(coordinator, device))
    async_add_entities(entities)


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


class MaxCubeTemperature(MaxCubeEntity, SensorEntity):
    """Measured room temperature reported by a thermostat."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.rf_address}_temperature"

    @property
    def native_value(self) -> float | None:
        """Return the measured temperature, if the device reports one."""
        temp = getattr(self._device, "actual_temperature", None)
        # Radiator thermostats only report a temperature in auto/manual mode.
        return temp if temp else None
