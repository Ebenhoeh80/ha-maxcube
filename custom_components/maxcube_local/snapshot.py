"""Immutable snapshot of the Cube state, taken at the end of every poll (no Home Assistant imports).

The library objects (``MaxCube``, ``MaxThermostat``, ...) are changed in place by the next poll,
which runs in the executor thread. Entities therefore read this snapshot instead: it is built once
per poll from the library objects and never changes afterwards. Commands still go to the library
objects and the Cube, as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from maxcube.device import MaxDevice

from .linkstatus import DeviceStatus, LinkStatusMaxCube

# The weekly programme of a thermostat: per day (in the order of the programme) its setpoints as
# ``(until "HH:MM", temperature)``. A tuple, so that nothing can change it after the poll.
Schedule = tuple[tuple[str, tuple[tuple[str, float], ...]], ...]

_UNKNOWN_STATUS = DeviceStatus(
    initialized=None, error=None, link_error=None, last_heard=None, stale=True
)


@dataclass(frozen=True, slots=True)
class DeviceState:
    """The values of one MAX! device at the time of the poll. ``None`` means unknown."""

    rf_address: str
    kind: int | None = None
    serial: str | None = None
    name: str | None = None
    room_id: int | None = None
    battery_low: bool | None = None
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


@dataclass(frozen=True, slots=True)
class CubeSnapshot:
    """The state of the Cube and of all its devices after one poll."""

    serial: str | None
    firmware_version: str | None
    duty_cycle: int | None
    free_memory_slots: int | None
    devices: Mapping[str, DeviceState]

    def device(self, rf_address: str) -> DeviceState:
        """Return the state of one device; a device that is not in this snapshot is unknown."""
        state = self.devices.get(rf_address)
        if state is None:
            return DeviceState(rf_address=rf_address)
        return state


def take_snapshot(
    cube: LinkStatusMaxCube, stale_after: float, battery_low: Mapping[str, bool]
) -> CubeSnapshot:
    """Copy the values of the library objects; call it in the executor, right after a poll."""
    devices: dict[str, DeviceState] = {}
    for device in cube.devices:
        rf_address = device.rf_address
        devices[rf_address] = _device_state(
            device,
            battery_low=battery_low.get(rf_address),
            status=cube.device_status(rf_address, stale_after),
        )
    return CubeSnapshot(
        serial=getattr(cube, "serial", None),
        firmware_version=getattr(cube, "firmware_version", None),
        duty_cycle=getattr(cube, "duty_cycle", None),
        free_memory_slots=getattr(cube, "free_memory_slots", None),
        devices=MappingProxyType(devices),
    )


def _device_state(
    device: MaxDevice, *, battery_low: bool | None, status: DeviceStatus
) -> DeviceState:
    """Copy the values of one library device; attributes a device kind does not have stay ``None``."""
    return DeviceState(
        rf_address=device.rf_address,
        kind=getattr(device, "type", None),
        serial=getattr(device, "serial", None),
        name=getattr(device, "name", None),
        room_id=getattr(device, "room_id", None),
        battery_low=battery_low,
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
        day: [{"until": until, "temp": temp} for until, temp in slots]
        for day, slots in schedule
    }
