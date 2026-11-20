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
    hub = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, CUBE_SERIAL), config_entry.entry_id
    )
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


async def test_a_low_battery_and_an_error_create_repair_hints_that_clear_again(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from homeassistant.helpers import issue_registry as ir

    cube.devices[0].battery = 1
    cube.errors[RADIATOR] = True
    await _setup(hass, config_entry)
    registry = ir.async_get(hass)
    ids = {issue_id for (domain, issue_id) in registry.issues if domain == DOMAIN}
    assert {i.split("_", 1)[1] for i in ids} == {
        f"battery_low_{RADIATOR}",
        f"device_error_{RADIATOR}",
    }

    cube.devices[0].battery = 0
    cube.errors[RADIATOR] = False
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not [1 for (domain, _) in registry.issues if domain == DOMAIN]


async def test_the_diagnostics_hide_addresses_and_names(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local.diagnostics import async_get_config_entry_diagnostics

    await _setup(hass, config_entry)
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(data)
    assert "192.168.10.60" not in text
    assert CUBE_SERIAL not in text and "Bad Thermostat" not in text
    assert data["devices"][0]["raw_flags"] == "0200"


async def test_reconfigure_changes_the_address_and_keeps_the_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch("custom_components.maxcube_local.config_flow._try_connect"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: NEW_HOST, "port": 62910}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == NEW_HOST


async def test_reconfigure_shows_an_error_when_the_new_address_does_not_answer(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch("custom_components.maxcube_local.config_flow._try_connect", side_effect=OSError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: NEW_HOST, "port": 62910}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_the_user_flow_creates_an_entry(hass: HomeAssistant, cube: FakeCube) -> None:
    with (
        patch("custom_components.maxcube_local.config_flow.discover_cubes", return_value=[]),
        patch("custom_components.maxcube_local.config_flow._try_connect"),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.10.70", "port": 62910}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == "192.168.10.70"


async def test_the_user_flow_reports_an_unreachable_cube_and_prefills_a_found_one(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    found = [{"host": "192.168.10.71", "serial": "KEQ9999999"}]
    with patch("custom_components.maxcube_local.config_flow.discover_cubes", return_value=found):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"
    with patch("custom_components.maxcube_local.config_flow._try_connect", side_effect=OSError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.10.71", "port": 62910}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_the_user_flow_refuses_a_cube_that_is_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.maxcube_local.config_flow.discover_cubes", return_value=[]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: config_entry.data[CONF_HOST], "port": 62910}
        )
    assert result["type"] == "abort" and result["reason"] == "already_configured"


async def test_the_poll_interval_can_be_changed_in_the_options(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120}
    )
    assert result["type"] == "create_entry"
    assert config_entry.options["scan_interval"] == 120



async def _climate_call(hass: HomeAssistant, service: str, entity_id: str, **data: object) -> None:
    await hass.services.async_call(
        "climate", service, {"entity_id": entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_the_hvac_modes_and_presets_are_written_to_the_cube(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from maxcube.device import (
        MAX_DEVICE_MODE_AUTOMATIC,
        MAX_DEVICE_MODE_BOOST,
        MAX_DEVICE_MODE_MANUAL,
        MAX_DEVICE_MODE_VACATION,
    )

    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    device = cube.devices[0]

    await _climate_call(hass, "set_hvac_mode", entity_id, hvac_mode="off")
    assert device.target_temperature == 4.5

    await _climate_call(hass, "set_hvac_mode", entity_id, hvac_mode="heat")
    assert device.target_temperature >= 5.0

    await _climate_call(hass, "set_hvac_mode", entity_id, hvac_mode="auto")
    assert device.mode == MAX_DEVICE_MODE_AUTOMATIC

    for preset, expected_mode in (
        ("boost", MAX_DEVICE_MODE_BOOST),
        ("away", MAX_DEVICE_MODE_VACATION),
        ("none", MAX_DEVICE_MODE_AUTOMATIC),
    ):
        await _climate_call(hass, "set_preset_mode", entity_id, preset_mode=preset)
        assert device.mode == expected_mode

    device.mode = MAX_DEVICE_MODE_MANUAL
    await _climate_call(hass, "set_preset_mode", entity_id, preset_mode="comfort")
    assert device.target_temperature == device.comfort_temperature
    await _climate_call(hass, "set_preset_mode", entity_id, preset_mode="eco")
    assert device.target_temperature == device.eco_temperature
    await _climate_call(hass, "set_preset_mode", entity_id, preset_mode="on")
    assert device.target_temperature == 30.5
    await _climate_call(hass, "set_temperature", entity_id, temperature=19.5)
    assert device.target_temperature == 19.5


async def test_the_climate_state_reflects_mode_valve_and_preset(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from maxcube.device import MAX_DEVICE_MODE_BOOST, MAX_DEVICE_MODE_MANUAL

    device = cube.devices[0]
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    coordinator = config_entry.runtime_data

    async def state():
        coordinator.async_set_updated_data(None)
        await hass.async_block_till_done()
        return hass.states.get(entity_id)

    device.valve_position = 40
    assert (await state()).attributes["hvac_action"] == "heating"
    device.valve_position = 0
    assert (await state()).attributes["hvac_action"] == "idle"
    device.target_temperature = 4.5
    assert (await state()).attributes["hvac_action"] == "off"
    device.target_temperature, device.mode = 30.5, MAX_DEVICE_MODE_MANUAL
    assert (await state()).attributes["preset_mode"] == "on"
    device.target_temperature = device.eco_temperature
    assert (await state()).attributes["preset_mode"] == "eco"
    device.target_temperature = 20.0
    assert (await state()).attributes["preset_mode"] == "none"
    device.mode = MAX_DEVICE_MODE_BOOST
    assert (await state()).attributes["preset_mode"] == "boost"


async def test_the_reboot_button_sends_a_datagram_and_survives_a_network_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local.button import MaxCubeRebootButton

    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "button", f"{CUBE_SERIAL}_reboot")
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch("custom_components.maxcube_local.button.socket.socket") as sock:
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    sent = sock.return_value.sendto.call_args.args[0]
    assert sent == b"eQ3Max*\x00" + CUBE_SERIAL.encode() + b"R"

    with patch("custom_components.maxcube_local.button.socket.socket") as sock:
        sock.return_value.sendto.side_effect = OSError("unreachable")
        MaxCubeRebootButton._send_reboot(b"x")  # must not raise
    assert sock.return_value.close.called


async def test_a_serial_of_the_wrong_length_is_not_sent(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local.button import MaxCubeRebootButton

    await _setup(hass, config_entry)
    button = MaxCubeRebootButton(config_entry.runtime_data)
    button.hass = hass
    button._serial = "SHORT"
    with patch("custom_components.maxcube_local.button.socket.socket") as sock:
        await button.async_press()
    assert not sock.called
