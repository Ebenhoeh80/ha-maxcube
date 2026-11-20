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

import re
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
# A time as the service takes it: one or two digits for the hour, two for the minutes, ASCII only
# (``int()`` would also accept signs, spaces and non-ASCII digits).
_TIME_FORMAT = re.compile(r"[0-9]{1,2}:[0-9]{2}")

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


# --- Writing: validating what the user asks for ---------------------------------------------

# One radio telegram holds at most seven setpoints for a day (the Cube stores up to 13 when it
# reads them back, but it accepts no more than seven per write).
MAX_SETPOINTS_WRITTEN = 7
MIN_TEMPERATURE = 4.5  # "off"
MAX_TEMPERATURE = 30.5  # "on"
TIME_STEP_MINUTES = 5


def encode_set_programme(rf_address: str, room_id: int, day: str, slots: list[dict[str, Any]]) -> str:
    """Return the radio message (hex) that sets one day's programme on one thermostat.

    Layout: ``00`` (unknown), ``00`` (addressed to a device, not a room), ``10`` (set week programme),
    the null address, the thermostat's RF address (3 bytes), its room id, the day (Saturday = 0) and
    exactly seven setpoints of two bytes each. A day with fewer setpoints is filled up with copies of
    its last one (which ends at 24:00), so the message always has its full length.

    ``slots`` must come from ``validate_periods`` (rising times, the last one ``24:00``).
    """
    padded = list(slots) + [slots[-1]] * (MAX_SETPOINTS_WRITTEN - len(slots))
    words = "".join(
        f"{(int(slot['temp'] * 2) << 9) | (parse_time(slot['until']) // TIME_STEP_MINUTES):04X}"
        for slot in padded
    )
    return (
        "00" "00" "10" "000000"
        + rf_address.upper()
        + f"{room_id:02X}"
        + f"{CUBE_DAY_ORDER.index(day):02X}"
        + words
    )


class ScheduleError(ValueError):
    """The requested programme is not valid. ``key`` names the problem, ``detail`` adds facts."""

    def __init__(self, key: str, detail: str = "") -> None:
        """Remember what is wrong."""
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key
        self.detail = detail


def _minutes_of(until: str) -> int:
    """Return the minutes since midnight of an ``H:MM``/``HH:MM`` time, or raise ``bad_time``."""
    if not _TIME_FORMAT.fullmatch(until):
        raise ScheduleError("bad_time", until)
    minutes = parse_time(until)
    if not 0 < minutes <= END_OF_DAY_MINUTES:
        raise ScheduleError("bad_time", until)
    return minutes


def _checked_temperature(value: float | str) -> float:
    """Return the temperature if it is a half degree within the range the thermostat accepts."""
    temp = float(value)
    if not MIN_TEMPERATURE <= temp <= MAX_TEMPERATURE or (temp * 2) % 1:
        raise ScheduleError("bad_temperature", str(temp))
    return temp


def validate_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check the setpoints of one day and return them as ``[{"until": "HH:MM", "temp": 21.0}]``.

    Each period gives the temperature that applies until the given time. The times must rise, be
    multiples of five minutes, and the last one must be ``24:00`` (so every minute of the day has
    a temperature). There may be at most seven periods, and the temperatures must be in half
    degrees between 4.5 and 30.5.
    """
    if not periods:
        raise ScheduleError("no_periods")
    if len(periods) > MAX_SETPOINTS_WRITTEN:
        raise ScheduleError("too_many_periods", str(MAX_SETPOINTS_WRITTEN))
    result: list[dict[str, Any]] = []
    previous = 0
    for period in periods:
        until = str(period["until"]).strip()
        minutes = _minutes_of(until)
        if minutes % TIME_STEP_MINUTES:
            raise ScheduleError("time_not_in_steps", until)
        if minutes <= previous:
            raise ScheduleError("times_not_rising", until)
        temp = _checked_temperature(period["temperature"])
        result.append({"until": format_time(minutes), "temp": temp})
        previous = minutes
    if previous != END_OF_DAY_MINUTES:
        raise ScheduleError("must_end_at_midnight")
    return result
