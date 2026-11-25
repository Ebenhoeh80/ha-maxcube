"""Tests for decoding the weekly heating programme."""

from __future__ import annotations

import base64
from datetime import datetime

import pytest
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
    week = dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)
    week["saturday"] = [(19.0, "24:00")]
    decoded = schedule.parse_week_program(_week(week))
    assert list(decoded) == list(schedule.WEEK_DAYS)
    assert decoded["saturday"] == [{"until": "24:00", "temp": 19.0}]
    assert decoded["monday"][0] == {"until": "06:00", "temp": 17.0}


def test_half_degrees_are_kept_where_the_library_cuts_them() -> None:
    data = _week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL))
    ours = schedule.parse_week_program(data)["monday"]
    theirs = get_programme(data)["monday"]
    assert {"until": "22:00", "temp": 21.5} in ours
    assert {"until": "22:00", "temp": 21} in theirs  # the library truncates 21.5 to 21


def test_whole_degrees_agree_with_the_library() -> None:
    whole = [(17.0, "06:00"), (21.0, "18:00"), (17.0, "24:00")]
    data = _week(dict.fromkeys(schedule.WEEK_DAYS, whole))
    ours = schedule.parse_week_program(data)
    theirs = get_programme(data)
    for day in schedule.WEEK_DAYS:
        assert ours[day] == [{"until": s["until"], "temp": float(s["temp"])} for s in theirs[day]]


def test_unused_setpoints_after_the_end_of_the_day_are_ignored() -> None:
    data = _week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL))
    assert len(schedule.parse_week_program(data)["tuesday"]) == len(TYPICAL)


def test_an_impossible_slot_is_not_turned_into_a_target_temperature() -> None:
    # 0xFFFF decodes to 42:35 and 63.5 °C, both impossible. Put it before a valid day and make
    # sure it is skipped instead of becoming an attribute or a target temperature.
    broken_day = (b"\xff\xff" + _encode_day(TYPICAL)[:10]).ljust(schedule.BLOCK_BYTES, b"\x00")
    week = bytearray(_week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)))
    monday = 2 * schedule.BLOCK_BYTES  # Saturday, Sunday, Monday
    week[monday : monday + schedule.BLOCK_BYTES] = broken_day
    decoded = schedule.parse_week_program(bytes(week))
    assert decoded["monday"] == [
        {"until": until, "temp": temp} for temp, until in TYPICAL
    ]
    # The damaged word must not leak into the "temperature scheduled now" attribute either.
    assert schedule.scheduled_temperature(decoded, datetime(2026, 11, 16, 7)) == 21.0


def test_an_impossible_temperature_alone_is_skipped() -> None:
    # A valid time (05:00) with 63.5 °C: only the temperature check rejects this word. The next
    # word is a valid 24:00, so the day must still end cleanly.
    impossible = ((127 << 9) | (300 // 5)).to_bytes(2, "big")
    broken_day = (impossible + _encode_day([(17.0, "24:00")])[:24]).ljust(
        schedule.BLOCK_BYTES, b"\x00"
    )
    week = bytearray(_week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)))
    monday = 2 * schedule.BLOCK_BYTES
    week[monday : monday + schedule.BLOCK_BYTES] = broken_day
    decoded = schedule.parse_week_program(bytes(week))
    assert decoded["monday"] == [{"until": "24:00", "temp": 17.0}]


@pytest.mark.parametrize(
    "word",
    [
        (0 << 9) | (300 // 5),  # 05:00, 0 °C: below "off"
        (18 << 9) | (1500 // 5),  # 25:00, 18 °C: past the end of the day
    ],
)
def test_an_invalid_time_or_temperature_word_is_skipped(word: int) -> None:
    broken_day = (word.to_bytes(2, "big") + _encode_day([(17.0, "24:00")])[:24]).ljust(
        schedule.BLOCK_BYTES, b"\x00"
    )
    week = bytearray(_week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)))
    week[2 * schedule.BLOCK_BYTES : 3 * schedule.BLOCK_BYTES] = broken_day
    assert schedule.parse_week_program(bytes(week))["monday"] == [
        {"until": "24:00", "temp": 17.0}
    ]


def test_a_damaged_last_slot_makes_the_programme_unwritable() -> None:
    # 24:00 with an impossible temperature. The slot is skipped, so the day has no end at midnight
    # and copying it must be refused instead of writing a shortened programme.
    impossible = ((127 << 9) | (1440 // 5)).to_bytes(2, "big")
    broken_day = (_encode_day(TYPICAL)[:8] + impossible).ljust(schedule.BLOCK_BYTES, b"\x00")
    week = bytearray(_week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)))
    monday = 2 * schedule.BLOCK_BYTES
    week[monday : monday + schedule.BLOCK_BYTES] = broken_day
    decoded = schedule.parse_week_program(bytes(week))
    assert decoded["monday"][-1] == {"until": "22:00", "temp": 21.5}
    with pytest.raises(schedule.ScheduleError, match="must_end_at_midnight"):
        schedule.source_programme(decoded, ["monday"])


