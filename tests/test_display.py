"""Tests for the display setting of a wall thermostat: the radio message (pure, and via the fake Cube).

Source of the layout: Bouni/max-cube-protocol, S-Message.md (command 82 "Enable/disable display of
current temperature", only wall thermostats, 04 = actual temperature, 00 = setpoint, the default), and
the official MAX! software 1.4.6 (``WallMountedThermostatDisplayConfigCommand``: header with frame type
0x82 in byte 2 and the RF address in bytes 6-8, the setting in byte 10 as 04 or 00).
"""

from __future__ import annotations

from fake_cube import FakeCube
from maxcube.device import MAX_THERMOSTAT, MAX_WALL_THERMOSTAT
from maxcube.thermostat import MaxThermostat
from maxcube.wallthermostat import MaxWallThermostat
from maxcube_local import cube as cube_module
from maxcube_local.display import encode_display_setting
from maxcube_local.linkstatus import LinkStatusMaxCube


class _FakeCommander:
    """Stands in for the library's connection handler and records the radio messages."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_radio_msg(self, hex_message: str) -> bool:
        self.sent.append(hex_message)
        return True


def test_showing_the_actual_temperature_sends_04_in_byte_10() -> None:
    assert encode_display_setting("0A1B2D", show_actual=True) == "0000820000000A1B2D0004"


def test_showing_the_setpoint_sends_00_in_byte_10() -> None:
    assert encode_display_setting("0A1B2D", show_actual=False) == "0000820000000A1B2D0000"


def test_the_message_is_eleven_bytes_and_the_address_is_upper_case() -> None:
    message = encode_display_setting("0a1b2d", show_actual=True)
    assert message == "0000820000000A1B2D0004"
    assert len(bytes.fromhex(message)) == 11


def _cube_with_devices(commander: _FakeCommander) -> cube_module.MaxCubeWithStatus:
    wall = MaxWallThermostat()
    wall.type = MAX_WALL_THERMOSTAT
    wall.rf_address = "0A1B2D"
    radiator = MaxThermostat()
    radiator.type = MAX_THERMOSTAT
    radiator.rf_address = "0A1B2C"
    cube = object.__new__(cube_module.MaxCubeWithStatus)
    cube.devices = [wall, radiator]
    cube._MaxCube__commander = commander
    return cube


def test_the_write_method_sends_the_telegram_through_the_connection() -> None:
    commander = _FakeCommander()
    cube = _cube_with_devices(commander)
    assert cube.write_display_setting("0A1B2D", show_actual=True) is True
    assert commander.sent == ["0000820000000A1B2D0004"]


def test_a_radiator_thermostat_or_an_unknown_address_gets_nothing() -> None:
    commander = _FakeCommander()
    cube = _cube_with_devices(commander)
    assert cube.write_display_setting("0A1B2C", show_actual=True) is False
    assert cube.write_display_setting("FFFFFF", show_actual=False) is False
    assert commander.sent == []


def test_the_telegram_reaches_the_fake_cube_as_radio_message() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device("0A1B2D", "Wall thermostat", kind="wall", room_id=1)
        linked = LinkStatusMaxCube(host="127.0.0.1", port=fake.port)
        linked.use_persistent_connection = False
        assert linked.write_display_setting("0A1B2D", show_actual=False) is True
        assert fake.radio_messages == ["0000820000000A1B2D0000"]
