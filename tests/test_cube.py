"""Tests for the pure parts: H message status, mode writes and Cube discovery."""

from __future__ import annotations

from datetime import datetime

from maxcube.device import (
    MAX_DEVICE_MODE_AUTOMATIC,
    MAX_DEVICE_MODE_BOOST,
    MAX_WALL_THERMOSTAT,
)
from maxcube.wallthermostat import MaxWallThermostat
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


class FakeCommander:
    """Collects the telegrams instead of sending them."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.messages: list[str] = []

    def send_radio_msg(self, message: str) -> bool:
        self.messages.append(message)
        return self.ok


def _cube_with(commander: FakeCommander) -> cube.MaxCubeWithStatus:
    instance = object.__new__(cube.MaxCubeWithStatus)
    instance._MaxCube__commander = commander
    instance._now = lambda: datetime(2026, 11, 25, 7, 0)  # a Wednesday
    instance.devices = []
    return instance


def _wall_thermostat() -> MaxWallThermostat:
    device = MaxWallThermostat()
    device.type = MAX_WALL_THERMOSTAT
    device.rf_address = "097F2C"
    device.room_id = 3
    device.mode = MAX_DEVICE_MODE_AUTOMATIC
    device.target_temperature = 21.0
    return device


def test_a_wall_thermostat_can_switch_to_auto_without_the_library_crash() -> None:
    """The library's AUTO lookup only exists on radiator thermostats (upstream #45)."""
    commander = FakeCommander()
    instance = _cube_with(commander)
    device = _wall_thermostat()
    device.mode = 1
    device.schedule = {"wednesday": [{"until": "12:00", "temp": 17.0}, {"until": "24:00", "temp": 19.5}]}

    assert instance.set_mode(device, MAX_DEVICE_MODE_AUTOMATIC)

    # Byte-identical to the library's telegram: mode 0, no own setpoint.
    assert commander.messages == ["000440000000097F2C0300"]
    assert device.mode == MAX_DEVICE_MODE_AUTOMATIC
    assert device.target_temperature == 17.0


def test_a_wall_thermostat_uses_the_room_programme_when_it_has_none() -> None:
    commander = FakeCommander()
    instance = _cube_with(commander)
    device = _wall_thermostat()
    radiator = _wall_thermostat()
    radiator.schedule = {"wednesday": [{"until": "24:00", "temp": 20.5}]}
    instance.devices = [radiator]

    assert instance.set_mode(device, MAX_DEVICE_MODE_AUTOMATIC)
    assert device.target_temperature == 20.5


def test_other_modes_keep_the_target_temperature_on_the_wire() -> None:
    """BOOST/VACATION must stay byte-compatible with the library's set_mode."""
    commander = FakeCommander()
    instance = _cube_with(commander)
    device = _wall_thermostat()
    device.target_temperature = 21.5

    assert instance.set_mode(device, MAX_DEVICE_MODE_BOOST)

    value = int(21.5 * 2) + (MAX_DEVICE_MODE_BOOST << 6)
    assert commander.messages == [f"000440000000097F2C03{value:02X}"]
    assert device.mode == MAX_DEVICE_MODE_BOOST
    assert device.target_temperature == 21.5


def test_a_refused_mode_change_does_not_change_the_device() -> None:
    instance = _cube_with(FakeCommander(ok=False))
    device = _wall_thermostat()
    device.mode = 1

    assert not instance.set_mode(device, MAX_DEVICE_MODE_AUTOMATIC)
    assert device.mode == 1
    assert device.target_temperature == 21.0


def test_find_host_matches_the_serial() -> None:
    cubes = [
        {"host": "192.168.10.60", "serial": "KEQ0523864"},
        {"host": "192.168.10.61", "serial": "KEQ0999999"},
    ]
    assert discovery.find_host(cubes, "KEQ0999999") == "192.168.10.61"
    assert discovery.find_host(cubes, "KEQ0000000") is None
    assert discovery.find_host([], "KEQ0523864") is None
