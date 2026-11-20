"""Binary sensor platform for eQ-3 MAX! Cube (window contacts, low battery)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from maxcube.device import MaxDevice

from .const import DOMAIN
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity, async_add_devices_as_they_appear

# read-only: the coordinator does the polling
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up window-contact and low-battery binary sensors."""
    coordinator = entry.runtime_data

    def _binary_sensors(
        coordinator: MaxCubeCoordinator, device: MaxDevice
    ) -> list[BinarySensorEntity]:
        entities: list[BinarySensorEntity] = []
        if device.is_windowshutter():
            entities.append(MaxCubeWindow(coordinator, device))
        if device.is_thermostat() or device.is_wallthermostat() or device.is_windowshutter():
            entities.append(MaxCubeBattery(coordinator, device))
            # RF link diagnostics: same bit set for every device type.
            entities.append(MaxCubeUninitialized(coordinator, device))
            entities.append(MaxCubeError(coordinator, device))
            entities.append(MaxCubeRadioFault(coordinator, device))
            entities.append(MaxCubeStale(coordinator, device))
        return entities

    async_add_devices_as_they_appear(entry, async_add_entities, _binary_sensors)
    if coordinator.cube.serial:
        async_add_entities([MaxCubeConnectivity(coordinator)])


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


class MaxCubeDeviceStatus(MaxCubeEntity, BinarySensorEntity):
    """Base for the RF link diagnostics recovered from the ``L`` message.

    Subclasses set ``_bit_name`` to pick one field out of the device status and
    ``_problem_value`` to the bit value that means "problem present" — the
    sensors report *on = problem*, so the HA problem indicator lights up
    correctly.  ``None`` (device never seen) is passed through to HA as
    unknown instead of being guessed.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _bit_name: str = ""
    _problem_value: bool = True

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.rf_address}_{self._bit_name}"

    @property
    def is_on(self) -> bool | None:
        """Return True when this device has the problem this sensor reports."""
        value = getattr(self.coordinator.device_status(self._rf_address), self._bit_name)
        if value is None:
            return None
        return value == self._problem_value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the raw flag bytes (hex) the bit was read from, for diagnosis."""
        return {"raw_flags": self.coordinator.device_status(self._rf_address).raw_flags}


class MaxCubeUninitialized(MaxCubeDeviceStatus, BinarySensorEntity):
    """Device is paired with the Cube but has never delivered a config."""

    _attr_translation_key = "uninitialized"
    _attr_entity_registry_enabled_default = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _bit_name = "initialized"
    # No "initialized" bit means the device never reported a configuration.
    _problem_value = False


class MaxCubeError(MaxCubeDeviceStatus, BinarySensorEntity):
    """Device is in an error state."""

    _attr_translation_key = "device_error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _bit_name = "error"
    _problem_value = True


class MaxCubeRadioFault(MaxCubeDeviceStatus, BinarySensorEntity):
    """Device is not reachable over the air ("Funkstörung").

    Deliberately ``problem`` rather than ``connectivity``: HA renders a
    ``connectivity`` sensor with *on = connected*, so a ``connectivity`` sensor
    called "Radio fault" would show "off" as "disconnected" — stating that the
    radio link is fine while simultaneously claiming the device is not
    connected.  With ``problem``, on means "fault present", which matches the
    sensor name.
    """

    _attr_translation_key = "radio_fault"
    _attr_entity_registry_enabled_default = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _bit_name = "link_error"
    _problem_value = True


class MaxCubeStale(MaxCubeDeviceStatus, BinarySensorEntity):
    """No frame has been heard from the device within the staleness window."""

    _attr_translation_key = "device_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _bit_name = "stale"
    _problem_value = True

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose when the device was last heard, for graphing and templates."""
        status = self.coordinator.device_status(self._rf_address)
        return {
            "last_heard": status.last_heard.isoformat() if status.last_heard else None,
            "raw_flags": status.raw_flags,
        }


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
