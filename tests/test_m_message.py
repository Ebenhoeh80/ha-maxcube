"""Tests of the M message (rooms and devices) when the Cube sends it empty or unreadable.

Some Cubes send ``M:`` with no argument on every connection. The library then reads no rooms and no
devices, so after a restart Home Assistant would have no entities. The integration remembers the
last readable M message and uses it in that case (synthetic addresses and names, no hardware).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fake_cube import MODE_MANUAL, FakeCube, FakeDevice, FakeRoom, build_m_line
from maxcube_local.cube import MaxCubeWithStatus
from maxcube_local.linkstatus import LinkStatusMaxCube

try:
    import pytest_socket
except ImportError:  # the plain job has no socket guard; the Home Assistant job has one
    pytest_socket = None

WARNING_TEXT = "Error processing response message"
ROOMS = [FakeRoom(1, "Living room")]
DEVICES = [
    FakeDevice("0A1B01", "Thermostat living", "ZZZ0000010", 1, "thermostat"),
    FakeDevice("0A1B02", "Window bedroom", "ZZZ0000011", 1, "window"),
]


@pytest.fixture(autouse=True)
def _allow_loopback_only() -> Iterator[None]:
    """Open loopback for the fake Cube where pytest-socket blocks sockets, then block again."""
    if pytest_socket is None:
        yield
        return
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1"])
    yield
    pytest_socket.disable_socket(allow_unix_socket=True)


def m_argument(devices: list[FakeDevice], rooms: list[FakeRoom]) -> str:
    """The argument of a full M message (what follows ``M:``)."""
    return build_m_line(devices, rooms)[len("M:") :]


def bare_cube() -> MaxCubeWithStatus:
    """A cube object without a connection, for feeding the M parser directly."""
    cube = object.__new__(MaxCubeWithStatus)
    cube.rooms = []
    cube.devices = []
    return cube


def names(cube: MaxCubeWithStatus) -> dict[str, str]:
    return {device.rf_address: device.name for device in cube.devices}


def test_empty_m_without_memory_gives_no_devices_and_no_library_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device("0A1B01", "Thermostat living", room_id=1)
        fake.set_empty_m(True)
        linked = LinkStatusMaxCube(host="127.0.0.1", port=fake.port)
        linked.disconnect()
    assert linked.devices == []
    assert linked.m_message_missing is True
    assert WARNING_TEXT not in caplog.text


def test_empty_m_uses_the_remembered_message_after_a_fresh_connection() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device("0A1B01", "Thermostat living", room_id=1)
        first = LinkStatusMaxCube(host="127.0.0.1", port=fake.port)
        first.disconnect()
        remembered = first.last_m_message
        assert remembered
        fake.set_empty_m(True)
        # A new object, as after a restart of Home Assistant: only the saved message is known.
        second = LinkStatusMaxCube(host="127.0.0.1", port=fake.port, last_m_message=remembered)
        second.disconnect()
    assert names(second) == {"0A1B01": "Thermostat living"}
    assert second.rooms and second.rooms[0].name == "Living room"
    assert second.m_message_missing is True


def test_a_valid_m_replaces_the_remembered_one() -> None:
    old_remembered = m_argument(DEVICES, ROOMS).split(",")[2]  # the saved form: Base64 only
    renamed = [FakeDevice("0A1B01", "Kitchen", "ZZZ0000010", 1, "thermostat")]
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device("0A1B01", "Kitchen", room_id=1)
        linked = LinkStatusMaxCube(host="127.0.0.1", port=fake.port, last_m_message=old_remembered)
        linked.disconnect()
    assert names(linked) == {"0A1B01": "Kitchen"}
    assert linked.m_message_missing is False
    assert linked.last_m_message != old_remembered
    assert linked.last_m_message == m_argument(renamed, ROOMS).split(",")[2]


def test_an_unreadable_m_with_memory_uses_the_memory() -> None:
    cube = bare_cube()
    cube.parse_m_message(m_argument(DEVICES, ROOMS))
    cube.parse_m_message("00,01,!!!not base64!!!")
    assert names(cube) == {"0A1B01": "Thermostat living", "0A1B02": "Window bedroom"}
    assert cube.m_message_missing is True


@pytest.mark.parametrize("message", ["", "00,01", "00,01,"])
def test_an_empty_or_short_m_without_memory_does_nothing(message: str) -> None:
    cube = bare_cube()
    cube.parse_m_message(message)
    assert cube.devices == []
    assert cube.rooms == []
    assert cube.m_message_missing is True


def test_a_valid_m_without_memory_is_read_and_remembered() -> None:
    cube = bare_cube()
    cube.parse_m_message(m_argument(DEVICES, ROOMS))
    assert names(cube) == {"0A1B01": "Thermostat living", "0A1B02": "Window bedroom"}
    assert cube.m_message_missing is False
    assert cube.last_m_message == m_argument(DEVICES, ROOMS).split(",")[2]


def test_a_valid_m_read_twice_does_not_duplicate_devices_or_rooms() -> None:
    cube = bare_cube()
    message = m_argument(DEVICES, ROOMS)
    cube.parse_m_message(message)
    first_devices = list(cube.devices)
    cube.parse_m_message(message)
    assert cube.devices == first_devices
    assert len(cube.rooms) == 1


def test_remembered_m_keeps_the_values_already_read() -> None:
    cube = bare_cube()
    cube.parse_m_message(m_argument(DEVICES, ROOMS))
    thermostat = cube.device_by_rf("0A1B01")
    thermostat.target_temperature = 21.5
    thermostat.mode = MODE_MANUAL
    cube.parse_m_message("")
    assert cube.device_by_rf("0A1B01") is thermostat
    assert thermostat.target_temperature == 21.5
    assert thermostat.mode == MODE_MANUAL


def test_the_missing_flag_follows_each_poll() -> None:
    cube = bare_cube()
    cube.parse_m_message(m_argument(DEVICES, ROOMS))
    flags = []
    for message in ["", "", "", m_argument(DEVICES, ROOMS), ""]:
        cube.parse_m_message(message)
        flags.append(cube.m_message_missing)
    assert flags == [True, True, True, False, True]
    assert names(cube) == {"0A1B01": "Thermostat living", "0A1B02": "Window bedroom"}
