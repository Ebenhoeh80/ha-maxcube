"""Tests of the link status against the fake Cube (synthetic frames, no Home Assistant, no hardware)."""

from __future__ import annotations

import base64
import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fake_cube import (
    MODE_AUTO,
    MODE_BOOST,
    MODE_MANUAL,
    MODE_VACATION,
    FakeCube,
)
from maxcube.device import (
    MAX_DEVICE_BATTERY_LOW,
    MAX_DEVICE_BATTERY_OK,
    MAX_THERMOSTAT,
    MAX_WALL_THERMOSTAT,
    MAX_WINDOW_SHUTTER,
    MaxDevice,
)
from maxcube_local import schedule
from maxcube_local.linkstatus import LinkStatusMaxCube

try:
    import pytest_socket
except ImportError:  # the plain job has no socket guard; the Home Assistant job has one
    pytest_socket = None

STALE_AFTER = 90.0


@pytest.fixture(autouse=True)
def _allow_loopback_only() -> Iterator[None]:
    """Open loopback for the fake Cube where pytest-socket blocks sockets, then block again.

    The Home Assistant plugin (pytest-homeassistant-custom-component) blocks every socket per test.
    Only 127.0.0.1 is allowed here, and the block is restored afterwards. Without the plugin there
    is no guard and nothing to do.
    """
    if pytest_socket is None:
        yield
        return
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1"])
    yield
    pytest_socket.disable_socket(allow_unix_socket=True)


def connect(fake: FakeCube) -> LinkStatusMaxCube:
    """Connect the way the coordinator does: one short connection per poll (see ``_connect``)."""
    linked = LinkStatusMaxCube(host="127.0.0.1", port=fake.port)
    linked.use_persistent_connection = False
    linked.disconnect()
    return linked


def device_at(linked: LinkStatusMaxCube, rf_address: str) -> MaxDevice:
    device = linked.device_by_rf(rf_address)
    assert device is not None, rf_address
    return device


@pytest.fixture
def cube() -> Iterator[FakeCube]:
    """Two rooms and four devices: a thermostat, a window contact, a thermostat and a wall thermostat."""
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_room(2, "Bedroom")
        fake.add_device(
            "0A1B01",
            "Thermostat living",
            room_id=1,
            valve=30,
            setpoint=21.5,
            actual=20.5,
            mode=MODE_MANUAL,
        )
        fake.add_device("0A1B02", "Window bedroom", kind="window", room_id=2)
        fake.add_device("0A1B03", "Thermostat bedroom", room_id=2, setpoint=17.0, actual=18.0)
        fake.add_device(
            "0A1B04", "Wall thermostat", kind="wall", room_id=1, setpoint=19.0, actual=25.6
        )
        yield fake


def test_devices_and_rooms_are_read(cube: FakeCube) -> None:
    linked = connect(cube)
    assert [(d.rf_address, d.type, d.name, d.room_id) for d in linked.devices] == [
        ("0A1B01", MAX_THERMOSTAT, "Thermostat living", 1),
        ("0A1B02", MAX_WINDOW_SHUTTER, "Window bedroom", 2),
        ("0A1B03", MAX_THERMOSTAT, "Thermostat bedroom", 2),
        ("0A1B04", MAX_WALL_THERMOSTAT, "Wall thermostat", 1),
    ]
    assert [(r.id, r.name) for r in linked.rooms] == [(1, "Living room"), (2, "Bedroom")]
    assert [d.serial for d in linked.devices] == [
        "ZZZ0000010",
        "ZZZ0000011",
        "ZZZ0000012",
        "ZZZ0000013",
    ]


def test_serial_and_firmware_of_the_cube_are_read(cube: FakeCube) -> None:
    linked = connect(cube)
    assert linked.serial == "ZZZ0000001"
    assert linked.firmware_version == "01.13"
    assert linked.rf_address == "0A1B2C"


def test_duty_cycle_and_free_slots_come_from_the_h_line(cube: FakeCube) -> None:
    cube.set_duty_cycle(42, 7)
    linked = connect(cube)
    assert (linked.duty_cycle, linked.free_memory_slots) == (42, 7)


def test_the_battery_flag_is_read_and_cleared(cube: FakeCube) -> None:
    cube.set_battery("0A1B01", True)
    linked = connect(cube)
    assert device_at(linked, "0A1B01").battery == MAX_DEVICE_BATTERY_LOW
    assert device_at(linked, "0A1B03").battery == MAX_DEVICE_BATTERY_OK

    cube.set_battery("0A1B01", False)
    linked.update()
    assert device_at(linked, "0A1B01").battery == MAX_DEVICE_BATTERY_OK


