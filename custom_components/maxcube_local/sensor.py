"""Sensor platform for eQ-3 MAX! Cube (valve position, temperature)."""

from __future__ import annotations

from maxcube.device import MaxDevice

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
    if cube.serial:
        if cube.duty_cycle is not None:
            entities.append(
                MaxCubeStatusSensor(coordinator, "duty_cycle", PERCENTAGE, "mdi:radio-tower")
            )
        if cube.free_memory_slots is not None:
            entities.append(
                MaxCubeStatusSensor(coordinator, "free_memory_slots", None, "mdi:memory")
            )
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


class MaxCubeStatusSensor(CoordinatorEntity[MaxCubeCoordinator], SensorEntity):
    """A status value of the Cube itself (duty cycle, free memory slots), read at every poll.

    The Cube may only use a limited share of the radio time. At a duty cycle of 100 % it sends no
    radio commands for about an hour, so watch this value when you change many settings.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: MaxCubeCoordinator,
        key: str,
        unit: str | None,
        icon: str,
    ) -> None:
        """Initialize the status sensor on the Cube's hub device."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        serial = coordinator.cube.serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def native_value(self) -> int | None:
        """Return the value from the Cube's latest H message."""
        return getattr(self.coordinator.cube, self._key, None)

