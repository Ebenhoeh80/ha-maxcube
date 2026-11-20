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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator

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
        cube = coordinator.cube
        self._serial = cube.serial or ""
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
                "Cannot reboot MAX! Cube: serial %r has %d characters, expected %d",
                self._serial,
                len(self._serial),
                _SERIAL_LENGTH,
            )
            return

        payload = _MAGIC_PREFIX + self._serial.encode("ascii") + _REBOOT_OPCODE

        # Blocking socket work belongs in the executor, not the event loop.
        await self.hass.async_add_executor_job(self._send_reboot, payload)
        _LOGGER.info("Sent reboot request to MAX! Cube %s", self._serial)

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

