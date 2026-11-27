"""HVAC action must not invent actuator feedback the Cube never reported (CI only)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.maxcube_local.const import DOMAIN

from .conftest import RADIATOR, WALL, FakeCube


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _entity_id(hass: HomeAssistant, rf_address: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("climate", DOMAIN, rf_address)
    assert entity_id is not None
    return entity_id


async def _state(
    hass: HomeAssistant, config_entry: MockConfigEntry, entity_id: str
) -> State | None:
    # The entity reads the snapshot of the last poll, so refresh before asserting.
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return hass.states.get(entity_id)


async def test_a_wall_thermostat_has_no_hvac_action(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A wall thermostat measures and commands but has no valve; 'idle' would be a lie."""
    device = cube.devices[1]
    assert device.rf_address == WALL
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, WALL)

    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert state.state == "heat"
    assert "hvac_action" not in state.attributes

    # A heated room must not turn 'heating' either: no valve means no actuator feedback.
    device.target_temperature = 30.0
    device.actual_temperature = 19.0
    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert "hvac_action" not in state.attributes

    # OFF is derived from the mode and stays valid for wall thermostats.
    device.target_temperature = 4.5
    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert state.attributes["hvac_action"] == "off"


async def test_an_unknown_valve_has_no_hvac_action(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A short L entry leaves the valve unknown; that is different from a closed valve."""
    device = cube.devices[0]
    assert device.rf_address == RADIATOR
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, RADIATOR)

    device.valve_position = None
    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert "hvac_action" not in state.attributes

    device.valve_position = 1
    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert state.attributes["hvac_action"] == "heating"

    device.valve_position = 0
    state = await _state(hass, config_entry, entity_id)
    assert state is not None
    assert state.attributes["hvac_action"] == "idle"
