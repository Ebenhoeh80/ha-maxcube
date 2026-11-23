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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from maxcube.device import MaxDevice

from .const import (
    CONF_CUBE_SERIAL,
    DOMAIN,
    M_MESSAGE_SAVE_DELAY,
    MAX_DUTY_CYCLE_FOR_WRITING,
    POLL_RETRY_DELAY,
    REDISCOVER_COOLDOWN,
    REQUEST_REFRESH_COOLDOWN,
    SCHEDULE_VERIFY_DELAY,
    STORAGE_VERSION,
)
from .discovery import discover_cubes, hosts_for_serial, is_reachable
from .health import BatteryHold
from .linkstatus import LinkStatusMaxCube
from .schedule import ScheduleError, changed_days, check_radio_budget, source_programme
from .snapshot import CubeSnapshot, DeviceState, schedule_as_dict, take_snapshot

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

type MaxCubeConfigEntry = ConfigEntry[MaxCubeCoordinator]

# A device counts as stale when nothing was heard from it for this long.  Never
# shorter than 90 s, so a fast poll interval does not flap the sensor.
MIN_STALE_AFTER = 90


class WrongCubeError(HomeAssistantError):
    """A different Cube than the one of this entry answers at the saved address.

    This is an identity mismatch, not a network failure. Keeping it separate from ``OSError``
    prevents a wrong Cube from being reported as "cannot reach" and lets rediscovery by serial
    number stay the explicit recovery path.
    """

    def __init__(self, message: str) -> None:
        """Carry a translation key so a service error is localised if it escapes a poll."""
        super().__init__(
            message, translation_domain=DOMAIN, translation_key="wrong_cube"
        )


def m_message_storage_key(entry_id: str) -> str:
    """Return the name of the file that keeps the last readable M message of an entry."""
    return f"{DOMAIN}_{entry_id}_m_message"


