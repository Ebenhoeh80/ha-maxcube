"""Shared entity base for eQ-3 MAX! Cube devices."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from maxcube.device import MaxDevice

from .const import DEVICE_TYPE_NAMES, DOMAIN, MANUFACTURER
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator

# Home Assistant 2026.11 links a device to its hub by registry id (``via_device_id``)
# and deprecates ``via_device`` (removed in 2027.8). Older versions only know
# ``via_device``, so the right one is chosen at import time.
_VIA_DEVICE_ID = hasattr(dr.DeviceRegistry, "async_get_device_by_identifier") and (
    "via_device_id" in getattr(DeviceInfo, "__dataclass_fields__", {})
)


def _apply_hub_link(
    info: DeviceInfo, coordinator: MaxCubeCoordinator, cube_serial: str | None
) -> None:
    """Group a device under the Cube hub (the way this Home Assistant version wants it)."""
    if not cube_serial:
        return
    if not _VIA_DEVICE_ID:
        # Older Home Assistant versions only know ``via_device``; newer ones removed the key.
        info["via_device"] = (DOMAIN, cube_serial)  # type: ignore[typeddict-unknown-key]
        return
    hub = dr.async_get(coordinator.hass).async_get_device_by_identifier(
        (DOMAIN, cube_serial), coordinator.config_entry.entry_id
    )
    if hub is not None:
        info["via_device_id"] = hub.id


@callback
def async_add_devices_as_they_appear(
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[MaxCubeCoordinator, MaxDevice], Iterable[Entity]],
) -> None:
    """Create entities for every device now and for each device that appears later.

    A device can be paired with the Cube while Home Assistant runs. It shows up in the next poll
    and gets its entities then, without reloading the entry.
    """
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        cube = coordinator.cube
        new = [device for device in cube.devices if device.rf_address not in known]
        if not new:
            return
        known.update(device.rf_address for device in new)
        async_add_entities([entity for device in new for entity in factory(coordinator, device)])

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class MaxCubeEntity(CoordinatorEntity[MaxCubeCoordinator]):
    """Base class tying a MAX! device to its coordinator and device entry."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the entity and its device registry entry."""
        super().__init__(coordinator)
        self._device = device
        self._rf_address = device.rf_address

        suggested_area: str | None = None
        room_id = getattr(device, "room_id", None)
        if room_id:
            try:
                room = coordinator.cube.room_by_id(room_id)
                suggested_area = room.name if room else None
            except Exception:  # noqa: BLE001 - defensive, library shape varies
                suggested_area = None

        cube_serial = getattr(coordinator.cube, "serial", None)
        info = DeviceInfo(
            identifiers={(DOMAIN, device.rf_address)},
            name=device.name or f"MAX! {device.rf_address}",
            manufacturer=MANUFACTURER,
            model=DEVICE_TYPE_NAMES.get(device.type, "MAX! Device"),
            serial_number=getattr(device, "serial", None),
            suggested_area=suggested_area,
        )
        _apply_hub_link(info, coordinator, cube_serial)
        self._attr_device_info = info

    @property
    def available(self) -> bool:
        """Return if entity is available.

        The device's own RF state does not affect availability: a device with a
        radio fault must stay visible, otherwise the diagnostic sensors could
        never report it.  Only a failed Cube connection takes entities offline,
        which is what ``super().available`` already reports.
        """
        return super().available
