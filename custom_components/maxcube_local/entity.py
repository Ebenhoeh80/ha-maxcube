"""Shared entity base for eQ-3 MAX! Cube devices."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, cast

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from maxcube.device import MaxDevice

from .const import DEVICE_TYPE_NAMES, DOMAIN, MANUFACTURER
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .snapshot import DeviceState

# Home Assistant 2026.11 links a device to its hub by registry id (``via_device_id``)
# and deprecates ``via_device`` (removed in 2027.8). Older versions only know
# ``via_device``, so the right one is chosen at import time.
_VIA_DEVICE_ID = hasattr(dr.DeviceRegistry, "async_get_device_by_identifier") and (
    "via_device_id" in getattr(DeviceInfo, "__annotations__", {})
)


def _apply_hub_link(
    info: DeviceInfo, coordinator: MaxCubeCoordinator, cube_serial: str | None
) -> None:
    """Group a device under the Cube hub (the way this Home Assistant version wants it)."""
    if not cube_serial:
        return
    # DeviceInfo is a version-dependent TypedDict (or a dataclass in newer versions), so the
    # value is treated as a loose mapping for the two spellings.
    values = cast(Any, info)
    if not _VIA_DEVICE_ID:
        # Older Home Assistant versions only know ``via_device``; newer ones removed the key.
        values["via_device"] = (DOMAIN, cube_serial)
        return
    find = getattr(dr.async_get(coordinator.hass), "async_get_device_by_identifier", None)
    if find is None:
        values["via_device"] = (DOMAIN, cube_serial)
        return
    hub = find((DOMAIN, cube_serial), coordinator.config_entry.entry_id)
    if hub is not None:
        if isinstance(values, dict):
            values["via_device_id"] = hub.id
        else:
            values.via_device_id = hub.id


@callback
def async_add_devices_as_they_appear(
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[MaxCubeCoordinator, DeviceState, MaxDevice], Iterable[Entity]],
) -> None:
    """Create entities for every device now and for each device that appears later.

    The devices are taken from the snapshot of the last poll. The library object of a device is
    passed along as well: commands go to it. A device that is no longer in the Cube's list gets
    no entities; the next poll decides.
    """
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [
            state for rf_address, state in coordinator.data.devices.items() if rf_address not in known
        ]
        entities: list[Entity] = []
        for state in new:
            device = coordinator.cube.device_by_rf(state.rf_address)
            if device is None:
                continue
            known.add(state.rf_address)
            entities.extend(factory(coordinator, state, device))
        if entities:
            async_add_entities(entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class MaxCubeEntity(CoordinatorEntity[MaxCubeCoordinator]):
    """Base class tying a MAX! device to its coordinator and device entry.

    Reads go to ``_device_state`` (the snapshot). ``_device`` is the library object, used only to
    send commands to the Cube.
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MaxCubeCoordinator, state: DeviceState, device: MaxDevice
    ) -> None:
        """Initialize the entity and its device registry entry."""
        super().__init__(coordinator)
        self._device = device
        self._rf_address = state.rf_address

        snapshot = coordinator.data
        suggested_area = (
            snapshot.room_names.get(state.room_id) if state.room_id else None
        )
        info = DeviceInfo(
            identifiers={(DOMAIN, state.rf_address)},
            name=state.name or f"MAX! {state.rf_address}",
            manufacturer=MANUFACTURER,
            model=(
                DEVICE_TYPE_NAMES.get(state.kind, "MAX! Device")
                if state.kind is not None
                else "MAX! Device"
            ),
            serial_number=state.serial,
            suggested_area=suggested_area,
        )
        _apply_hub_link(info, coordinator, snapshot.serial)
        self._attr_device_info = info

    @property
    def _device_state(self) -> DeviceState:
        """The values of this device at the last poll; the entity reads nothing else."""
        return self.coordinator.data.device(self._rf_address)

    @property
    def available(self) -> bool:
        """Return if entity is available.

        The device's own RF state does not affect availability: a device with a
        radio fault must stay visible, otherwise the diagnostic sensors could
        never report it.  Only a failed Cube connection takes entities offline,
        which is what ``super().available`` already reports.
        """
        return super().available
