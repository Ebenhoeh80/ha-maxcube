"""Data update coordinator for the eQ-3 MAX! Cube.

The ``maxcube-api`` library is fully synchronous and opens a short-lived TCP
connection to the Cube LAN gateway for every poll, so all library calls are run
in the executor. The Cube accepts only a single connection at a time.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .linkstatus import DeviceStatus, LinkStatusMaxCube

_LOGGER = logging.getLogger(__name__)

type MaxCubeConfigEntry = ConfigEntry[MaxCubeCoordinator]

# A device counts as stale when nothing was heard from it for this long.  Never
# shorter than 90 s, so a fast poll interval does not flap the sensor.
MIN_STALE_AFTER = 90


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
        self.scan_interval = scan_interval
        # Three missed polls before a device is considered stale.
        self.stale_after = max(3 * scan_interval, MIN_STALE_AFTER)
        self.cube: LinkStatusMaxCube | None = None

    def _connect(self) -> LinkStatusMaxCube:
        """Build the MaxCube; the constructor performs the initial read (blocking)."""
        return LinkStatusMaxCube(self._host, self._port, now=dt_util.utcnow)

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

    def device_status(self, rf_address: str) -> DeviceStatus:
        """Return the RF link status for one device.

        Falls back to an all-unknown, stale status while the Cube object has not
        been built yet, so entities can always read a well-formed value.
        """
        if self.cube is None:
            return DeviceStatus(
                initialized=None, error=None, link_error=None, last_heard=None, stale=True
            )
        return self.cube.device_status(rf_address, self.stale_after)
