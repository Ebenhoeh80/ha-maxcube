"""Tests of the poll snapshot against the fake Cube (synthetic frames, no Home Assistant, no hardware)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from fake_cube import MODE_BOOST, FakeCube
from maxcube_local.linkstatus import LinkStatusMaxCube
from maxcube_local.snapshot import CubeSnapshot, schedule_as_dict, take_snapshot

try:
    import pytest_socket
except ImportError:  # the plain job has no socket guard; the Home Assistant job has one
    pytest_socket = None

RADIATOR = "0A1B2C"
WINDOW = "0A1B2E"
STALE_AFTER = 90.0


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


def connect(fake: FakeCube) -> LinkStatusMaxCube:
    """Connect the way the coordinator does: one short connection per poll."""
    linked = LinkStatusMaxCube(host="127.0.0.1", port=fake.port)
    linked.use_persistent_connection = False
    linked.disconnect()
    return linked


def snapshot_of(
    cube: LinkStatusMaxCube, battery_low: dict[str, bool] | None = None
) -> CubeSnapshot:
    return take_snapshot(cube, STALE_AFTER, battery_low or {})


def test_the_snapshot_keeps_its_values_when_the_library_object_changes() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(RADIATOR, "Radiator", setpoint=20.0, actual=19.5, valve=10)
        cube = connect(fake)
        before = snapshot_of(cube)

        # what the next poll does to the library objects, in place
        device = cube.device_by_rf(RADIATOR)
        device.target_temperature = 25.0
        device.mode = MODE_BOOST
        device.valve_position = 99
        device.actual_temperature = 30.0
        device.schedule["monday"].append({"until": "24:00", "temp": 5.0})

    state = before.device(RADIATOR)
    assert state.target_temperature == 20.0
    assert state.mode != MODE_BOOST
    assert state.valve_position == 10
    assert state.actual_temperature == 19.5
    assert ("monday", (("24:00", 5.0),)) not in state.schedule


def test_a_new_snapshot_after_a_poll_shows_the_new_values() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(RADIATOR, "Radiator", setpoint=20.0)
        cube = connect(fake)
        fake.set_setpoint(RADIATOR, 22.5)
        cube.update()
        after = snapshot_of(cube)
    assert after.device(RADIATOR).target_temperature == 22.5


def test_the_device_values_and_the_cube_values_are_copied() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(
            RADIATOR, "Radiator", setpoint=21.5, actual=19.0, valve=35, battery_low=True
        )
        fake.set_duty_cycle(12, free_slots=40)
        cube = connect(fake)
        snap = snapshot_of(cube, {RADIATOR: True})

    state = snap.device(RADIATOR)
    assert (state.name, state.room_id, state.serial) == (
        "Radiator",
        1,
        cube.device_by_rf(RADIATOR).serial,
    )
    assert state.kind == cube.device_by_rf(RADIATOR).type
    assert (state.target_temperature, state.actual_temperature, state.valve_position) == (
        21.5,
        19.0,
        35,
    )
    assert state.battery_low is True
    assert state.status.initialized is True
    assert state.status.stale is False
    assert (snap.serial, snap.firmware_version) == (cube.serial, "01.13")
    assert (snap.duty_cycle, snap.free_memory_slots) == (12, 40)


def test_the_weekly_programme_is_an_immutable_copy_with_the_same_content() -> None:
    schedule = {"monday": [{"until": "06:00", "temp": 17.5}, {"until": "24:00", "temp": 20.0}]}
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(
            RADIATOR, "Radiator", schedule={"monday": [("06:00", 17.5), ("24:00", 20.0)]}
        )
        cube = connect(fake)
        snap = snapshot_of(cube)

    state = snap.device(RADIATOR)
    assert isinstance(state.schedule, tuple)
    assert schedule_as_dict(state.schedule)["monday"] == schedule["monday"]
    assert schedule_as_dict(state.schedule) == cube.device_by_rf(RADIATOR).schedule


def test_a_value_the_device_does_not_carry_is_none() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(WINDOW, "Window", kind="window")
        cube = connect(fake)
        snap = snapshot_of(cube)

    window = snap.device(WINDOW)
    assert window.target_temperature is None
    assert window.valve_position is None
    assert window.comfort_temperature is None
    assert window.schedule == ()
    assert window.is_open is False


def test_a_device_that_is_not_in_the_snapshot_is_unknown_and_stale() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(RADIATOR, "Radiator")
        cube = connect(fake)
        snap = snapshot_of(cube)

    unknown = snap.device("FFFFFF")
    assert unknown.rf_address == "FFFFFF"
    assert unknown.target_temperature is None
    assert unknown.battery_low is None
    assert unknown.status.stale is True


def test_the_snapshot_cannot_be_changed() -> None:
    with FakeCube() as fake:
        fake.add_room(1, "Living room")
        fake.add_device(RADIATOR, "Radiator")
        cube = connect(fake)
        snap = snapshot_of(cube)

    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.duty_cycle = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        snap.devices["FFFFFF"] = snap.device(RADIATOR)  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.device(RADIATOR).target_temperature = 1.0  # type: ignore[misc]