def test_short_data_leaves_out_the_missing_days() -> None:
    data = _encode_day(TYPICAL) * 3  # Saturday, Sunday, Monday only
    decoded = schedule.parse_week_program(data)
    assert list(decoded) == ["monday", "saturday", "sunday"]


def test_the_scheduled_temperature_follows_the_clock() -> None:
    decoded = schedule.parse_week_program(_week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL)))
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
    data = settings + _week(dict.fromkeys(schedule.WEEK_DAYS, TYPICAL))
    assert len(settings) == schedule.PROGRAMME_OFFSET
    cube.parse_c_message("0A1B2C," + base64.b64encode(data).decode())

    assert thermostat.comfort_temperature == 20.5  # the library's own fields still work
    assert thermostat.schedule["monday"][0] == {"until": "06:00", "temp": 17.0}
    assert {"until": "22:00", "temp": 21.5} in thermostat.schedule["tuesday"]


# --- Writing: validating the request ----------------------------------------------------------


def _period(until: str, temperature: float) -> dict:
    return {"until": until, "temperature": temperature}


def test_a_valid_day_is_normalised() -> None:
    result = schedule.validate_periods(
        [_period("6:00", 17), _period("08:30", 21.5), _period("24:00", "17.0")]
    )
    assert result == [
        {"until": "06:00", "temp": 17.0},
        {"until": "08:30", "temp": 21.5},
        {"until": "24:00", "temp": 17.0},
    ]


def _error(periods: list[dict]) -> str:
    try:
        schedule.validate_periods(periods)
    except schedule.ScheduleError as err:
        return err.key
    return ""


def test_the_last_period_must_end_at_midnight() -> None:
    assert _error([_period("06:00", 17), _period("23:00", 20)]) == "must_end_at_midnight"


def test_times_must_rise_and_use_five_minute_steps() -> None:
    assert _error([_period("08:00", 17), _period("07:00", 20), _period("24:00", 17)]) == (
        "times_not_rising"
    )
    assert _error([_period("08:00", 17), _period("08:00", 20), _period("24:00", 17)]) == (
        "times_not_rising"
    )
    assert _error([_period("06:03", 17), _period("24:00", 17)]) == "time_not_in_steps"


def test_bad_times_are_named() -> None:
    assert _error([_period("soon", 17), _period("24:00", 17)]) == "bad_time"
    assert _error([_period("25:00", 17)]) == "bad_time"
    assert _error([_period("00:00", 17), _period("24:00", 17)]) == "bad_time"
    assert _error([_period("6", 17), _period("24:00", 17)]) == "bad_time"


def test_temperatures_must_be_half_degrees_in_range() -> None:
    assert _error([_period("24:00", 21.3)]) == "bad_temperature"
    assert _error([_period("24:00", 4.0)]) == "bad_temperature"
    assert _error([_period("24:00", 31.0)]) == "bad_temperature"
    assert _error([_period("24:00", 4.5)]) == ""  # "off"
    assert _error([_period("24:00", 30.5)]) == ""  # "on"


def test_at_most_seven_periods_and_at_least_one() -> None:
    many = [_period(f"{h:02d}:00", 17) for h in range(1, 9)] + [_period("24:00", 17)]
    assert _error(many) == "too_many_periods"
    assert _error([]) == "no_periods"
    seven = [_period(f"{h:02d}:00", 17) for h in range(1, 7)] + [_period("24:00", 17)]
    assert _error(seven) == ""


def test_what_is_written_reads_back_the_same() -> None:
    periods = [_period("06:00", 17), _period("08:05", 21.5), _period("24:00", 17)]
    validated = schedule.validate_periods(periods)
    data = _encode_day([(p["temp"], p["until"]) for p in validated])
    decoded = schedule.parse_week_program(data * 7)
    assert decoded["monday"] == validated


# --- Writing: the radio message ---------------------------------------------------------------


class _FakeCommander:
    """Stands in for the library's connection handler and records the radio messages."""

    def __init__(self, accept: bool = True) -> None:
        self.sent: list[str] = []
        self.accept = accept

    def send_radio_msg(self, hex_message: str) -> bool:
        self.sent.append(hex_message)
        return self.accept