def test_the_link_flags_are_read_per_device(cube: FakeCube) -> None:
    cube.set_flags("0A1B03", initialized=False, error=True, link_error=True)
    linked = connect(cube)

    # bits1 0x12 (bit 4 and initialized), bits2 0x01 (manual)
    living = linked.device_status("0A1B01", STALE_AFTER)
    assert (living.initialized, living.error, living.link_error) == (True, False, False)
    assert living.raw_flags == "1201"
    assert living.stale is False
    assert living.last_heard is not None

    # bits1 0x18 (bit 4, error), bits2 0x40 (link error, auto)
    bedroom = linked.device_status("0A1B03", STALE_AFTER)
    assert (bedroom.initialized, bedroom.error, bedroom.link_error) == (False, True, True)
    assert bedroom.raw_flags == "1840"


def test_a_device_not_in_any_frame_is_unknown_and_stale(cube: FakeCube) -> None:
    status = connect(cube).device_status("FFFFFF", STALE_AFTER)
    assert (status.initialized, status.error, status.link_error, status.raw_flags) == (None,) * 4
    assert status.stale is True


def test_a_window_contact_with_six_bytes_does_not_crash(cube: FakeCube) -> None:
    linked = connect(cube)
    window = device_at(linked, "0A1B02")
    assert window.is_windowshutter()
    assert "0A1B02" in linked.last_heard
    # The thermostat behind the contact is still read correctly.
    bedroom = device_at(linked, "0A1B03")
    assert bedroom.target_temperature == 17.0
    assert bedroom.actual_temperature == pytest.approx(18.0)


def test_a_short_dead_telegram_does_not_crash() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device("0A1B01", "Dead thermostat", short_telegram=True, valve=0, setpoint=20.0)
        fake.add_device("0A1B02", "Healthy thermostat", mode=MODE_MANUAL, valve=55, setpoint=21.0)
        linked = connect(fake)

    dead = linked.device_status("0A1B01", STALE_AFTER)
    assert dead.last_heard is not None
    assert (dead.initialized, dead.error, dead.link_error, dead.raw_flags) == (None,) * 4
    healthy = device_at(linked, "0A1B02")
    assert healthy.valve_position == 55
    assert healthy.target_temperature == 21.0


def test_thermostat_reads_actual_temperature_in_auto_and_manual(cube: FakeCube) -> None:
    cube.set_actual("0A1B01", 19.5)
    linked = connect(cube)
    assert device_at(linked, "0A1B01").actual_temperature == pytest.approx(19.5)

    cube.set_mode("0A1B01", MODE_AUTO)
    linked = connect(cube)
    assert device_at(linked, "0A1B01").actual_temperature == pytest.approx(19.5)


def test_wall_thermostat_reads_setpoint_and_actual_temperature_with_high_bit(
    cube: FakeCube,
) -> None:
    linked = connect(cube)
    wall = device_at(linked, "0A1B04")
    assert wall.is_wallthermostat()
    assert wall.target_temperature == 19.0
    assert wall.actual_temperature == pytest.approx(25.6)


def test_the_frame_carries_the_actual_temperature_in_boost(cube: FakeCube) -> None:
    """Sanity check of the fake itself: in boost mode the bytes of the frame hold the value."""
    cube.set_mode("0A1B01", MODE_BOOST)
    cube.set_actual("0A1B01", 21.0)
    l_line = cube.frames()[-1]
    data = base64.b64decode(l_line.removeprefix("L:"))
    assert data[0] == 11  # first entry: the living room thermostat
    assert (data[9] << 8) + data[10] == 210


@pytest.mark.xfail(
    strict=True, reason="library drops the actual temperature outside auto/manual mode"
)
@pytest.mark.parametrize("mode", [MODE_VACATION, MODE_BOOST])
def test_actual_temperature_is_read_in_boost_and_vacation(cube: FakeCube, mode: int) -> None:
    cube.set_mode("0A1B01", mode)
    cube.set_actual("0A1B01", 21.0)
    linked = connect(cube)
    assert device_at(linked, "0A1B01").actual_temperature == pytest.approx(21.0)


