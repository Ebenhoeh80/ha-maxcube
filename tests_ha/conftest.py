"""Fixtures for tests that run the integration inside a real Home Assistant core (CI only).

They use ``pytest-homeassistant-custom-component`` and run in their own CI job. The Cube is replaced by
a fake that behaves like the library's ``MaxCube``: no network, but real device objects.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from maxcube.device import (
    MAX_DEVICE_MODE_MANUAL,
    MAX_THERMOSTAT,
    MAX_WALL_THERMOSTAT,
    MAX_WINDOW_SHUTTER,
)
from maxcube.room import MaxRoom
from maxcube.thermostat import MaxThermostat
from maxcube.wallthermostat import MaxWallThermostat
from maxcube.windowshutter import MaxWindowShutter
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.maxcube_local.const import DOMAIN
from custom_components.maxcube_local.linkstatus import DeviceStatus

pytest_plugins = "pytest_homeassistant_custom_component"

CUBE_SERIAL = "KEQ0523864"
HOST = "192.168.10.60"
RADIATOR = "0A1B2C"
WALL = "0A1B2D"
WINDOW = "0A1B2E"

DAY = [
    {"until": "06:00", "temp": 17.0},
    {"until": "08:00", "temp": 21.5},
    {"until": "24:00", "temp": 17.0},
]


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from ``custom_components/``."""


@pytest.fixture(autouse=True)
def _no_network_scan() -> Iterator[None]:
    """The scan after startup would open a socket; the tests that want it patch it themselves."""
    with patch("custom_components.maxcube_local.discover_cubes", return_value=[]):
        yield


def _thermostat() -> MaxThermostat:
    device = MaxThermostat()
    device.type = MAX_THERMOSTAT
    device.rf_address = RADIATOR
    device.room_id = 1
    device.name = "Bad Thermostat"
    device.serial = "KEQ1111111"
    device.battery = 0
    device.mode = MAX_DEVICE_MODE_MANUAL
    device.target_temperature = 21.0
    device.actual_temperature = 19.5
    device.valve_position = 30
    device.comfort_temperature = 21.5
    device.eco_temperature = 17.0
    device.min_temperature = 5.0
    device.max_temperature = 30.0
    device.programme = {}
    device.schedule = {
        day: [dict(slot) for slot in DAY]
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }
    return device


def _wall_thermostat() -> MaxWallThermostat:
    device = MaxWallThermostat()
    device.type = MAX_WALL_THERMOSTAT
    device.rf_address = WALL
    device.room_id = 1
    device.name = "Bad Wandthermostat"
    device.serial = "KEQ2222222"
    device.battery = 0
    device.mode = MAX_DEVICE_MODE_MANUAL
    device.target_temperature = 21.0
    device.actual_temperature = 19.8
    device.comfort_temperature = 21.5
    device.eco_temperature = 17.0
    device.min_temperature = 5.0
    device.max_temperature = 30.0
    return device


def _window() -> MaxWindowShutter:
    device = MaxWindowShutter()
    device.type = MAX_WINDOW_SHUTTER
    device.rf_address = WINDOW
    device.room_id = 1
    device.name = "Bad Fenster"
    device.serial = "KEQ3333333"
    device.battery = 0
    device.is_open = False
    return device


class FakeCube:
    """Behaves like the library's ``MaxCube`` without any network."""

    def __init__(self) -> None:
        self.serial = CUBE_SERIAL
        self.firmware_version = "01.13"
        self.duty_cycle: int | None = 12
        self.free_memory_slots: int | None = 50
        room = MaxRoom()
        room.id = 1
        room.name = "Bad"
        self.rooms = [room]
        self.devices = [_thermostat(), _wall_thermostat(), _window()]
        self.use_persistent_connection = True
        self.updates = 0
        self.disconnects = 0
        self.fail_updates = 0
        self.errors: dict[str, bool] = {}
        self.accept_writes = True
        self.written: list[tuple[str, str, list[dict[str, Any]]]] = []

    def update(self) -> None:
        self.updates += 1
        if self.fail_updates:
            self.fail_updates -= 1
            raise OSError("Cube not reachable")

    def disconnect(self) -> None:
        self.disconnects += 1

    def device_status(self, rf_address: str, stale_after: float) -> DeviceStatus:
        """Report every device as healthy and recently heard."""
        return DeviceStatus(
            initialized=True,
            error=self.errors.get(rf_address, False),
            link_error=False,
            last_heard=datetime.now(UTC),
            stale=False,
            raw_flags="0200",
        )

    def room_by_id(self, room_id: int | None) -> MaxRoom | None:
        return next((room for room in self.rooms if room.id == room_id), None)

    def devices_by_room(self, room: MaxRoom) -> list[Any]:
        return [device for device in self.devices if device.room_id == room.id]

    def write_day_schedule(self, thermostat: Any, day: str, slots: list[dict[str, Any]]) -> bool:
        self.written.append((thermostat.rf_address, day, slots))
        if self.accept_writes:
            thermostat.schedule[day] = slots  # the Cube would show it after a while; here at once
        return self.accept_writes

    def set_target_temperature(self, device: Any, temperature: float) -> bool:
        device.target_temperature = temperature
        return True

    def set_mode(self, device: Any, mode: int) -> bool:
        device.mode = mode
        return True


@pytest.fixture
def cube() -> Iterator[FakeCube]:
    """Patch the integration's cube class with a fake and return the fake."""
    fake = FakeCube()
    with patch("custom_components.maxcube_local.coordinator.LinkStatusMaxCube", lambda *a, **k: fake):
        yield fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for the Cube (setup is done by the tests)."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=HOST,
        title=f"MAX! Cube ({HOST})",
        data={CONF_HOST: HOST, CONF_PORT: 62910},
        options={},
    )
