"""Tests for decoding the weekly heating programme."""

from __future__ import annotations

import base64
from datetime import datetime

from maxcube.cube import get_programme
from maxcube.device import MAX_THERMOSTAT
from maxcube.thermostat import MaxThermostat
from maxcube_local import cube as cube_module
from maxcube_local import schedule


def _encode_day(slots: list[tuple[float, str]]) -> bytes:
    """Encode the setpoints (temperature, until HH:MM) of one day as the Cube does (26 bytes)."""
    block = b""
    for temp, until in slots:
        word = (int(temp * 2) << 9) | (schedule.parse_time(until) // 5)
        block += word.to_bytes(2, "big")
    return block.ljust(26, b"\x00")


# One typical day: night 17, morning 21, day 18, evening 21, night 17 again until midnight.
TYPICAL = [(17.0, "06:00"), (21.0, "08:00"), (18.0, "17:00"), (21.5, "22:00"), (17.0, "24:00")]


def _week(day_slots: dict[str, list[tuple[float, str]]]) -> bytes:
    """Encode a whole week, in the Cube's order (Saturday first)."""
    return b"".join(_encode_day(day_slots[day]) for day in schedule.CUBE_DAY_ORDER)


def test_the_week_starts_with_saturday_in_the_data_but_monday_in_the_result() -> None:
    week = {day: TYPICAL for day in schedule.WEEK_DAYS}
    week["saturday"] = [(19.0, "24:00")]
    decoded = schedule.parse_week_program(_week(week))
    assert list(decoded) == list(schedule.WEEK_DAYS)
    assert decoded["saturday"] == [{"until": "24:00", "temp": 19.0}]
    assert decoded["monday"][0] == {"until": "06:00", "temp": 17.0}


def test_half_degrees_are_kept_where_the_library_cuts_them() -> None:
    data = _week({day: TYPICAL for day in schedule.WEEK_DAYS})
    ours = schedule.parse_week_program(data)["monday"]
    theirs = get_programme(data)["monday"]
    assert {"until": "22:00", "temp": 21.5} in ours
    assert {"until": "22:00", "temp": 21} in theirs  # the library truncates 21.5 to 21


def test_whole_degrees_agree_with_the_library() -> None:
    whole = [(17.0, "06:00"), (21.0, "18:00"), (17.0, "24:00")]
    data = _week({day: whole for day in schedule.WEEK_DAYS})
    ours = schedule.parse_week_program(data)
    theirs = get_programme(data)
    for day in schedule.WEEK_DAYS:
        assert ours[day] == [{"until": s["until"], "temp": float(s["temp"])} for s in theirs[day]]


def test_unused_setpoints_after_the_end_of_the_day_are_ignored() -> None:
    data = _week({day: TYPICAL for day in schedule.WEEK_DAYS})
    assert len(schedule.parse_week_program(data)["tuesday"]) == len(TYPICAL)


def test_short_data_leaves_out_the_missing_days() -> None:
    data = _encode_day(TYPICAL) * 3  # Saturday, Sunday, Monday only
    decoded = schedule.parse_week_program(data)
    assert list(decoded) == ["monday", "saturday", "sunday"]


def test_the_scheduled_temperature_follows_the_clock() -> None:
    decoded = schedule.parse_week_program(_week({day: TYPICAL for day in schedule.WEEK_DAYS}))
    monday = datetime(2026, 11, 16)  # a Monday
    assert monday.weekday() == 0
    at = lambda hour, minute: schedule.scheduled_temperature(  # noqa: E731
        decoded, monday.replace(hour=hour, minute=minute)
    )
    assert at(0, 0) == 17.0
    assert at(5, 59) == 17.0
    assert at(6, 0) == 21.0  # a setpoint ends *at* its time
    assert at(12, 30) == 18.0
    assert at(21, 59) == 21.5
    assert at(23, 59) == 17.0


def test_no_programme_gives_no_temperature() -> None:
    assert schedule.scheduled_temperature({}, datetime(2026, 11, 16, 12)) is None


def test_a_c_message_sets_the_schedule_and_keeps_the_library_fields() -> None:
    thermostat = MaxThermostat()
    thermostat.type = MAX_THERMOSTAT
    thermostat.rf_address = "0A1B2C"
    cube = object.__new__(cube_module.MaxCubeWithStatus)
    cube.devices = [thermostat]
    settings = bytes(18) + bytes([41, 33, 61, 9]) + bytes(7)  # comfort 20.5, eco 16.5, max, min
    data = settings + _week({day: TYPICAL for day in schedule.WEEK_DAYS})
    assert len(settings) == schedule.PROGRAMME_OFFSET
    cube.parse_c_message("0A1B2C," + base64.b64encode(data).decode())

    assert thermostat.comfort_temperature == 20.5  # the library's own fields still work
    assert thermostat.schedule["monday"][0] == {"until": "06:00", "temp": 17.0}
    assert {"until": "22:00", "temp": 21.5} in thermostat.schedule["tuesday"]
