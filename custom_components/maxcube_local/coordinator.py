"""Data update coordinator for the eQ-3 MAX! Cube.

The ``maxcube-api`` library is fully synchronous, so all library calls are run in the executor.
The Cube accepts only a single connection at a time, so the connection is opened for every poll
and closed again afterwards: other clients (the MAX! software) can use the Cube in between, and
every poll starts with a fresh ``H:`` line, which carries the duty cycle and the free memory slots.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_CUBE_SERIAL, DOMAIN, REDISCOVER_COOLDOWN
from .cube import MaxCubeWithStatus
from .discovery import discover_cubes, find_host

_LOGGER = logging.getLogger(__name__)

type MaxCubeConfigEntry = ConfigEntry[MaxCubeCoordinator]


class MaxCubeCoordinator(DataUpdateCoordinator[None]):
    """Owns the blocking MaxCube object and refreshes it in the executor."""

    config_entry: MaxCubeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MaxCubeConfigEntry,
        host: str,
        port: int,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._host = host
        self._port = port
        self._last_rediscovery = float("-inf")
        self.cube: MaxCubeWithStatus | None = None

    def _connect(self) -> MaxCubeWithStatus:
        """Build the MaxCube; the constructor performs the initial read (blocking)."""
        cube = MaxCubeWithStatus(self._host, self._port)
        # From now on every poll opens its own short connection (see the module docstring).
        cube.use_persistent_connection = False
        cube.disconnect()
        return cube

    async def _async_setup(self) -> None:
        """Open the connection once before the first refresh."""
        self.cube = await self.hass.async_add_executor_job(self._connect)

    async def _async_update_data(self) -> None:
        """Refresh all device states from the Cube."""
        if self.cube is None:
            self.cube = await self.hass.async_add_executor_job(self._connect)
            return
        try:
            await self.hass.async_add_executor_job(self.cube.update)
        except (OSError, TimeoutError) as err:
            if await self._async_rediscover():
                raise UpdateFailed(
                    "The MAX! Cube has a new IP address; reloading with the new address"
                ) from err
            raise UpdateFailed(f"Error communicating with MAX! Cube: {err}") from err

    async def _async_rediscover(self) -> bool:
        """Look for the Cube under a new IP address (it may have got a new DHCP lease).

        Returns True if a new address was found and saved; the entry then reloads by itself.
        """
        serial = self.config_entry.data.get(CONF_CUBE_SERIAL)
        now = time.monotonic()
        if not serial or now - self._last_rediscovery < REDISCOVER_COOLDOWN:
            return False
        self._last_rediscovery = now
        cubes = await self.hass.async_add_executor_job(discover_cubes)
        new_host = find_host(cubes, serial)
        if new_host is None or new_host == self._host:
            return False
        _LOGGER.warning("MAX! Cube %s moved from %s to %s", serial, self._host, new_host)
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_HOST: new_host},
            unique_id=new_host,
        )
        return True

    async def async_reconnect(self) -> None:
        """Close the connection and read everything from the Cube again."""
        if self.cube is not None:
            await self.hass.async_add_executor_job(self.cube.disconnect)
        await self.async_request_refresh()
