"""Immutable snapshot of the Cube state, taken at the end of every poll (no Home Assistant imports).

The library objects (``MaxCube``, ``MaxThermostat``, ...) are changed in place by the next poll,
which runs in the executor thread. Entities therefore read this snapshot instead: it is built once
per poll from the library objects and never changes afterwards. Commands still go to the library
objects and the Cube, as before.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from maxcube.device import (
    MAX_THERMOSTAT,
    MAX_THERMOSTAT_PLUS,
    MAX_WALL_THERMOSTAT,
    MAX_WINDOW_SHUTTER,
    MaxDevice,
)

from .linkstatus import DeviceStatus, LinkStatusMaxCube

# The weekly programme of a thermostat: per day (in the order of the programme) its setpoints as
# ``(until "HH:MM", temperature)``. A tuple, so that nothing can change it after the poll.
Schedule = tuple[tuple[str, tuple[tuple[str, float], ...]], ...]

_UNKNOWN_STATUS = DeviceStatus(
    initialized=None, error=None, link_error=None, last_heard=None, stale=True
)


@dataclass(frozen=True, slots=True)
class DeviceState:
    """The values of one MAX! device at the time of the poll. ``None`` means unknown.

    ``battery_low`` is the held value (see ``health.BatteryHold``), ``battery_raw`` the flag as the
    Cube sent it in this poll.
    """

    rf_address: str
    kind: int | None = None
    serial: str | None = None
    name: str | None = None
    room_id: int | None = None
    battery_low: bool | None = None
    battery_raw: bool | None = None
    mode: int | None = None
    target_temperature: float | None = None
    actual_temperature: float | None = None
    valve_position: int | None = None
    is_open: bool | None = None
    comfort_temperature: float | None = None
    eco_temperature: float | None = None
    min_temperature: float | None = None
    max_temperature: float | None = None
    schedule: Schedule = ()
    status: DeviceStatus = _UNKNOWN_STATUS

    @property
    def is_thermostat(self) -> bool:
        """Return True for a radiator thermostat (as ``MaxDevice.is_thermostat``)."""
        return self.kind in (MAX_THERMOSTAT, MAX_THERMOSTAT_PLUS)

    @property
    def is_wallthermostat(self) -> bool:
        """Return True for a wall thermostat."""
        return self.kind == MAX_WALL_THERMOSTAT

    @property
    def is_windowshutter(self) -> bool:
        """Return True for a window contact."""
        return self.kind == MAX_WINDOW_SHUTTER


@dataclass(frozen=True, slots=True)
class CubeSnapshot:
    """The state of the Cube and of all its devices after one poll."""

    serial: str | None
    firmware_version: str | None
    duty_cycle: int | None
    free_memory_slots: int | None
    devices: Mapping[str, DeviceState]
    room_names: Mapping[int, str]
    # Last S-message values: 1 means the Cube discarded a command. ``None`` means
    # no S message has been seen yet, not "0".
    queue_status: int | None = None
    queued_telegrams: int | None = None
    pending_telegrams: int = 0
    rejected_commands: int = 0

    def device(self, rf_address: str) -> DeviceState:
        """Return the state of one device; a device that is not in this snapshot is unknown."""
        state = self.devices.get(rf_address)
        if state is None:
            return DeviceState(rf_address=rf_address)
        return state


def take_snapshot(
    cube: LinkStatusMaxCube,
    stale_after: float,
    held_battery: Callable[[str, bool], bool],
) -> CubeSnapshot:
    """Copy the values of the library objects; call it in the executor, right after a poll.

    ``held_battery(rf_address, raw_low)`` returns the low-battery state to show (the coordinator
    feeds its ``BatteryHold`` with it, so it is called once per device and poll, in order).

    The stale flag of a device is decided at this moment (``stale_after`` seconds after the last
    frame of that device). While the Cube cannot be read, the snapshot of the last successful poll
    stays in place: the entities are unavailable then, and their stale flags are not updated.
    """
    devices: dict[str, DeviceState] = {}
    for device in cube.devices:
        rf_address = device.rf_address
        raw_low = bool(getattr(device, "battery", 0))
        devices[rf_address] = _device_state(
            device,
            battery_low=held_battery(rf_address, raw_low),
            battery_raw=raw_low,
            status=cube.device_status(rf_address, stale_after),
        )
    log = getattr(cube, "telegram_log", None)
    counts = log.summary() if log is not None else {}
    queue = log.queue_status if log is not None else {}
    return CubeSnapshot(
        serial=getattr(cube, "serial", None),
        firmware_version=getattr(cube, "firmware_version", None),
        duty_cycle=getattr(cube, "duty_cycle", None),
        free_memory_slots=getattr(cube, "free_memory_slots", None),
        devices=MappingProxyType(devices),
        room_names=MappingProxyType({room.id: room.name for room in getattr(cube, "rooms", [])}),
        queue_status=queue.get("status"),
        queued_telegrams=queue.get("queued_telegrams"),
        pending_telegrams=counts.get("pending", 0),
        rejected_commands=log.rejected_count if log is not None else 0,
    )


def _device_state(
    device: MaxDevice, *, battery_low: bool, battery_raw: bool, status: DeviceStatus
) -> DeviceState:
    """Copy the values of one library device; attributes a device kind does not have stay ``None``."""
    return DeviceState(
        rf_address=device.rf_address,
        kind=getattr(device, "type", None),
        serial=getattr(device, "serial", None),
        name=getattr(device, "name", None),
        room_id=getattr(device, "room_id", None),
        battery_low=battery_low,
        battery_raw=battery_raw,
        mode=getattr(device, "mode", None),
        target_temperature=getattr(device, "target_temperature", None),
        actual_temperature=getattr(device, "actual_temperature", None),
        valve_position=getattr(device, "valve_position", None),
        is_open=getattr(device, "is_open", None),
        comfort_temperature=getattr(device, "comfort_temperature", None),
        eco_temperature=getattr(device, "eco_temperature", None),
        min_temperature=getattr(device, "min_temperature", None),
        max_temperature=getattr(device, "max_temperature", None),
        schedule=_freeze_schedule(getattr(device, "schedule", None)),
        status=status,
    )


def _freeze_schedule(schedule: Mapping[str, list[dict[str, Any]]] | None) -> Schedule:
    """Turn the programme of the library (a dict of lists of dicts) into nested tuples."""
    if not schedule:
        return ()
    return tuple(
        (day, tuple((slot["until"], slot["temp"]) for slot in slots))
        for day, slots in schedule.items()
    )


def schedule_as_dict(schedule: Schedule) -> dict[str, list[dict[str, Any]]]:
    """Return a fresh copy of a snapshot programme in the shape the services and attributes use."""
    return {
        day: [{"until": until, "temp": temp} for until, temp in slots] for day, slots in schedule
    }
