"""Which devices need attention (pure logic, no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

ISSUE_BATTERY = "battery_low"
ISSUE_ERROR = "device_error"
ISSUE_UNREACHABLE = "cube_unreachable"
ISSUE_RADIO_BUSY = "radio_busy"

# The Cube counts as lost when it has not answered for this long.
UNREACHABLE_AFTER = 6 * 3600  # seconds
# The radio is "busy" when the duty cycle stays at or above HIGH for SUSTAIN seconds; the hint goes
# away once it has dropped below LOW (the gap keeps it from flapping around the threshold).
DUTY_HIGH = 90  # percent
DUTY_LOW = 80  # percent
DUTY_SUSTAIN = 600  # seconds


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


class DutyCycleWatch:
    """Decides, with hysteresis, whether the Cube's radio has been busy for too long."""

    def __init__(
        self, high: int = DUTY_HIGH, low: int = DUTY_LOW, sustain: float = DUTY_SUSTAIN
    ) -> None:
        """Set the thresholds (percent) and how long the value must stay high (seconds)."""
        self._high = high
        self._low = low
        self._sustain = sustain
        self._high_since: float | None = None
        self.active = False

    def update(self, duty: int | None, now: float) -> bool:
        """Feed one reading taken at ``now`` (monotonic seconds); return whether the hint applies.

        An unknown reading (``None``) changes nothing.
        """
        if duty is None:
            return self.active
        if self.active:
            if duty < self._low:
                self.active = False
                self._high_since = None
        elif duty >= self._high:
            if self._high_since is None:
                self._high_since = now
            if now - self._high_since >= self._sustain:
                self.active = True
        else:
            self._high_since = None
        return self.active
