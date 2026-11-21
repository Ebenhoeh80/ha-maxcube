"""Which devices need attention (pure logic, no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

ISSUE_BATTERY = "battery_low"
ISSUE_ERROR = "device_error"
ISSUE_UNREACHABLE = "cube_unreachable"
ISSUE_RADIO_BUSY = "radio_busy"

# The Cube reports the low-battery flag unevenly (it came and went within minutes for hours on a real
# thermostat, most likely with the load of the valve motor), so a report is held this long after the
# Cube has stopped sending it. Blips of up to five minutes were measured.
BATTERY_HOLD = 15 * 60  # seconds

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
    devices: Iterable[Any],
    status_of: Callable[[str], Any],
    battery_low: Callable[[str], bool] | None = None,
) -> list[DeviceFinding]:
    """Return the findings for all devices.

    ``status_of(rf_address)`` returns an object with an ``error`` attribute (``True``, ``False`` or
    ``None`` while unknown). A low battery is taken from ``battery_low(rf_address)`` (see
    :class:`BatteryHold`), or from the device itself if that is not given.
    """
    findings: list[DeviceFinding] = []
    for device in devices:
        name = device.name or device.rf_address
        low = (
            battery_low(device.rf_address)
            if battery_low is not None
            else bool(getattr(device, "battery", 0))
        )
        if low:
            findings.append(DeviceFinding(ISSUE_BATTERY, device.rf_address, name))
        if status_of(device.rf_address).error:
            findings.append(DeviceFinding(ISSUE_ERROR, device.rf_address, name))
    return findings


class BatteryHold:
    """Keeps a low-battery report for a while after the Cube stops sending it.

    It turns on at once and turns off only when the flag has been clear for ``hold`` seconds, so a
    flag that comes and goes does not make the sensor, the repair hint and automations flap (an
    automation that waits for "on for 30 minutes" would otherwise never fire).
    """

    def __init__(self, hold: float = BATTERY_HOLD) -> None:
        """Set how long (seconds) a report is kept after the last time it was seen."""
        self._hold = hold
        self._last_low: dict[str, float] = {}

    def update(self, rf_address: str, low: bool, now: float) -> bool:
        """Feed one reading taken at ``now`` (seconds); return whether the battery counts as low."""
        if low:
            self._last_low[rf_address] = now
            return True
        last = self._last_low.get(rf_address)
        if last is None:
            return False
        if now - last < self._hold:
            return True
        del self._last_low[rf_address]
        return False


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
