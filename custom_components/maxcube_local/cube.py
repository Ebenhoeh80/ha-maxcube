"""``MaxCube`` that also keeps the status values from the Cube's ``H:`` message.

The Cube starts every connection with an ``H:`` line: serial, RF address, firmware, an unknown
field, the HTTP connection id, the **duty cycle** (share of the radio time budget already used,
hex), the **number of free memory slots** (hex), then the date and time. The Cube may only send a
limited share of the time; at 100 % it stops sending radio commands for about an hour. The
``maxcube-api`` library reads only the first three fields, so they are picked up here.
"""

from __future__ import annotations

from maxcube.cube import MaxCube

_DUTY_CYCLE_FIELD = 5
_FREE_SLOTS_FIELD = 6


def _hex_field(tokens: list[str], index: int) -> int | None:
    """Return a hex field of the H message as an integer, or ``None`` if it is missing or bad."""
    try:
        return int(tokens[index], 16)
    except (IndexError, ValueError):
        return None


def parse_h_status(message: str) -> tuple[int | None, int | None]:
    """Return ``(duty_cycle_percent, free_memory_slots)`` from the argument of an H message."""
    tokens = message.strip().split(",")
    duty = _hex_field(tokens, _DUTY_CYCLE_FIELD)
    if duty is not None and not 0 <= duty <= 100:
        duty = None
    return duty, _hex_field(tokens, _FREE_SLOTS_FIELD)


class MaxCubeWithStatus(MaxCube):
    """A ``MaxCube`` that exposes ``duty_cycle`` and ``free_memory_slots``."""

    duty_cycle: int | None = None
    free_memory_slots: int | None = None

    def parse_h_message(self, message: str) -> None:
        """Parse the H message as the library does, and keep the Cube's status values."""
        super().parse_h_message(message)
        self.duty_cycle, self.free_memory_slots = parse_h_status(message)
