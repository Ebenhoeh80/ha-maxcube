"""Weekly heating programme of a MAX! thermostat: decoding (pure functions, no Home Assistant).

The Cube sends a ``C:`` message per thermostat. After the settings (bytes 0-28 of the decoded data)
the weekly programme follows: seven blocks of 26 bytes, **starting with Saturday**. Each block holds
13 setpoints of two bytes: the upper 7 bits are the target temperature in half degrees, the lower
9 bits the time until which it applies, in steps of 5 minutes. The last setpoint of a day ends at
24:00, anything after it is unused.

The ``maxcube-api`` library decodes the same data but cuts half degrees (20.5 becomes 20), so the
programme is decoded here to keep the exact temperatures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Order of the days in the Cube's data: Saturday first.
CUBE_DAY_ORDER = ("saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday")
# Order for people (and for ``datetime.weekday()``): Monday first.
WEEK_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

PROGRAMME_OFFSET = 29  # where the weekly programme starts in the decoded C message of a thermostat
BLOCK_BYTES = 26
SLOTS_PER_DAY = 13
END_OF_DAY_MINUTES = 24 * 60

Schedule = dict[str, list[dict[str, Any]]]


def format_time(minutes: int) -> str:
    """Return minutes since midnight as ``HH:MM`` (``24:00`` is the end of the day)."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_time(text: str) -> int:
    """Return ``HH:MM`` as minutes since midnight."""
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def parse_week_program(data: bytes) -> Schedule:
    """Decode the weekly programme (the bytes after the thermostat settings).

    Returns ``{"monday": [{"until": "06:00", "temp": 17.0}, ...], ...}`` in the order Monday to
    Sunday. Days for which the data is too short are left out.
    """
    by_day: Schedule = {}
    for index, name in enumerate(CUBE_DAY_ORDER):
        block = data[index * BLOCK_BYTES : (index + 1) * BLOCK_BYTES]
        if len(block) < BLOCK_BYTES:
            continue
        slots: list[dict[str, Any]] = []
        for position in range(0, BLOCK_BYTES, 2):
            word = (block[position] << 8) | block[position + 1]
            minutes = (word & 0x1FF) * 5
            slots.append({"until": format_time(minutes), "temp": (word >> 9) / 2})
            if minutes >= END_OF_DAY_MINUTES:
                break
        by_day[name] = slots
    return {day: by_day[day] for day in WEEK_DAYS if day in by_day}


def scheduled_temperature(schedule: Schedule, moment: datetime) -> float | None:
    """Return the temperature the programme sets at ``moment``, or ``None`` without a programme."""
    slots = schedule.get(WEEK_DAYS[moment.weekday()])
    if not slots:
        return None
    now = moment.hour * 60 + moment.minute
    for slot in slots:
        if now < parse_time(slot["until"]):
            return float(slot["temp"])
    return None
