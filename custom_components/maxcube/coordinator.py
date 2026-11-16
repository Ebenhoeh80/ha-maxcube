"""Data update coordinator for the eQ-3 MAX! Cube.

The ``maxcube-api`` library is fully synchronous and opens a short-lived TCP
connection to the Cube LAN gateway for every poll, so all library calls are run
in the executor. The Cube accepts only a single connection at a time.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from maxcube.cube import MaxCube

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

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
        self.cube: MaxCube | None = None

    def _connect(self) -> MaxCube:
        """Build the MaxCube; the constructor performs the initial read (blocking)."""
        return MaxCube(self._host, self._port)

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
            raise UpdateFailed(f"Error communicating with MAX! Cube: {err}") from err