def _cube_with_thermostat(commander: _FakeCommander):
    thermostat = MaxThermostat()
    thermostat.type = MAX_THERMOSTAT
    thermostat.rf_address = "0A1B2C"
    thermostat.room_id = 1
    thermostat.programme = {day: [] for day in schedule.WEEK_DAYS}
    cube = object.__new__(cube_module.MaxCubeWithStatus)
    cube.devices = [thermostat]
    cube._MaxCube__commander = commander
    return cube, thermostat


SEVEN = [
    {"until": "06:00", "temp": 17.0},
    {"until": "08:00", "temp": 21.0},
    {"until": "12:00", "temp": 19.0},
    {"until": "14:00", "temp": 20.0},
    {"until": "17:00", "temp": 18.0},
    {"until": "22:00", "temp": 21.0},
    {"until": "24:00", "temp": 17.0},
]


def test_the_message_is_the_one_the_library_builds_for_a_full_day() -> None:
    library = _FakeCommander()
    cube, thermostat = _cube_with_thermostat(library)
    thermostat.programme["monday"] = []  # differs from SEVEN, so the library sends it
    cube.set_programme(thermostat, "monday", SEVEN)
    ours = schedule.encode_set_programme("0A1B2C", 1, "monday", SEVEN)
    # The library sends the message base64-encoded after hex-decoding; compare via a second fake.
    assert len(library.sent) == 1
    assert ours == library.sent[0]


def test_the_message_has_a_fixed_length_with_seven_setpoints() -> None:
    short = [{"until": "07:00", "temp": 16.5}, {"until": "24:00", "temp": 21.0}]
    message = schedule.encode_set_programme("0A1B2C", 3, "saturday", short)
    # 00 00 10 000000 | 0A1B2C 03 00 | 7 x 2 bytes
    assert len(message) == 2 * (1 + 1 + 1 + 3 + 3 + 1 + 1 + 14)
    assert message.startswith("0000100000000A1B2C0300")
    # The two real setpoints, then the last one repeated until 24:00 to fill the message.
    words = [message[22 + 4 * i : 26 + 4 * i] for i in range(7)]
    assert words[0] == f"{(33 << 9) | (7 * 12):04X}"
    assert words[1:] == [f"{(42 << 9) | (24 * 12):04X}"] * 6


def test_a_written_programme_reads_back_the_same() -> None:
    short = [{"until": "07:00", "temp": 16.5}, {"until": "24:00", "temp": 21.0}]
    message = schedule.encode_set_programme("0A1B2C", 1, "sunday", short)
    payload = bytes.fromhex(message)[11:]  # the setpoints after the header
    decoded = schedule.parse_week_program(b"\x00" * 26 + payload + b"\x00" * 26 * 5)
    assert decoded["sunday"] == short


def test_write_day_schedule_sends_the_message_and_reports_the_answer() -> None:
    commander = _FakeCommander(accept=True)
    cube, thermostat = _cube_with_thermostat(commander)
    assert cube.write_day_schedule(thermostat, "friday", SEVEN) is True
    assert commander.sent == [schedule.encode_set_programme("0A1B2C", 1, "friday", SEVEN)]
    refusing = _FakeCommander(accept=False)
    cube, thermostat = _cube_with_thermostat(refusing)
    assert cube.write_day_schedule(thermostat, "friday", SEVEN) is False


def test_the_library_pads_a_short_day_with_one_byte_so_its_message_is_too_short() -> None:
    # This is why the message is built here instead of with the library's set_programme.
    library = _FakeCommander()
    cube, thermostat = _cube_with_thermostat(library)
    short = [{"until": "07:00", "temp": 16.5}, {"until": "24:00", "temp": 21.0}]
    cube.set_programme(thermostat, "monday", short)
    ours = schedule.encode_set_programme("0A1B2C", 1, "monday", short)
    assert len(library.sent[0]) < len(ours)


def test_only_plain_hh_mm_times_are_taken() -> None:
    fullwidth = chr(0xFF10) + chr(0xFF17) + ":00"
    arabic = chr(0x660) + chr(0x667) + ":00"
    odd_times = ["+7:00", "-1:05", "07:0", "007:00", "07:000", "07 :00", fullwidth, arabic, "07.00", ""]
    for odd in odd_times:
        assert _error([_period(odd, 17), _period("24:00", 17)]) == "bad_time", repr(odd)
    assert _error([_period(" 7:05" + chr(10), 17), _period("24:00", 17)]) == ""  # surrounding blanks are cut off


def test_temperatures_that_are_not_numbers_are_refused() -> None:
    for odd in (float("nan"), float("inf"), float("-inf"), "abc", None, [21.0]):
        assert _error([_period("24:00", odd)]) == "bad_temperature", odd


# --- Writing several days, and copying a programme ------------------------------------------


