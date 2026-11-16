"""Binary sensor platform for eQ-3 MAX! Cube (window contacts, low battery)."""

from __future__ import annotations

from maxcube.device import MaxDevice

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
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
    if coordinator.cube.serial:
        entities.append(MaxCubeConnectivity(coordinator))
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


class MaxCubeConnectivity(CoordinatorEntity[MaxCubeCoordinator], BinarySensorEntity):
    """Connectivity of the Cube itself (on = the last poll succeeded)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MaxCubeCoordinator) -> None:
        """Initialize the Cube connectivity sensor on the hub device."""
        super().__init__(coordinator)
        serial = coordinator.cube.serial
        self._attr_unique_id = f"{serial}_connectivity"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    @property
    def available(self) -> bool:
        """Stay available so it can report the offline state itself."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True while the Cube is reachable."""
        return self.coordinator.last_update_success
