"""Tests for the pure parts: the H message status values and finding the Cube by its serial."""

from __future__ import annotations

from maxcube_local import cube, discovery

# serial, rf address, firmware, unknown, http id, duty cycle (hex), free slots (hex), date, time ...
H_MESSAGE = "KEQ0523864,097f2c,0113,00000000,477719c0,32,0f,0d0c09,0900,03,0000,04"


def test_status_values_are_read_from_the_h_message() -> None:
    assert cube.parse_h_status(H_MESSAGE) == (50, 15)


def test_zero_duty_cycle_is_a_value_not_a_missing_one() -> None:
    message = "KEQ0523864,097f2c,0113,00000000,477719c0,00,32,0d0c09,0900,03,0000,04"
    assert cube.parse_h_status(message) == (0, 50)


def test_a_duty_cycle_above_100_percent_is_rejected() -> None:
    message = "KEQ0523864,097f2c,0113,00000000,477719c0,ff,32,0d0c09,0900,03,0000,04"
    assert cube.parse_h_status(message) == (None, 50)


def test_short_or_garbled_messages_give_no_values() -> None:
    assert cube.parse_h_status("KEQ0523864,097f2c,0113") == (None, None)
    assert cube.parse_h_status("a,b,c,d,e,zz,yy") == (None, None)
    assert cube.parse_h_status("") == (None, None)


def test_the_library_fields_are_still_parsed() -> None:
    parsed = object.__new__(cube.MaxCubeWithStatus)
    parsed.parse_h_message(H_MESSAGE)
    assert parsed.serial == "KEQ0523864"
    assert parsed.firmware_version == "01.13"
    assert (parsed.duty_cycle, parsed.free_memory_slots) == (50, 15)


def test_the_status_defaults_to_none_before_any_message() -> None:
    parsed = object.__new__(cube.MaxCubeWithStatus)
    assert parsed.duty_cycle is None
    assert parsed.free_memory_slots is None


def test_find_host_matches_the_serial() -> None:
    cubes = [
        {"host": "192.168.10.60", "serial": "KEQ0523864"},
        {"host": "192.168.10.61", "serial": "KEQ0999999"},
    ]
    assert discovery.find_host(cubes, "KEQ0999999") == "192.168.10.61"
    assert discovery.find_host(cubes, "KEQ0000000") is None
    assert discovery.find_host([], "KEQ0523864") is None
