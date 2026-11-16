"""Binary sensor platform for eQ-3 MAX! Cube (window contacts, low battery)."""

from __future__ import annotations

from maxcube.device import MaxDevice

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up window-contact and low-battery binary sensors."""
    coordinator = entry.runtime_data
    cube = coordinator.cube
    entities: list[BinarySensorEntity] = []
    for device in cube.devices:
        if device.is_windowshutter():
            entities.append(MaxCubeWindow(coordinator, device))
        if (
            device.is_thermostat()
            or device.is_wallthermostat()
            or device.is_windowshutter()
        ):
            entities.append(MaxCubeBattery(coordinator, device))
    async_add_entities(entities)


class MaxCubeWindow(MaxCubeEntity, BinarySensorEntity):
    """Open state of a window / door contact."""

    _attr_name = None
    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the window contact."""
        super().__init__(coordinator, device)
        self._attr_unique_id = device.rf_address

    @property
    def is_on(self) -> bool:
        """Return True when the window is open."""
        return bool(self._device.is_open)


class MaxCubeBattery(MaxCubeEntity, BinarySensorEntity):
    """Low-battery indicator for a MAX! device (on = battery low)."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.rf_address}_battery"

    @property
    def is_on(self) -> bool:
        """Return True when the battery is low (maxcube-api: battery == 1)."""
        return bool(getattr(self._device, "battery", 0))
