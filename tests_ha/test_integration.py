"""The integration running inside a real Home Assistant core (CI only)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.maxcube_local.const import CONF_CUBE_SERIAL, DOMAIN

from .conftest import CUBE_SERIAL, DAY, RADIATOR, WALL, WINDOW, FakeCube

NEW_HOST = "192.168.10.99"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _entity_id(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no {domain} entity {unique_id}"
    return entity_id


async def test_setup_creates_the_entities_and_the_hub_device(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    for domain, unique_id in (
        ("climate", RADIATOR),
        ("climate", WALL),
        ("sensor", f"{RADIATOR}_valve"),
        ("sensor", f"{RADIATOR}_temperature"),
        ("sensor", f"{WALL}_temperature"),
        ("sensor", f"{CUBE_SERIAL}_duty_cycle"),
        ("sensor", f"{CUBE_SERIAL}_free_memory_slots"),
        ("binary_sensor", WINDOW),
        ("binary_sensor", f"{RADIATOR}_battery"),
        ("binary_sensor", f"{CUBE_SERIAL}_connectivity"),
    ):
        assert _entity_id(hass, domain, unique_id)
    hub = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, CUBE_SERIAL)})
    assert hub is not None
    assert hub.sw_version == "01.13"


async def test_the_cube_status_sensors_show_the_values_of_the_cube(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    assert hass.states.get(_entity_id(hass, "sensor", f"{CUBE_SERIAL}_duty_cycle")).state == "12"
    slots = hass.states.get(_entity_id(hass, "sensor", f"{CUBE_SERIAL}_free_memory_slots"))
    assert slots.state == "50"


async def test_the_serial_number_is_saved_in_the_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.data[CONF_CUBE_SERIAL] == CUBE_SERIAL


async def test_the_climate_entity_shows_the_weekly_programme(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    state = hass.states.get(_entity_id(hass, "climate", RADIATOR))
    assert state.attributes["schedule"]["monday"] == DAY
    assert state.attributes["scheduled_temperature"] in (17.0, 21.5)
    # A wall thermostat shows the programme of the radiator thermostat in its room.
    wall = hass.states.get(_entity_id(hass, "climate", WALL))
    assert wall.attributes["schedule"]["monday"] == DAY


async def test_get_schedule_returns_the_programme(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    response = await hass.services.async_call(
        DOMAIN, "get_schedule", {"entity_id": entity_id}, blocking=True, return_response=True
    )
    assert response[entity_id]["sunday"] == DAY


async def test_set_schedule_dry_run_sends_nothing(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    response = await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {
            "entity_id": entity_id,
            "days": ["monday", "tuesday"],
            "periods": [{"until": "07:00", "temperature": 16.5}, {"until": "24:00", "temperature": 21}],
            "dry_run": True,
        },
        blocking=True,
        return_response=True,
    )
    assert response[entity_id]["dry_run"] is True
    assert set(response[entity_id]["would_write"]) == {"monday", "tuesday"}
    assert cube.written == []


async def test_set_schedule_writes_the_days_and_reports_the_result(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    response = await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {
            "entity_id": entity_id,
            "days": ["monday", "monday", "friday"],  # a day listed twice is written once
            "periods": [{"until": "07:00", "temperature": 16.5}, {"until": "24:00", "temperature": 21}],
        },
        blocking=True,
        return_response=True,
    )
    assert response[entity_id]["result"] == {"monday": "confirmed", "friday": "confirmed"}
    assert [(address, day) for address, day, _ in cube.written] == [
        (RADIATOR, "monday"),
        (RADIATOR, "friday"),
    ]
    assert cube.written[0][2] == [
        {"until": "07:00", "temp": 16.5},
        {"until": "24:00", "temp": 21.0},
    ]
    await hass.async_block_till_done()


async def test_set_schedule_rejects_a_bad_request_before_sending(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {
                "entity_id": entity_id,
                "days": ["monday"],
                "periods": [{"until": "23:00", "temperature": 21}],  # does not end at 24:00
            },
            blocking=True,
        )
    assert cube.written == []


async def test_set_schedule_refuses_when_the_cube_is_busy(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    cube.duty_cycle = 95
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {
                "entity_id": _entity_id(hass, "climate", RADIATOR),
                "days": ["monday"],
                "periods": [{"until": "24:00", "temperature": 21}],
            },
            blocking=True,
        )
    assert cube.written == []


async def test_set_schedule_is_for_radiator_thermostats_only(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {
                "entity_id": _entity_id(hass, "climate", WALL),
                "days": ["monday"],
                "periods": [{"until": "24:00", "temperature": 21}],
            },
            blocking=True,
        )


async def test_a_refused_write_is_an_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    cube.accept_writes = False
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {
                "entity_id": _entity_id(hass, "climate", RADIATOR),
                "days": ["monday"],
                "periods": [{"until": "24:00", "temperature": 21}],
            },
            blocking=True,
        )


async def test_reconnect_closes_the_connection_and_reads_again(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    before = (cube.disconnects, cube.updates)
    await hass.services.async_call(DOMAIN, "reconnect", {}, blocking=True)
    await hass.async_block_till_done()
    assert cube.disconnects == before[0] + 1
    assert cube.updates > before[1]


async def test_reconnect_without_a_cube_is_an_error(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})  # registers the service
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "reconnect", {}, blocking=True)


async def test_the_cube_is_found_again_under_a_new_address(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.fail_updates = 1
    with patch(
        "custom_components.maxcube_local.coordinator.discover_cubes",
        return_value=[{"host": NEW_HOST, "serial": CUBE_SERIAL}],
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == NEW_HOST


async def test_another_cube_is_not_taken_for_ours(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.fail_updates = 1
    with patch(
        "custom_components.maxcube_local.coordinator.discover_cubes",
        return_value=[{"host": NEW_HOST, "serial": "KEQ9999999"}],
    ):
        await coordinator.async_refresh()
    assert config_entry.data[CONF_HOST] == "192.168.10.60"
    assert coordinator.last_update_success is False


async def test_the_entry_unloads_cleanly(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
