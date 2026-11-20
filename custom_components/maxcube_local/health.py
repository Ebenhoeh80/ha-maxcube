"""Which devices need attention (pure logic, no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

ISSUE_BATTERY = "battery_low"
ISSUE_ERROR = "device_error"


@dataclass(frozen=True, slots=True)
class DeviceFinding:
    """One thing a user should look at."""

    kind: str  # ISSUE_BATTERY or ISSUE_ERROR
    rf_address: str
    name: str


def find_problems(
    devices: Iterable[Any], status_of: Callable[[str], Any]
) -> list[DeviceFinding]:
    """Return the findings for all devices.

    ``status_of(rf_address)`` returns an object with an ``error`` attribute (``True``, ``False`` or
    ``None`` while unknown). A low battery is taken from the device itself.
    """
    findings: list[DeviceFinding] = []
    for device in devices:
        name = device.name or device.rf_address
        if getattr(device, "battery", 0):
            findings.append(DeviceFinding(ISSUE_BATTERY, device.rf_address, name))
        if status_of(device.rf_address).error:
            findings.append(DeviceFinding(ISSUE_ERROR, device.rf_address, name))
    return findings
