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
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from maxcube.device import MaxDevice

from .const import (
    CONF_CUBE_SERIAL,
    DOMAIN,
    POLL_RETRY_DELAY,
    REDISCOVER_COOLDOWN,
    REQUEST_REFRESH_COOLDOWN,
    SCHEDULE_VERIFY_DELAY,
)
from .discovery import discover_cubes, hosts_for_serial, is_reachable
from .linkstatus import DeviceStatus, LinkStatusMaxCube

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

type MaxCubeConfigEntry = ConfigEntry[MaxCubeCoordinator]

# A device counts as stale when nothing was heard from it for this long.  Never
# shorter than 90 s, so a fast poll interval does not flap the sensor.
MIN_STALE_AFTER = 90


class WrongCubeError(OSError):
    """A different Cube than the one of this entry answers at the saved address."""


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
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_COOLDOWN, immediate=True
            ),
        )
        self._host = host
        self._port = port
        self._last_rediscovery = float("-inf")
        # Two locks with two jobs; they cannot be merged. ``_io_lock`` makes every single call to
        # the Cube (which accepts one connection at a time) wait for the one before. ``_write_lock``
        # keeps a whole programme write (send, then read back) together so that two writes do not
        # interleave; it is held while the read-back takes ``_io_lock``, so one lock for both would
        # block itself.
        self._write_lock = asyncio.Lock()
        self._io_lock = asyncio.Lock()
        # Pending "was the programme taken?" checks, one timer per device (see async_write_schedule).
        self._verify_timers: dict[str, Callable[[], None]] = {}
        self._verify_days: dict[str, dict[str, list[dict]]] = {}
        entry.async_on_unload(self._cancel_verifications)
        # What the last polls cost (shown in the diagnostics).
        self.last_poll_ms: int | None = None
        self.polls = 0
        self.failed_polls = 0
        self.scan_interval = scan_interval
        # Three missed polls before a device is considered stale.
        self.stale_after = max(3 * scan_interval, MIN_STALE_AFTER)
        self._cube: LinkStatusMaxCube | None = None

    @property
    def cube(self) -> LinkStatusMaxCube:
        """Return the Cube; it exists as soon as the first refresh has succeeded."""
        if self._cube is None:
            raise RuntimeError("The MAX! Cube is not connected yet")
        return self._cube

    def _connect(self) -> LinkStatusMaxCube:
        """Build the MaxCube; the constructor performs the initial read (blocking)."""
        cube = LinkStatusMaxCube(self._host, self._port, now=dt_util.now)
        try:
            self._check_identity(cube)
        except WrongCubeError:
            cube.disconnect()
            raise
        # From now on every poll opens its own short connection (see the module docstring).
        cube.use_persistent_connection = False
        cube.disconnect()
        return cube

    def _check_identity(self, cube: LinkStatusMaxCube) -> None:
        """Make sure the Cube that answers is the one this entry belongs to (compared by serial number)."""
        expected = self.config_entry.data.get(CONF_CUBE_SERIAL)
        if expected and cube.serial and cube.serial != expected:
            raise WrongCubeError(
                f"Another MAX! Cube ({cube.serial}) answers at {self._host}; this entry belongs to {expected}"
            )

    async def _async_setup(self) -> None:
        """Open the connection once before the first refresh.

        If the saved address does not answer, the Cube is looked up by its serial number: it may
        have got a new address while Home Assistant was not running or while the Cube was off.
        """
        try:
            self._cube = await self.hass.async_add_executor_job(self._connect)
        except (OSError, TimeoutError) as err:
            self._last_rediscovery = time.monotonic()
            new_host = await self._async_find_new_host()
            if new_host is None:
                raise UpdateFailed(f"Cannot reach the MAX! Cube at {self._host}: {err}") from err
            self._adopt_host(new_host)
            self._cube = await self.hass.async_add_executor_job(self._connect)

    async def _async_update_data(self) -> None:
        """Refresh all device states from the Cube."""
        if self._cube is None:
            self._cube = await self.hass.async_add_executor_job(self._connect)
            return
        try:
            await self._async_poll(self._cube)
            self._check_identity(self._cube)
        except (OSError, TimeoutError) as err:
            if await self._async_rediscover():
                raise UpdateFailed(
                    "The MAX! Cube has a new IP address; reloading with the new address"
                ) from err
            raise UpdateFailed(f"Error communicating with MAX! Cube: {err}") from err

    async def _async_locked_call(self, func: Callable[..., T], *args: object) -> T:
        """Run a blocking Cube call in the executor, one call at a time (errors pass through)."""
        async with self._io_lock:
            return await self.hass.async_add_executor_job(func, *args)

    async def async_cube_call(self, func: Callable[..., T], *args: object) -> T:
        """Run a blocking Cube call for a user action, one call at a time.

        Polls, commands and programme writes would otherwise run in different threads on the same
        connection object and could overlap; the Cube then refuses one of them. A network error
        becomes a translated ``HomeAssistantError`` so that the user sees why an action failed
        (the poll uses ``_async_locked_call`` and handles the raw error itself).
        """
        try:
            return await self._async_locked_call(func, *args)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cube_unreachable",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err

    async def async_cube_command(self, func: Callable[..., Any], *args: object) -> None:
        """Send a command to the Cube and raise if it does not accept it (returns a false value)."""
        if not await self.async_cube_call(func, *args):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_rejected"
            )

    async def _async_poll(self, cube: LinkStatusMaxCube) -> None:
        """Read the Cube, once more after a refused or dropped connection."""
        started = time.monotonic()
        self.polls += 1
        try:
            try:
                await self._async_locked_call(cube.update)
            except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError) as err:
                _LOGGER.debug("The Cube dropped the connection (%s); trying once more", err)
                await asyncio.sleep(POLL_RETRY_DELAY)
                await self._async_locked_call(cube.update)
        except (OSError, TimeoutError):
            self.failed_polls += 1
            raise
        finally:
            self.last_poll_ms = round((time.monotonic() - started) * 1000)

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
        """Save a new address of the Cube and use it from now on.

        Only the address changes: the identity of the entry (serial number) and its title stay.
        The update listener of the entry reloads it with the new address.
        """
        _LOGGER.warning(
            "MAX! Cube %s moved from %s to %s",
            self.config_entry.data.get(CONF_CUBE_SERIAL),
            self._host,
            new_host,
        )
        self._host = new_host
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: new_host}
        )

    def _send_days(self, device: MaxDevice, days: dict[str, list[dict]]) -> dict[str, bool]:
        """Send the programme of each day (blocking, runs in the executor)."""
        return {day: self.cube.write_day_schedule(device, day, slots) for day, slots in days.items()}

    async def async_write_schedule(
        self, device: MaxDevice, days: dict[str, list[dict]]
    ) -> dict[str, str]:
        """Write the programme of the given days and check, by reading it back, what arrived.

        Returns ``{day: "confirmed" | "sent_not_confirmed" | "failed"}``. ``confirmed`` means the
        Cube already reports exactly the requested programme. ``sent_not_confirmed`` means the Cube
        took the message but still shows the old programme: it updates its copy only after the
        thermostat has taken the change (about two minutes), so these days are checked again later
        and a warning is logged if they still differ.
        """
        async with self._write_lock:
            sent = await self.async_cube_call(self._send_days, device, days)
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
            self._schedule_verification(device, pending)
        return results

    def _schedule_verification(self, device: MaxDevice, pending: dict[str, list[dict]]) -> None:
        """Check the days in ``pending`` again later; one timer per device, replaced by a new write.

        A second write to the same device before the check merges its days into the same check
        (the newer programme of a day wins) and restarts the wait, so nothing is verified twice and
        no callback is left behind for every write.
        """
        address = device.rf_address
        cancel = self._verify_timers.pop(address, None)
        if cancel is not None:
            cancel()
        self._verify_days[address] = {**self._verify_days.get(address, {}), **pending}

        async def _verify(_now: datetime) -> None:
            self._verify_timers.pop(address, None)
            days = self._verify_days.pop(address, {})
            await self._async_verify_schedule(device, days)

        self._verify_timers[address] = async_call_later(
            self.hass, SCHEDULE_VERIFY_DELAY, _verify
        )

    @callback
    def _cancel_verifications(self) -> None:
        """Drop the pending programme checks (the entry is unloaded)."""
        for cancel in self._verify_timers.values():
            cancel()
        self._verify_timers.clear()
        self._verify_days.clear()

    async def async_shutdown(self) -> None:
        """Stop the coordinator, including the pending programme checks."""
        self._cancel_verifications()
        await super().async_shutdown()

    async def _async_verify_schedule(
        self, device: MaxDevice, days: dict[str, list[dict]]
    ) -> None:
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
        if self._cube is not None:
            await self.async_cube_call(self._cube.disconnect)
        await self.async_request_refresh()

    def device_status(self, rf_address: str) -> DeviceStatus:
        """Return the RF link status for one device.

        Falls back to an all-unknown, stale status while the Cube object has not
        been built yet, so entities can always read a well-formed value.
        """
        if self._cube is None:
            return DeviceStatus(
                initialized=None, error=None, link_error=None, last_heard=None, stale=True
            )
        return self._cube.device_status(rf_address, self.stale_after)
