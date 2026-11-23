"""Button platform for eQ-3 MAX! Cube (reboot).

The Cube listens for a UDP broadcast on port 23272 — the same port used for
LAN discovery.  The reboot request is a single datagram::

    eQ3Max* + NUL + <10-character serial> + 'R'

sent to 255.255.255.255:23272.  This is separate from the TCP connection on
port 62910 that carries device data, so the integration does not need to tear
down its live connection to reboot the Cube.

Serial validation mirrors the reference implementation: exactly 10 characters,
otherwise the datagram is meaningless and would be dropped.
"""

from __future__ import annotations

import logging
import socket

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from maxcube.device import MaxDevice

from .const import DOMAIN
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity, async_add_devices_as_they_appear
from .snapshot import DeviceState

_LOGGER = logging.getLogger(__name__)

# Port and address the Cube listens on for control datagrams.
CUBE_CONTROL_PORT = 23272
CUBE_BROADCAST = "255.255.255.255"

# Payload prefix the Cube expects; 'R' is the reboot opcode.
_MAGIC_PREFIX = b"eQ3Max*\x00"
_REBOOT_OPCODE = b"R"
_SERIAL_LENGTH = 10

# Bound the blocking socket call; the send is fire-and-forget.
_SEND_TIMEOUT = 3.0


# a press talks to the Cube: the coordinator does the polling
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the reboot button for a MAX! Cube."""
    coordinator = entry.runtime_data
    async_add_entities([MaxCubeRebootButton(coordinator)])
    async_add_devices_as_they_appear(entry, async_add_entities, _display_buttons)


def _display_buttons(
    coordinator: MaxCubeCoordinator, state: DeviceState, device: MaxDevice
) -> list[Entity]:
    """Two buttons per wall thermostat: show the room temperature, or show the setpoint.

    Radiator thermostats have no display setting, so they get no buttons. The current setting can not
    be read back from the Cube, so no state is shown (see ``display.py``).
    """
    if not state.is_wallthermostat:
        return []
    return [
        MaxCubeDisplayButton(coordinator, state, device, key=key, show_actual=show_actual)
        for key, show_actual in (("show_room_temperature", True), ("show_setpoint", False))
    ]


class MaxCubeRebootButton(ButtonEntity):
    """Restarts the MAX! Cube by sending it a control datagram."""

    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    # A press restarts the Cube, so it must be switched on deliberately.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: MaxCubeCoordinator) -> None:
        """Initialize the button on the Cube's hub device."""
        super().__init__()
        self.coordinator = coordinator
        self._serial = coordinator.data.serial or ""
        self._attr_unique_id = f"{self._serial}_reboot"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._serial)})

    @property
    def available(self) -> bool:
        """Return True if the coordinator is available."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Send the reboot datagram to the Cube."""
        if len(self._serial) != _SERIAL_LENGTH:
            _LOGGER.error(
                "Cannot reboot MAX! Cube: its identity has an unexpected length (%d, expected %d)",
                len(self._serial),
                _SERIAL_LENGTH,
            )
            return

        payload = _MAGIC_PREFIX + self._serial.encode("ascii") + _REBOOT_OPCODE

        # Blocking socket work belongs in the executor, not the event loop.
        await self.hass.async_add_executor_job(self._send_reboot, payload)
        _LOGGER.info("Sent reboot request to MAX! Cube")

    @staticmethod
    def _send_reboot(payload: bytes) -> None:
        """Broadcast the reboot datagram; never raises on a network error."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(_SEND_TIMEOUT)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(payload, (CUBE_BROADCAST, CUBE_CONTROL_PORT))
        except OSError as err:
            _LOGGER.warning("Could not send the reboot request to the MAX! Cube: %s", err)
        finally:
            sock.close()


class MaxCubeDisplayButton(MaxCubeEntity, ButtonEntity):
    """Sets what a wall thermostat shows on its display: the room temperature or the setpoint."""

    def __init__(
        self,
        coordinator: MaxCubeCoordinator,
        state: DeviceState,
        device: MaxDevice,
        *,
        key: str,
        show_actual: bool,
    ) -> None:
        """Initialize the button on the wall thermostat's device."""
        super().__init__(coordinator, state, device)
        self._show_actual = show_actual
        self._attr_translation_key = key
        self._attr_unique_id = f"{state.serial or state.rf_address}_{key}"

    async def async_press(self) -> None:
        """Send the display setting to the wall thermostat (checked against the radio budget first)."""
        await self.coordinator.async_set_display(self._rf_address, self._show_actual)
