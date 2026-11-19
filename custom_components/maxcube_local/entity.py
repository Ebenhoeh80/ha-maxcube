"""Shared entity base for eQ-3 MAX! Cube devices."""

from __future__ import annotations

from typing import Any

from maxcube.device import MaxDevice

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_NAMES, DOMAIN, MANUFACTURER
from .coordinator import MaxCubeCoordinator


# Home Assistant 2026.11 links a device to its hub by registry id (``via_device_id``)
# and deprecates ``via_device`` (removed in 2027.8). Older versions only know
# ``via_device``, so the right one is chosen at import time.
_VIA_DEVICE_ID = hasattr(dr.DeviceRegistry, "async_get_device_by_identifier") and (
    "via_device_id" in getattr(DeviceInfo, "__dataclass_fields__", {})
)


def _hub_link(
    coordinator: MaxCubeCoordinator, cube_serial: str | None
) -> dict[str, Any]:
    """Return the DeviceInfo fields that group a device under the Cube hub."""
    if not cube_serial:
        return {}
    if not _VIA_DEVICE_ID:
        return {"via_device": (DOMAIN, cube_serial)}
    hub = dr.async_get(coordinator.hass).async_get_device_by_identifier(
        (DOMAIN, cube_serial), coordinator.config_entry.entry_id
    )
    return {"via_device_id": hub.id} if hub is not None else {}


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.rf_address)},
            name=device.name or f"MAX! {device.rf_address}",
            manufacturer=MANUFACTURER,
            model=DEVICE_TYPE_NAMES.get(device.type, "MAX! Device"),
            serial_number=getattr(device, "serial", None),
            suggested_area=suggested_area,
            **_hub_link(coordinator, cube_serial),
        )