def test_several_polls_in_a_row_each_read_the_cube(cube: FakeCube) -> None:
    linked = connect(cube)
    for _ in range(3):
        linked.update()
        assert device_at(linked, "0A1B01").valve_position == 30
        assert device_at(linked, "0A1B01").target_temperature == 21.5


def test_a_change_between_two_polls_arrives(cube: FakeCube) -> None:
    linked = connect(cube)
    cube.set_valve("0A1B01", 75)
    cube.set_setpoint("0A1B01", 22.0)
    cube.set_battery("0A1B01", True)
    linked.update()
    living = device_at(linked, "0A1B01")
    assert (living.valve_position, living.target_temperature) == (75, 22.0)
    assert living.battery == MAX_DEVICE_BATTERY_LOW


def test_a_radio_command_is_sent_and_answered(cube: FakeCube) -> None:
    linked = connect(cube)
    assert linked.set_mode(device_at(linked, "0A1B01"), MODE_AUTO) is True
    # Set-temperature command: flags 0000 0440 0000, RF address, room 01, target 00 (auto).
    assert cube.radio_messages == ["000440000000" + "0A1B01" + "01" + "00"]


def test_the_programme_of_a_thermostat_is_read_from_the_c_line() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(
            "0A1B01",
            "Thermostat",
            schedule={"monday": [("06:30", 17.5), ("24:00", 20.5)]},
        )
        linked = connect(fake)
    programme = device_at(linked, "0A1B01").schedule
    assert programme["monday"] == [
        {"until": "06:30", "temp": 17.5},
        {"until": "24:00", "temp": 20.5},
    ]
    assert programme["sunday"] == [{"until": "24:00", "temp": 20.0}]


def test_the_fake_releases_its_port_and_thread_on_exit() -> None:
    with FakeCube() as fake:
        port = fake.port
        assert port > 0
    assert not any(thread.name == "fake-cube" for thread in threading.enumerate())
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


# --- round trip of the weekly programme (encoder in schedule.py, parser in schedule.py) -------------

PERIOD_CASES: list[Any] = [
    pytest.param([{"until": "24:00", "temperature": 21.0}], id="one-section"),
    pytest.param(
        [
            {"until": "06:30", "temperature": 17.5},
            {"until": "08:00", "temperature": 21.5},
            {"until": "11:45", "temperature": 18.0},
            {"until": "17:00", "temperature": 20.5},
            {"until": "21:55", "temperature": 22.0},
            {"until": "23:00", "temperature": 19.0},
            {"until": "24:00", "temperature": 16.5},
        ],
        id="seven-sections",
    ),
    pytest.param(
        [{"until": "06:30", "temperature": 17.5}, {"until": "24:00", "temperature": 20.5}],
        id="half-degrees",
    ),
    pytest.param([{"until": "24:00", "temperature": 4.5}], id="off-limit"),
]
DAYS = ["monday", "saturday", "sunday"]
HEADER_BYTES = 11  # command bytes, RF address, room and day, before the setpoints


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.parametrize("periods", PERIOD_CASES)
def test_a_day_survives_the_round_trip(periods: list[dict[str, Any]], day: str) -> None:
    slots = schedule.validate_periods(periods)
    raw = bytes.fromhex(schedule.encode_set_programme("0A1B01", 1, day, slots))
    assert len(raw) == HEADER_BYTES + 14  # always seven setpoints, however many are used
    assert raw[6:9] == bytes.fromhex("0A1B01")
    assert raw[9] == 1
    assert raw[10] == schedule.CUBE_DAY_ORDER.index(day)

    # The setpoints go into the day's block of the weekly programme, which the parser reads back.
    block = raw[HEADER_BYTES:].ljust(26, b"\x00")
    week = bytes(26 * schedule.CUBE_DAY_ORDER.index(day)) + block
    decoded = schedule.parse_week_program(week)[day]
    assert decoded == [{"until": s["until"], "temp": s["temp"]} for s in slots]


@pytest.mark.parametrize(
    "periods",
    [
        pytest.param([], id="no-periods"),
        pytest.param([{"until": "06:30", "temperature": 17.5}], id="does-not-end-at-midnight"),
        pytest.param([{"until": "24:00", "temperature": 17.25}], id="quarter-degree"),
    ],
)
def test_invalid_days_are_refused(periods: list[dict[str, Any]]) -> None:
    with pytest.raises(schedule.ScheduleError):
        schedule.validate_periods(periods)