def _key(call, *args) -> str:  # noqa: ANN001
    """Return the error key the call raises, or "" if it does not raise."""
    try:
        call(*args)
    except schedule.ScheduleError as err:
        return err.key
    return ""


def test_one_list_of_periods_is_written_to_every_day_given_once() -> None:
    periods = [_period("06:00", 17), _period("24:00", 21)]
    planned = schedule.plan_request(["friday", "monday", "friday"], periods, None)
    assert list(planned) == ["friday", "monday"]
    expected = [{"until": "06:00", "temp": 17.0}, {"until": "24:00", "temp": 21.0}]
    assert planned == {"friday": expected, "monday": expected}


def test_by_day_gives_each_day_its_own_periods() -> None:
    by_day = {
        "monday": [_period("24:00", 17)],
        "saturday": [_period("08:00", 19), _period("24:00", 21)],
    }
    assert schedule.plan_request(None, None, by_day) == {
        "monday": [{"until": "24:00", "temp": 17.0}],
        "saturday": [{"until": "08:00", "temp": 19.0}, {"until": "24:00", "temp": 21.0}],
    }


def test_days_and_by_day_are_not_mixed() -> None:
    by_day = {"monday": [_period("24:00", 17)]}
    assert _key(schedule.plan_request, ["monday"], None, by_day) == "mixed_request"
    assert _key(schedule.plan_request, None, [_period("24:00", 17)], by_day) == "mixed_request"


def test_a_request_needs_days_or_by_day() -> None:
    periods = [_period("24:00", 17)]
    assert _key(schedule.plan_request, None, periods, None) == "no_days"
    assert _key(schedule.plan_request, [], periods, None) == "no_days"
    assert _key(schedule.plan_request, None, None, {}) == "no_days"


def test_days_need_periods() -> None:
    assert _key(schedule.plan_request, ["monday"], None, None) == "no_periods"
    assert _key(schedule.plan_request, ["monday"], [], None) == "no_periods"


def test_every_day_of_by_day_is_checked() -> None:
    by_day = {"monday": [_period("24:00", 17)], "sunday": [_period("23:00", 17)]}
    assert _key(schedule.plan_request, None, None, by_day) == "must_end_at_midnight"


def test_a_source_day_is_returned_as_writable_periods() -> None:
    source = {
        "monday": [{"until": "06:00", "temp": 17.0}, {"until": "24:00", "temp": 21.0}],
        "tuesday": [{"until": "24:00", "temp": 19.0}],
    }
    assert schedule.source_programme(source, ["tuesday", "monday"]) == {
        "tuesday": [{"until": "24:00", "temp": 19.0}],
        "monday": [{"until": "06:00", "temp": 17.0}, {"until": "24:00", "temp": 21.0}],
    }


def test_a_source_without_the_requested_day_is_refused() -> None:
    source = {"monday": [{"until": "24:00", "temp": 17.0}]}
    assert _key(schedule.source_programme, {}, ["monday"]) == "no_source_programme"
    assert _key(schedule.source_programme, source, ["monday", "friday"]) == "no_source_programme"


def test_a_source_day_with_more_periods_than_one_write_holds_is_refused() -> None:
    source = {"monday": [{"until": f"{hour:02d}:00", "temp": 17.0} for hour in range(1, 14)]}
    assert _key(schedule.source_programme, source, ["monday"]) == "too_many_periods"


def test_only_the_days_that_differ_from_the_target_are_sent() -> None:
    wanted = {"monday": [{"until": "24:00", "temp": 17.0}], "tuesday": [{"until": "24:00", "temp": 19.0}]}
    stored = {"monday": [{"until": "24:00", "temp": 21.0}], "tuesday": [{"until": "24:00", "temp": 19.0}]}
    assert schedule.changed_days(wanted, stored) == {"monday": wanted["monday"]}
    assert schedule.changed_days(wanted, {}) == wanted
    assert schedule.changed_days(wanted, dict(wanted)) == {}


def test_each_radio_telegram_counts_2_8_percent_of_the_radio_time() -> None:
    assert schedule.RADIO_PERCENT_PER_TELEGRAM == 2.8
    schedule.check_radio_budget(0, 6)  # 16.8 %
    schedule.check_radio_budget(70, 7)  # 89.6 %, below the limit of 90 %
    assert _key(schedule.check_radio_budget, 70, 8) == "radio_too_busy"  # 92.4 %
    assert _key(schedule.check_radio_budget, 89, 1) == "radio_too_busy"  # 91.8 %


def test_an_unknown_duty_cycle_counts_as_zero_and_no_telegram_is_never_refused() -> None:
    schedule.check_radio_budget(None, 10)  # 28 %
    assert _key(schedule.check_radio_budget, None, 40) == "radio_too_busy"  # 112 %
    schedule.check_radio_budget(99, 0)
