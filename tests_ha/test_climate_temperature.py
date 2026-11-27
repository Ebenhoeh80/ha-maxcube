"""Regressions for temperature and mode commands that must not waste radio time (CI only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from maxcube.device import (
    MAX_DEVICE_MODE_AUTOMATIC,
    MAX_DEVICE_MODE_MANUAL,
)
from pytest_homeassistant.common import MockConfigEntry

from custom_components.maxcube_local.const import DOMAIN
from custom_components.maxcube_local.coordinator import MaxCubeCoordinator
from custom_components.maxcube_local.schedule import ScheduleError

from .conftest import RADIATOR, FakeCube


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _entity_id(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("climate", DOMAIN, RADIATOR)
    assert entity_id is not None
    return entity_id


async def _set_temperature(hass: HomeAssistant, entity_id: str, **data: object) -> None:
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_an_unchanged_setpoint_does_not_use_radio(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A repeated setpoint must not add duty cycle or trigger a read-back."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)
    commands = len(cube.temperature_modes)
    updates = cube.updates

    await _set_temperature(hass, entity_id, temperature=21.0)  # the initial value

    assert len(cube.temperature_modes) == commands
    assert cube.updates == updates


async def test_a_second_setpoint_before_the_poll_is_not_lost(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A stale poll cache must not suppress a different setpoint sent moments later.

    The Cube acknowledges a write in seconds while the next HA poll can be a minute away.
    Sending A and then B inside that window must leave B on the device, not A.
    """
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)

    # Simulate the poll that has not happened yet after the first write.
    with patch.object(MaxCubeCoordinator, "async_request_refresh", new_callable=AsyncMock):
        await _set_temperature(hass, entity_id, temperature=22.0)
        # The UI must not wait for the next poll to show what was just sent.
        assert hass.states.get(entity_id).attributes["temperature"] == 22.0
        await _set_temperature(hass, entity_id, temperature=21.0)  # still the cached value

    assert cube.temperature_modes[-2:] == [
        (RADIATOR, 22.0, MAX_DEVICE_MODE_MANUAL),
        (RADIATOR, 21.0, MAX_DEVICE_MODE_MANUAL),
    ]


async def test_a_mode_change_before_the_poll_is_not_lost(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A setpoint's MANUAL write must not hide a following mode request from the guard."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "auto"}, blocking=True
    )
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    with patch.object(MaxCubeCoordinator, "async_request_refresh", new_callable=AsyncMock):
        await _set_temperature(hass, entity_id, temperature=22.0)
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "auto"}, blocking=True
        )
        await hass.async_block_till_done()

    assert cube.temperature_modes[-1] == (RADIATOR, 0.0, MAX_DEVICE_MODE_AUTOMATIC)


async def test_an_unchanged_mode_does_not_use_radio(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A repeated preset must not send a second telegram either."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": "boost"}, blocking=True
    )
    await hass.async_block_till_done()
    commands = len(cube.temperature_modes)

    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": "boost"}, blocking=True
    )
    await hass.async_block_till_done()

    assert len(cube.temperature_modes) == commands


@pytest.mark.parametrize(("given", "sent"), [(21.4, 21.5), (21.9, 22.0)])
async def test_setpoints_are_rounded_to_half_degrees(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, given: float, sent: float
) -> None:
    """The library truncates; the integration sends the value the UI advertised."""
    await _setup(hass, config_entry)

    await _set_temperature(hass, _entity_id(hass), temperature=given)

    assert cube.temperature_modes[-1] == (RADIATOR, sent, MAX_DEVICE_MODE_MANUAL)


async def test_hvac_mode_auto_without_a_setpoint_keeps_the_weekly_programme(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A mode-only AUTO request switches back to the weekly programme."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)

    await _set_temperature(hass, entity_id, temperature=19.5)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "auto"}, blocking=True
    )
    await hass.async_block_till_done()
    assert cube.temperature_modes[-1] == (RADIATOR, 0.0, MAX_DEVICE_MODE_AUTOMATIC)
    await config_entry.runtime_data.async_refresh()  # the 2 s read-back cooldown may defer it
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == HVACMode.AUTO

    await _set_temperature(hass, entity_id, temperature=20.0, hvac_mode="off")
    assert cube.temperature_modes[-1] == (RADIATOR, 4.5, MAX_DEVICE_MODE_MANUAL)

    await _set_temperature(hass, entity_id, temperature=20.5, hvac_mode="heat")
    assert cube.temperature_modes[-1] == (RADIATOR, 20.5, MAX_DEVICE_MODE_MANUAL)


async def test_an_explicit_setpoint_beats_hvac_mode_auto(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """The frontend sends AUTO with the setpoint; an explicit target must still stick."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)

    await _set_temperature(hass, entity_id, temperature=20.0, hvac_mode="auto")

    assert cube.temperature_modes[-1] == (RADIATOR, 20.0, MAX_DEVICE_MODE_MANUAL)

    commands = len(cube.temperature_modes)
    await _set_temperature(hass, entity_id, temperature=20.0, hvac_mode="auto")
    assert len(cube.temperature_modes) == commands  # the no-change guard must still hold


@pytest.mark.parametrize("target", [20.5, 16.0, 17.5])
async def test_target_temperatures_are_sent_as_manual(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, target: float
) -> None:
    """Representative targets, including the room values used live, stay MANUAL."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)

    await _set_temperature(hass, entity_id, temperature=target)

    assert cube.temperature_modes[-1] == (RADIATOR, target, MAX_DEVICE_MODE_MANUAL)


async def test_a_busy_cube_refuses_a_temperature_change(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """The 90 % radio budget applies to setpoints and modes, not only to programmes."""
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass)
    commands = len(cube.temperature_modes)

    with (
        patch(
            "custom_components.maxcube_local.climate.check_radio_budget",
            side_effect=ScheduleError("radio_too_busy", "95"),
        ),
        pytest.raises(ServiceValidationError) as raised,
    ):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": 22.0}, blocking=True
        )

    assert raised.value.translation_key == "temperature_radio_too_busy"
    assert raised.value.translation_domain == DOMAIN
    assert len(cube.temperature_modes) == commands
