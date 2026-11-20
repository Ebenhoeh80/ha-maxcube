"""Data update coordinator for the eQ-3 MAX! Cube.

The ``maxcube-api`` library is fully synchronous, so all library calls are run in the executor.
The Cube accepts only a single connection at a time, so the connection is opened for every poll
and closed again afterwards: other clients (the MAX! software) can use the Cube in between, and
every poll starts with a fresh ``H:`` line, which carries the duty cycle and the free memory slots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_CUBE_SERIAL, DOMAIN, REDISCOVER_COOLDOWN, SCHEDULE_VERIFY_DELAY
from .cube import MaxCubeWithStatus
from .discovery import discover_cubes, hosts_for_serial, is_reachable

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
        self._write_lock = asyncio.Lock()
        self.cube: MaxCubeWithStatus | None = None

    def _connect(self) -> MaxCubeWithStatus:
        """Build the MaxCube; the constructor performs the initial read (blocking)."""
        cube = MaxCubeWithStatus(self._host, self._port)
        # From now on every poll opens its own short connection (see the module docstring).
        cube.use_persistent_connection = False
        cube.disconnect()
        return cube

    async def _async_setup(self) -> None:
        """Open the connection once before the first refresh.

        If the saved address does not answer, the Cube is looked up by its serial number: it may
        have got a new address while Home Assistant was not running or while the Cube was off.
        """
        try:
            self.cube = await self.hass.async_add_executor_job(self._connect)
        except (OSError, TimeoutError):
            self._last_rediscovery = time.monotonic()
            new_host = await self._async_find_new_host()
            if new_host is None:
                raise
            self._adopt_host(new_host)
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
        now = time.monotonic()
        if now - self._last_rediscovery < REDISCOVER_COOLDOWN:
            return False
        self._last_rediscovery = now
        new_host = await self._async_find_new_host()
        if new_host is None:
            return False
        self._adopt_host(new_host)
        return True

    async def _async_find_new_host(self) -> str | None:
        """Return a new address of this Cube that answers on the data port, if there is one."""
        serial = self.config_entry.data.get(CONF_CUBE_SERIAL)
        if not serial:
            return None
        cubes = await self.hass.async_add_executor_job(discover_cubes)
        for host in hosts_for_serial(cubes, serial):
            if host == self._host:
                continue
            if await self.hass.async_add_executor_job(is_reachable, host, self._port):
                return host
            _LOGGER.debug("MAX! Cube %s answers from %s, which cannot be reached; ignored", serial, host)
        return None

    def _adopt_host(self, new_host: str) -> None:
        """Save a new address of the Cube and use it from now on."""
        _LOGGER.warning(
            "MAX! Cube %s moved from %s to %s",
            self.config_entry.data.get(CONF_CUBE_SERIAL),
            self._host,
            new_host,
        )
        self._host = new_host
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_HOST: new_host},
            unique_id=new_host,
        )

    def _send_days(self, device, days: dict[str, list[dict]]) -> dict[str, bool]:
        """Send the programme of each day (blocking, runs in the executor)."""
        return {day: self.cube.write_day_schedule(device, day, slots) for day, slots in days.items()}

    async def async_write_schedule(self, device, days: dict[str, list[dict]]) -> dict[str, str]:
        """Write the programme of the given days and check, by reading it back, what arrived.

        Returns ``{day: "confirmed" | "sent_not_confirmed" | "failed"}``. ``confirmed`` means the
        Cube already reports exactly the requested programme. ``sent_not_confirmed`` means the Cube
        took the message but still shows the old programme: it updates its copy only after the
        thermostat has taken the change (about two minutes), so these days are checked again later
        and a warning is logged if they still differ.
        """
        async with self._write_lock:
            sent = await self.hass.async_add_executor_job(self._send_days, device, days)
            await self.async_refresh()
        stored = getattr(device, "schedule", None) or {}
        results: dict[str, str] = {}
        for day, slots in days.items():
            if stored.get(day) == slots:
                results[day] = "confirmed"
            else:
                results[day] = "sent_not_confirmed" if sent[day] else "failed"
        pending = {day: days[day] for day, result in results.items() if result == "sent_not_confirmed"}
        if pending:
            self.config_entry.async_on_unload(
                async_call_later(
                    self.hass,
                    SCHEDULE_VERIFY_DELAY,
                    lambda _now: self.hass.async_create_task(
                        self._async_verify_schedule(device, pending)
                    ),
                )
            )
        return results

    async def _async_verify_schedule(self, device, days: dict[str, list[dict]]) -> None:
        """Check again, a few minutes after a write, whether the Cube shows the new programme."""
        await self.async_refresh()
        stored = getattr(device, "schedule", None) or {}
        differing = [day for day, slots in days.items() if stored.get(day) != slots]
        if differing:
            _LOGGER.warning(
                "The Cube still shows the old weekly programme of %s for %s, %d s after it was sent. "
                "The thermostat may not have taken it (check its batteries and its range to the Cube)",
                getattr(device, "name", device.rf_address),
                ", ".join(differing),
                SCHEDULE_VERIFY_DELAY,
            )

    async def async_reconnect(self) -> None:
        """Close the connection and read everything from the Cube again."""
        if self.cube is not None:
            await self.hass.async_add_executor_job(self.cube.disconnect)
        await self.async_request_refresh()