class MaxCubeCoordinator(DataUpdateCoordinator[CubeSnapshot]):
    """Owns the blocking MaxCube object and refreshes it in the executor.

    ``data`` is the snapshot of the last successful poll (see ``snapshot.py``): entities read
    only that, never the library objects, which the next poll changes in the executor.
    """

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
        # One dedicated worker serialises every Cube call (poll, command, snapshot, disconnect).
        # An asyncio.Lock would be released when a Home Assistant task is cancelled while its
        # executor thread still talks to the Cube; the next call could then overlap on the
        # single-client port. A one-thread executor keeps the serialization in the worker, where
        # the blocking call actually happens.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maxcube_io")
        # Keeps a whole programme write (send, then read back) together so two writes cannot
        # interleave. It is independent of the worker: the read-back is submitted to that worker
        # while this lock is held, so an asyncio lock for both would deadlock here.
        self._write_lock = asyncio.Lock()
        # Pending "was the programme taken?" checks, one timer per device (see async_write_schedule).
        self._verify_timers: dict[str, Callable[[], None]] = {}
        self._verify_days: dict[str, dict[str, list[dict]]] = {}
        # Whether the pending check may resend once. A retry clears it so a second
        # check only warns instead of writing again (no endless retry loop).
        self._verify_allow_retry: dict[str, bool] = {}
        # Set before anything is awaited in async_shutdown: an already running verification
        # callback must not start a new write while the entry is going away.
        self._shutting_down = False
        self._shutdown_started = False
        self._worker_closed = False
        entry.async_on_unload(self._cancel_verifications)
        # What the last polls cost (shown in the diagnostics).
        self.last_poll_ms: int | None = None
        self.polls = 0
        self.failed_polls = 0
        self.scan_interval = scan_interval
        # Three missed polls before a device is considered stale.
        self.stale_after = max(3 * scan_interval, MIN_STALE_AFTER)
        self._cube: LinkStatusMaxCube | None = None
        # Low-battery reports are held for a while (see ``BatteryHold``); the held value is in the snapshot.
        self._battery_hold = BatteryHold()
        # The last readable M message, saved between restarts (see ``_remember_m_message``).
        self._store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, m_message_storage_key(entry.entry_id)
        )
        self._saved_m_message: str | None = None
        # Polls in a row in which the Cube sent no readable M message (see ``issues.py``).
        self.m_missing_polls = 0

    @property
    def cube(self) -> LinkStatusMaxCube:
        """Return the Cube; it exists as soon as the first refresh has succeeded."""
        if self._cube is None:
            raise RuntimeError("The MAX! Cube is not connected yet")
        return self._cube

    def _connect(self, host: str | None = None) -> LinkStatusMaxCube:
        """Build the MaxCube; the constructor performs the initial read (blocking).

        ``host`` lets a candidate address from discovery be checked before it is saved. A
        Cube answering under a different serial is rejected here, so an unauthenticated discovery
        answer cannot redirect this entry to a device that is not ours. A Cube that reports no
        serial at all cannot be distinguished this way (see ``_check_identity``).
        """
        cube = LinkStatusMaxCube(
            host or self._host, self._port, now=dt_util.now, last_m_message=self._saved_m_message
        )
        try:
            self._check_identity(cube)
        except WrongCubeError:
            cube.disconnect()
            raise
        # From now on every poll opens its own short connection (see the module docstring).
        cube.use_persistent_connection = False
        cube.disconnect()
        return cube

    def _check_identity(
        self, cube: LinkStatusMaxCube, *, require_serial: bool = False
    ) -> None:
        """Make sure the Cube that answers is the one this entry belongs to (compared by serial number).

        Normal polls stay permissive when a Cube reports no serial at all: older setups and
        migrations must keep working. A discovery candidate is checked strictly (``require_serial``),
        because its address is only adopted after the identity has been confirmed.
        """
        expected = self.config_entry.data.get(CONF_CUBE_SERIAL)
        if not expected:
            return
        if require_serial:
            mismatch = cube.serial != expected
        else:
            mismatch = bool(cube.serial) and cube.serial != expected
        if mismatch:
            # Do not put serial numbers in logs or user-facing errors: they are unauthenticated
            # identifiers and are redacted from diagnostics for the same reason.
            raise WrongCubeError(
                "A different MAX! Cube answers at the saved address; "
                "this entry belongs to another device"
            )

    async def _async_setup(self) -> None:
        """Load the saved M message, then open the connection once before the first refresh.

        If the saved address does not answer, the Cube is looked up by its serial number: it may
        have got a new address while Home Assistant was not running or while the Cube was off.
        """
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("m_message"), str):
            self._saved_m_message = stored["m_message"]
        try:
            self._cube = await self._async_io_call(self._connect)
        except WrongCubeError as err:
            self._last_rediscovery = time.monotonic()
            new_host = await self._async_find_new_host()
            if new_host is None:
                raise UpdateFailed(str(err)) from err
            self._cube = await self._async_connect_at(new_host)
            self._adopt_host(new_host)
        except (OSError, TimeoutError) as err:
            self._last_rediscovery = time.monotonic()
            new_host = await self._async_find_new_host()
            if new_host is None:
                raise UpdateFailed(f"Cannot reach the MAX! Cube at {self._host}: {err}") from err
            self._cube = await self._async_connect_at(new_host)
            self._adopt_host(new_host)

    async def _async_connect_at(self, host: str) -> LinkStatusMaxCube:
        """Connect to a discovery candidate and verify it before its address is saved.

        Discovery answers are unauthenticated. Persisting a candidate before its serial has been
        checked would let a forged reply redirect this entry permanently. A failed check leaves
        the saved address untouched.
        """
        try:
            cube = await self._async_io_call(self._connect, host)
            # A candidate with no serial cannot be confirmed; do not save its address.
            self._check_identity(cube, require_serial=True)
            return cube
        except WrongCubeError as err:
            raise UpdateFailed(str(err)) from err
        except HomeAssistantError as err:
            raise UpdateFailed(str(err)) from err
        except (OSError, TimeoutError) as err:
            raise UpdateFailed(
                f"Cannot reach the MAX! Cube at the discovered address: {err}"
            ) from err

    async def _async_update_data(self) -> CubeSnapshot:
        """Refresh all device states from the Cube and return the snapshot of this poll."""
        if self._shutting_down:
            # A refresh racing the unload is expected; UpdateFailed keeps it out of the error log.
            raise UpdateFailed("The MAX! Cube connection is shutting down")
        try:
            if self._cube is None:
                self._cube = await self._async_io_call(self._connect)
            else:
                await self._async_poll(self._cube)
                self._check_identity(self._cube)
            # Shutdown can start while either await above is in flight.
            self._raise_if_shutting_down()
            snapshot = await self._async_snapshot(self._cube)
            self._raise_if_shutting_down()
            self._sync_device_names(snapshot)
            return snapshot
        except WrongCubeError as err:
            if await self._async_rediscover():
                raise UpdateFailed(
                    "A different MAX! Cube answered at the saved address; "
                    "reloading with the configured Cube"
                ) from err
            raise UpdateFailed(str(err)) from err
        except HomeAssistantError as err:
            # Includes the shutdown guard after an await; an unload is not an error to log.
            raise UpdateFailed(str(err)) from err
        except (OSError, TimeoutError) as err:
            if await self._async_rediscover():
                raise UpdateFailed(
                    "The MAX! Cube has a new IP address; reloading with the new address"
                ) from err
            raise UpdateFailed(f"Error communicating with MAX! Cube: {err}") from err

    @staticmethod
    def _device_for_identifier(
        registry: dr.DeviceRegistry, identifier: tuple[str, str], entry_id: str
    ) -> dr.DeviceEntry | None:
        """Find a device by identifier, scoped to this config entry across HA versions."""
        find = getattr(registry, "async_get_device_by_identifier", None)
        if find is not None:
            return find(identifier, entry_id)
        device = registry.async_get_device(identifiers={identifier})
        if device is None:
            return None
        # RF addresses are only three bytes; two Cubes can use the same one.
        single = getattr(device, "config_entry_id", None)
        if single is not None:
            return device if single == entry_id else None
        return device if entry_id in getattr(device, "config_entries", ()) else None

    @callback
    def _sync_device_names(self, snapshot: CubeSnapshot) -> None:
        """Follow a name changed on the Cube without overwriting a name chosen in Home Assistant.

        ``DeviceInfo`` is applied when an entity is added, so a rename in the Cube's ``M`` message
        would otherwise stay invisible until the next reload. This is a deliberate registry write
        in the refresh path: entities are not recreated on a poll. Only devices of this entry with
        no custom name are touched, and only when the name actually changed.
        """
        registry = dr.async_get(self.hass)
        for address, state in snapshot.devices.items():
            if not state.name:
                continue
            device = self._device_for_identifier(
                registry, (DOMAIN, address), self.config_entry.entry_id
            )
            if device is None or device.name_by_user is not None or device.name == state.name:
                continue
            registry.async_update_device(device.id, name=state.name)

    def _remember_m_message(self, cube: LinkStatusMaxCube) -> None:
        """Count the polls without a readable M message and save a new one when it changes.

        The file is written only when the message changes (not on every poll), and the write is
        delayed, so a burst of changes costs one write.
        """
        self.m_missing_polls = self.m_missing_polls + 1 if cube.m_message_missing else 0
        message = cube.last_m_message
        if message and message != self._saved_m_message:
            self._saved_m_message = message
            self._store.async_delay_save(self._m_message_data, M_MESSAGE_SAVE_DELAY)

    @callback
    def _m_message_data(self) -> dict[str, str]:
        """The data written to the file: the Base64 part of the M message and when it was saved."""
        return {
            "m_message": self._saved_m_message or "",
            "saved": dt_util.utcnow().isoformat(),
        }

    async def _async_io_call(
        self, func: Callable[..., T], *args: object, allow_shutdown: bool = False
    ) -> T:
        """Run a blocking Cube call in the dedicated worker (errors pass through).

        The worker has one thread, so calls are serialised even if the awaiting Home Assistant
        task is cancelled: the thread finishes the call before the next one starts. Once shutdown
        has begun no further work may be queued - only the explicit disconnect uses
        ``allow_shutdown`` - otherwise a call could be submitted to a closed executor or slip past
        the disconnect into a new coordinator after a reload.
        """
        if self._shutting_down and not allow_shutdown:
            self._raise_if_shutting_down()
        return await self.hass.loop.run_in_executor(self._executor, func, *args)

    def _raise_if_shutting_down(self) -> None:
        """Reject work that reaches a new await after shutdown has started."""
        if self._shutting_down:
            raise HomeAssistantError(
                "The MAX! Cube connection is shutting down",
                translation_domain=DOMAIN,
                translation_key="cube_shutting_down",
            )

    async def _async_snapshot(self, cube: LinkStatusMaxCube) -> CubeSnapshot:
        """Copy the library state in the same worker as the poll, then remember metadata.

        The copy cannot overlap a Cube call. It is not atomic with the poll: identity checks and
        metadata writes run on the event loop, and another task can queue a command in between.
        The copy is serialised with all worker I/O, but is not guaranteed to be the exact state
        immediately after the poll.
        """
        self._remember_m_message(cube)
        return await self._async_io_call(self._take_snapshot, cube)

    async def async_cube_call(self, func: Callable[..., T], *args: object) -> T:
        """Run a blocking Cube call for a user action, one call at a time.

        Polls, commands and programme writes would otherwise run in different threads on the same
        connection object and could overlap; the Cube then refuses one of them. A network error
        becomes a translated ``HomeAssistantError`` so that the user sees why an action failed
        (the poll uses ``_async_io_call`` and handles the raw error itself).
        """
        try:
            return await self._async_io_call(func, *args)
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
                await self._async_io_call(cube.update)
            except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError) as err:
                _LOGGER.debug("The Cube dropped the connection (%s); trying once more", err)
                await asyncio.sleep(POLL_RETRY_DELAY)
                await self._async_io_call(cube.update)
        except (OSError, TimeoutError):
            self.failed_polls += 1
            raise
        finally:
            self.last_poll_ms = round((time.monotonic() - started) * 1000)

    async def _async_rediscover(self) -> bool:
        """Look for the Cube under a new IP address (it may have got a new DHCP lease).

        Returns True if a new address was found and saved; the entry then reloads by itself.
        """
        if self._shutting_down:
            return False
        now = time.monotonic()
        if now - self._last_rediscovery < REDISCOVER_COOLDOWN:
            return False
        self._last_rediscovery = now
        new_host = await self._async_find_new_host()
        if new_host is None:
            return False
        try:
            await self._async_connect_at(new_host)
        except UpdateFailed:
            return False  # keep the reported error and the saved address
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
            _LOGGER.debug("MAX! Cube answers from %s, which cannot be reached; ignored", host)
        return None

    def _adopt_host(self, new_host: str) -> None:
        """Save a new address of the Cube and use it from now on.

        Only the address changes: the identity of the entry (serial number) and its title stay.
        The update listener of the entry reloads it with the new address.
        """
        _LOGGER.warning("MAX! Cube moved from %s to %s", self._host, new_host)
        self._host = new_host
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: new_host}
        )

    def _send_days(self, device: MaxDevice, days: dict[str, list[dict]]) -> dict[str, bool]:
        """Send the programme of each day (blocking, runs in the executor)."""
        return {day: self.cube.write_day_schedule(device, day, slots) for day, slots in days.items()}

    async def async_write_schedule(
        self, device: MaxDevice, days: dict[str, list[dict]], *, allow_retry: bool = True
    ) -> dict[str, str]:
        """Write the programme of the given days and check, by reading it back, what arrived.

        Returns ``{day: "confirmed" | "sent_not_confirmed" | "failed"}``. ``confirmed`` means the
        Cube already reports exactly the requested programme. ``sent_not_confirmed`` means the Cube
        took the message but still shows the old programme: it updates its copy only after the
        thermostat has taken the change (about two minutes), so these days are checked again later.
        ``allow_retry=False`` is used for that one automatic resend; the second check only warns.
        """
        async with self._write_lock:
            if self._shutting_down:
                return dict.fromkeys(days, "failed")
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
            self._schedule_verification(device, pending, allow_retry=allow_retry)
        return results

    async def async_set_display(self, rf_address: str, show_actual: bool) -> None:
        """Send the display setting of a wall thermostat, unless the Cube is too busy for one more telegram.

        The duty cycle is the one of the last poll; the check is the same as the one for a programme copy.
        """
        try:
            check_radio_budget(self.data.duty_cycle, 1)
        except ScheduleError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="display_radio_too_busy",
                translation_placeholders={"detail": err.detail},
            ) from err
        await self.async_cube_command(self.cube.write_display_setting, rf_address, show_actual)

    def _copy_plans(
        self, source: DeviceState, targets: list[DeviceState], days: list[str]
    ) -> dict[str, dict[str, list[dict]]]:
        """Check a copy and return the days to send to each target (``{address: {day: slots}}``).

        The programmes and the radio budget come from the snapshot of the last poll. Nothing is sent
        when the check fails: the problems are raised as translated service errors.
        """
        for state in (source, *targets):
            if not state.is_thermostat:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="schedule_radiator_only"
                )
        try:
            wanted = source_programme(schedule_as_dict(source.schedule), days)
            plans = {
                target.rf_address: changed_days(wanted, schedule_as_dict(target.schedule))
                for target in targets
            }
            check_radio_budget(self.data.duty_cycle, sum(len(plan) for plan in plans.values()))
        except ScheduleError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=f"schedule_{err.key}",
                translation_placeholders={"detail": err.detail},
            ) from err
        return plans

    async def async_copy_schedule(
        self, source_rf: str, target_rfs: list[str], days: list[str]
    ) -> dict[str, dict[str, str]]:
        """Copy the weekly programme of a radiator thermostat to other radiator thermostats.

        Only the days that differ from a target's programme are written, and the radio time is
        checked before the first telegram. Returns ``{address: {day: state}}``: the states of
        ``async_write_schedule``, and ``"unchanged"`` for the days that were not sent. The
        programmes and the devices are read from the snapshot; the write goes to the library object.
        """
        snapshot = self.data
        plans = self._copy_plans(
            snapshot.device(source_rf), [snapshot.device(rf) for rf in target_rfs], days
        )
        results: dict[str, dict[str, str]] = {}
        for rf_address in target_rfs:
            plan = plans[rf_address]
            states = dict.fromkeys(days, "unchanged")
            if plan:
                device = self.cube.device_by_rf(rf_address)
                if device is None:
                    states.update(dict.fromkeys(plan, "failed"))
                else:
                    states.update(await self.async_write_schedule(device, plan))
            results[rf_address] = states
        failed = [
            f"{day} ({address})"
            for address, states in results.items()
            for day, state in states.items()
            if state == "failed"
        ]
        if failed:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="schedule_not_written",
                translation_placeholders={"days": ", ".join(failed)},
            )
        return results

    def _schedule_verification(
        self, device: MaxDevice, pending: dict[str, list[dict]], *, allow_retry: bool = True
    ) -> None:
        """Check the days in ``pending`` again later; one timer per device, replaced by a new write.

        A second write to the same device before the check merges its days into the same check
        (the newer programme of a day wins) and restarts the wait, so nothing is verified twice and
        no callback is left behind for every write. A new user write re-enables the single retry.
        """
        if self._shutting_down:
            return
        address = device.rf_address
        cancel = self._verify_timers.pop(address, None)
        if cancel is not None:
            cancel()
        self._verify_days[address] = {**self._verify_days.get(address, {}), **pending}
        self._verify_allow_retry[address] = self._verify_allow_retry.get(address, False) or allow_retry

        async def _verify(_now: datetime) -> None:
            self._verify_timers.pop(address, None)
            days = self._verify_days.pop(address, {})
            allow = self._verify_allow_retry.pop(address, False)
            if self._shutting_down:
                return
            await self._async_verify_schedule(device, days, allow_retry=allow)

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
        self._verify_allow_retry.clear()

    async def async_shutdown(self) -> None:
        """Stop the coordinator, release the Cube's port and close the Cube worker.

        The library already disconnects after every poll and command when
        ``use_persistent_connection`` is false, so this explicit call is normally a no-op. It is a
        defensive release for the case that a connection object still holds a socket. Setting
        ``_shutting_down`` first stops any new call from entering the worker; the disconnect is
        queued behind the calls that were already submitted. Awaiting it therefore drains the
        worker before the executor is closed. A network error is logged so shutdown itself does not
        fail. Repeated calls are harmless.
        """
        # Set before the first await: two parallel unloads/stops must not both disconnect.
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._shutting_down = True
        # Also needed when Home Assistant stops without unloading the entry first.
        self._cancel_verifications()
        await super().async_shutdown()
        try:
            if self._cube is not None:
                try:
                    await self._async_io_call(self._cube.disconnect, allow_shutdown=True)
                except (OSError, TimeoutError, HomeAssistantError, RuntimeError) as err:
                    _LOGGER.debug("Could not release the Cube connection during shutdown: %s", err)
        finally:
            # Normally the awaited disconnect drained the queue and the thread exits on its own.
            # wait=False also covers a cancelled shutdown: it never blocks the event loop inside a
            # library socket timeout, and cancel_futures drops work queued after that.
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._worker_closed = True

    async def _async_verify_schedule(
        self, device: MaxDevice, days: dict[str, list[dict]], *, allow_retry: bool = True
    ) -> None:
        """Check again after a write; resend once if the Cube still shows the old programme."""
        await self.async_refresh()
        if self._shutting_down:
            return
        stored = getattr(device, "schedule", None) or {}
        differing = {day: days[day] for day in days if stored.get(day) != days[day]}
        if not differing:
            return
        name = getattr(device, "name", device.rf_address)
        if not allow_retry:
            _LOGGER.warning(
                "The Cube still shows the old weekly programme of %s for %s, %d s after it was sent "
                "and one retry. The thermostat may not have taken it (check its batteries and its "
                "range to the Cube)",
                name,
                ", ".join(differing),
                2 * SCHEDULE_VERIFY_DELAY,
            )
            return
        duty = getattr(self.cube, "duty_cycle", None)
        if duty is not None and duty >= MAX_DUTY_CYCLE_FOR_WRITING:
            _LOGGER.warning(
                "Not retrying the weekly programme of %s for %s: radio duty cycle is %d %%",
                name,
                ", ".join(differing),
                duty,
            )
            return
        _LOGGER.info(
            "Retrying the weekly programme of %s for %s once: the Cube still shows the old one",
            name,
            ", ".join(differing),
        )
        # The retry clears ``allow_retry``; its own check will only warn, never write again.
        try:
            result = await self.async_write_schedule(device, differing, allow_retry=False)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not retry the weekly programme of %s for %s: %s",
                name,
                ", ".join(differing),
                err,
            )
            return
        self._warn_about_retry_result(name, result)

    def _warn_about_retry_result(self, name: str, result: dict[str, str]) -> None:
        """Report a refused retry, unless the coordinator is already shutting down."""
        if self._shutting_down:
            return
        refused = [day for day, status in result.items() if status == "failed"]
        if refused:
            _LOGGER.warning(
                "The Cube refused the retry of the weekly programme of %s for %s",
                name,
                ", ".join(refused),
            )

    async def async_reconnect(self) -> None:
        """Close the connection and read everything from the Cube again."""
        if self._cube is not None:
            await self.async_cube_call(self._cube.disconnect)
        await self.async_request_refresh()

    def _take_snapshot(self, cube: LinkStatusMaxCube) -> CubeSnapshot:
        """Copy the Cube into a snapshot; runs in the dedicated Cube worker.

        Polls, commands and snapshots share that one thread, so the library objects cannot be
        mutated during the copy. The low-battery flags go through ``BatteryHold`` here, so the held
        value is part of the snapshot.
        """
        now = dt_util.utcnow().timestamp()
        return take_snapshot(
            cube,
            self.stale_after,
            lambda rf_address, low: self._battery_hold.update(rf_address, low, now),
        )
