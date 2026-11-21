"""The integration running inside a real Home Assistant core (CI only)."""

from __future__ import annotations

from datetime import timedelta
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

from .conftest import CUBE_SERIAL, DAY, HOST, RADIATOR, WALL, WINDOW, FakeCube

NEW_HOST = "192.168.10.99"
NO_CUBES_FOUND = ("custom_components.maxcube_local.coordinator.discover_cubes", [])


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
    with (
        patch(
            "custom_components.maxcube_local.coordinator.discover_cubes",
            return_value=[{"host": NEW_HOST, "serial": CUBE_SERIAL}],
        ),
        patch("custom_components.maxcube_local.coordinator.is_reachable", return_value=True),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == CUBE_SERIAL  # the address changed, the identity did not


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
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, freezer
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
    # The error hint is gone at once; the battery hint is held for a while (the Cube reports that flag
    # unevenly) and goes when it has been clear for 15 minutes.
    ids = {issue_id for (domain, issue_id) in registry.issues if domain == DOMAIN}
    assert {i.split("_", 1)[1] for i in ids} == {f"battery_low_{RADIATOR}"}

    freezer.tick(timedelta(minutes=16))
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not [1 for (domain, _) in registry.issues if domain == DOMAIN]


async def test_the_diagnostics_hide_addresses_and_names(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await _setup(hass, config_entry)
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(data)
    assert "192.168.10.60" not in text
    assert CUBE_SERIAL not in text and "Bad Thermostat" not in text
    assert data["devices"][0]["raw_flags"] == "0200"


async def test_reconfigure_changes_the_address_and_keeps_the_identity(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    title = config_entry.title
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(
        "custom_components.maxcube_local.config_flow._try_connect", return_value=CUBE_SERIAL
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: NEW_HOST, "port": 62910}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == CUBE_SERIAL  # the address changed, the identity did not
    assert config_entry.title == title


async def test_reconfigure_refuses_another_cube(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.maxcube_local.config_flow._try_connect", return_value="KEQ9999999"
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: NEW_HOST, "port": 62910}
        )
    assert result["type"] == "abort" and result["reason"] == "wrong_cube"
    assert config_entry.data[CONF_HOST] == HOST
    assert config_entry.unique_id == CUBE_SERIAL


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
        patch(
            "custom_components.maxcube_local.config_flow._try_connect", return_value=CUBE_SERIAL
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.10.70", "port": 62910}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == "192.168.10.70"
    assert result["data"][CONF_CUBE_SERIAL] == CUBE_SERIAL
    assert result["result"].unique_id == CUBE_SERIAL


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
    with (
        patch("custom_components.maxcube_local.config_flow.discover_cubes", return_value=[]),
        patch(
            "custom_components.maxcube_local.config_flow._try_connect", return_value=CUBE_SERIAL
        ),
    ):
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


async def test_a_device_paired_later_gets_its_entities_without_a_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from .conftest import _thermostat

    await _setup(hass, config_entry)
    new = _thermostat()
    new.rf_address, new.name, new.serial = "0A1B2F", "Kitchen Thermostat", "KEQ4444444"
    cube.devices.append(new)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _entity_id(hass, "climate", "0A1B2F")
    assert _entity_id(hass, "sensor", "0A1B2F_valve")
    assert _entity_id(hass, "binary_sensor", "0A1B2F_battery")


async def test_a_device_that_left_the_cube_is_removed_but_an_empty_list_is_not_trusted(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    registry = dr.async_get(hass)
    assert registry.async_get_device_by_identifier((DOMAIN, WINDOW), config_entry.entry_id) is not None

    gone = cube.devices.pop()  # the window contact
    assert gone.rf_address == WINDOW
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_device_by_identifier((DOMAIN, WINDOW), config_entry.entry_id) is None
    assert registry.async_get_device_by_identifier((DOMAIN, RADIATOR), config_entry.entry_id) is not None

    cube.devices.clear()  # a failed read must not wipe the registry
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_device_by_identifier((DOMAIN, RADIATOR), config_entry.entry_id) is not None


async def test_the_user_may_delete_only_a_device_the_cube_no_longer_lists(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local import async_remove_config_entry_device

    await _setup(hass, config_entry)
    registry = dr.async_get(hass)
    present = registry.async_get_device_by_identifier((DOMAIN, RADIATOR), config_entry.entry_id)
    assert not await async_remove_config_entry_device(hass, config_entry, present)

    orphan = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, "FFFFFF")}
    )
    assert await async_remove_config_entry_device(hass, config_entry, orphan)

    cube.devices.clear()
    assert not await async_remove_config_entry_device(hass, config_entry, orphan)
FACTORY_ADDRESS = "192.168.0.222"


def _entry_with_serial() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=HOST,
        data={CONF_HOST: HOST, "port": 62910, CONF_CUBE_SERIAL: CUBE_SERIAL},
    )


def _factory(cube: FakeCube, calls: list[str]):
    """A Cube class that does not answer at the saved address, but at any other."""

    def build(host: str, port: int, *args: object, **kwargs: object) -> FakeCube:
        calls.append(host)
        if host == HOST:
            raise OSError("timed out")
        return cube

    return build


async def test_setup_finds_the_cube_again_when_the_saved_address_does_not_answer(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    """The Cube was off or got a new lease while Home Assistant started."""
    entry = _entry_with_serial()
    entry.add_to_hass(hass)
    calls: list[str] = []
    with (
        patch("custom_components.maxcube_local.coordinator.LinkStatusMaxCube", _factory(cube, calls)),
        patch(
            "custom_components.maxcube_local.coordinator.discover_cubes",
            return_value=[{"host": NEW_HOST, "serial": CUBE_SERIAL}],
        ),
        patch("custom_components.maxcube_local.coordinator.is_reachable", return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_HOST] == NEW_HOST
    assert calls == [HOST, NEW_HOST]


async def test_an_address_that_cannot_be_reached_is_never_saved(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    """A Cube without a lease answers from its factory address; that address is useless."""
    entry = _entry_with_serial()
    entry.add_to_hass(hass)
    calls: list[str] = []
    with (
        patch("custom_components.maxcube_local.coordinator.LinkStatusMaxCube", _factory(cube, calls)),
        patch(
            "custom_components.maxcube_local.coordinator.discover_cubes",
            return_value=[{"host": FACTORY_ADDRESS, "serial": CUBE_SERIAL}],
        ),
        patch("custom_components.maxcube_local.coordinator.is_reachable", return_value=False),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_HOST] == HOST
    assert calls == [HOST]


async def test_a_poll_and_a_command_never_use_the_cube_at_the_same_time(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """The Cube accepts a single connection; overlapping calls make one of them fail."""
    import asyncio

    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    entity_id = _entity_id(hass, "climate", RADIATOR)
    cube.io_delay = 0.15
    cube.max_active = 0

    await asyncio.gather(
        coordinator.async_refresh(),
        hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": 20.5}, blocking=True
        ),
        hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True
        ),
    )
    assert cube.max_active == 1


async def test_a_refused_connection_is_tried_once_more_before_the_cube_counts_as_gone(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """Another client (the MAX! app) can hold the single connection for a moment."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.fail_with = ConnectionRefusedError

    with patch("custom_components.maxcube_local.coordinator.POLL_RETRY_DELAY", 0):
        cube.fail_updates = 1
        await coordinator.async_refresh()
        assert coordinator.last_update_success is True

        cube.fail_updates = 2
        with patch(NO_CUBES_FOUND[0], return_value=NO_CUBES_FOUND[1]):
            await coordinator.async_refresh()
        assert coordinator.last_update_success is False


async def test_a_slow_failure_is_not_repeated(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """A timeout already took long; repeating it would hold the Cube for twice as long."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    before = cube.updates
    cube.fail_with = TimeoutError
    cube.fail_updates = 1
    with patch(NO_CUBES_FOUND[0], return_value=NO_CUBES_FOUND[1]):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert cube.updates == before + 1


async def test_the_polls_are_counted_and_timed_in_the_diagnostics(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from custom_components.maxcube_local.diagnostics import async_get_config_entry_diagnostics

    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.io_delay = 0.02
    await coordinator.async_refresh()
    with patch(NO_CUBES_FOUND[0], return_value=NO_CUBES_FOUND[1]):
        cube.fail_updates = 1
        await coordinator.async_refresh()
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    assert data["polls"]["failed"] == 1
    assert data["polls"]["total"] >= 3
    assert data["polls"]["last_duration_ms"] >= 20


async def test_two_quick_commands_are_read_back_within_a_few_seconds(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, freezer
) -> None:
    """The default merge time of 10 s would leave the second change unseen for that long."""
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)

    async def change(temperature: float) -> None:
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": temperature}, blocking=True
        )
        await hass.async_block_till_done()

    await change(19.0)  # read back at once
    before = cube.updates
    await change(20.0)  # inside the cooldown: read back after it
    assert cube.updates == before
    freezer.tick(timedelta(seconds=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert cube.updates == before + 1


@pytest.mark.parametrize("error", [OSError, TimeoutError, ConnectionResetError])
async def test_a_command_that_cannot_reach_the_cube_is_a_translated_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, error: type[OSError]
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    cube.command_error = error
    for service, data in (
        ("set_temperature", {"temperature": 20.0}),
        ("set_hvac_mode", {"hvac_mode": "auto"}),
        ("set_preset_mode", {"preset_mode": "boost"}),
    ):
        with pytest.raises(HomeAssistantError) as raised:
            await hass.services.async_call(
                "climate", service, {"entity_id": entity_id, **data}, blocking=True
            )
        assert raised.value.translation_key == "cube_unreachable"
        assert raised.value.translation_domain == DOMAIN
        assert not isinstance(raised.value, OSError)


async def test_a_command_the_cube_does_not_accept_is_a_translated_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    cube.accept_commands = False
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": 20.0}, blocking=True
        )
    assert raised.value.translation_key == "command_rejected"


async def test_a_programme_write_that_cannot_reach_the_cube_is_a_translated_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)

    def broken(*args: object) -> bool:
        raise TimeoutError("timed out")

    cube.write_day_schedule = broken  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "maxcube_local",
            "set_schedule",
            {
                "entity_id": entity_id,
                "days": ["monday"],
                "periods": [{"until": "24:00", "temperature": 19.0}],
            },
            blocking=True,
        )
    assert raised.value.translation_key == "cube_unreachable"


def _translations(name: str) -> dict:
    import json
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / "maxcube_local"
    return json.loads((base / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("file", ["strings.json", "translations/en.json", "translations/de.json"])
async def test_every_preset_of_the_thermostat_has_a_translated_name(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, file: str
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    entry = er.async_get(hass).async_get(entity_id)
    assert entry is not None and entry.translation_key == "thermostat"
    presets = hass.states.get(entity_id).attributes["preset_modes"]
    assert "on" in presets
    states = _translations(file)["entity"]["climate"]["thermostat"]["state_attributes"]["preset_mode"]["state"]
    assert set(presets) <= set(states)


async def test_no_identifier_appears_anywhere_in_the_diagnostics(hass: HomeAssistant, cube: FakeCube) -> None:
    """Search the whole report (as it is downloaded) for every address, serial number and name."""
    import json

    from custom_components.maxcube_local.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CUBE_SERIAL,
        title=f"MAX! Cube ({CUBE_SERIAL})",
        data={CONF_HOST: HOST, "port": 62910, CONF_CUBE_SERIAL: CUBE_SERIAL},
    )
    await _setup(hass, entry)
    report = json.dumps(await async_get_config_entry_diagnostics(hass, entry), default=str)

    identifiers = {
        "host": HOST,
        "serial of the Cube": CUBE_SERIAL,
        "title": entry.title,
        "unique id": entry.unique_id,
        "room": '"Bad"',
    }
    for device in cube.devices:
        identifiers[f"serial of {device.rf_address}"] = device.serial
        identifiers[f"name of {device.rf_address}"] = device.name
    for what, value in identifiers.items():
        assert value not in report, f"{what} leaks into the diagnostics"
    assert "192.168" not in report


def _cube_issues(hass: HomeAssistant) -> set[str]:
    from homeassistant.helpers import issue_registry as ir

    return {
        issue_id.split("_", 1)[1]
        for (domain, issue_id) in ir.async_get(hass).issues
        if domain == DOMAIN
    }


async def test_a_cube_that_stays_unreachable_for_six_hours_creates_a_repair_hint_that_clears(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.fail_updates = 10_000
    with patch(NO_CUBES_FOUND[0], return_value=NO_CUBES_FOUND[1]):
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False
        assert "cube_unreachable_cube" not in _cube_issues(hass)

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=5, minutes=59))
        await hass.async_block_till_done()
        assert "cube_unreachable_cube" not in _cube_issues(hass)

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=6, minutes=1))
        await hass.async_block_till_done()
        assert "cube_unreachable_cube" in _cube_issues(hass)

        cube.fail_updates = 0
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.last_update_success is True
    assert "cube_unreachable_cube" not in _cube_issues(hass)


async def test_a_short_outage_creates_no_repair_hint(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    cube.fail_updates = 1
    cube.fail_with = TimeoutError
    with patch(NO_CUBES_FOUND[0], return_value=NO_CUBES_FOUND[1]):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    await coordinator.async_refresh()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=7))
    await hass.async_block_till_done()
    assert "cube_unreachable_cube" not in _cube_issues(hass)


async def test_a_sustained_high_radio_load_creates_a_repair_hint_with_hysteresis(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    clock = [1000.0]
    with patch("custom_components.maxcube_local.issues.monotonic", lambda: clock[0]):
        cube.duty_cycle = 95
        await _setup(hass, config_entry)
        coordinator = config_entry.runtime_data
        assert "radio_busy_cube" not in _cube_issues(hass)

        clock[0] += 300
        await coordinator.async_refresh()
        assert "radio_busy_cube" not in _cube_issues(hass)

        clock[0] += 400
        await coordinator.async_refresh()
        assert "radio_busy_cube" in _cube_issues(hass)

        cube.duty_cycle = 85  # between the thresholds: stays
        clock[0] += 60
        await coordinator.async_refresh()
        assert "radio_busy_cube" in _cube_issues(hass)

        cube.duty_cycle = 70
        clock[0] += 60
        await coordinator.async_refresh()
        assert "radio_busy_cube" not in _cube_issues(hass)


async def test_the_cube_repair_hints_are_removed_when_the_entry_unloads(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    clock = [0.0]
    with patch("custom_components.maxcube_local.issues.monotonic", lambda: clock[0]):
        cube.duty_cycle = 99
        await _setup(hass, config_entry)
        clock[0] = 10_000
        await config_entry.runtime_data.async_refresh()
        assert "radio_busy_cube" in _cube_issues(hass)
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert not _cube_issues(hass)


async def _write_monday(hass: HomeAssistant, entity_id: str, temperature: float) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {
            "entity_id": entity_id,
            "days": ["monday"],
            "periods": [{"until": "24:00", "temperature": temperature}],
        },
        blocking=True,
        return_response=True,
    )


async def test_every_programme_write_keeps_one_check_and_no_callback_behind(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, "climate", RADIATOR)
    coordinator = config_entry.runtime_data
    cube.store_writes = False
    registered = len(config_entry._on_unload or [])

    for temperature in (18.0, 19.0, 20.0):
        await _write_monday(hass, entity_id, temperature)

    assert len(coordinator._verify_timers) == 1
    assert len(config_entry._on_unload or []) == registered  # nothing added per write
    # The newest programme is the one that gets checked.
    assert coordinator._verify_days[RADIATOR]["monday"][0]["temp"] == 20.0


async def test_the_lifecycle_leaves_no_tasks_or_listeners_behind(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP
    from homeassistant.helpers import issue_registry as ir

    await _setup(hass, config_entry)
    first = config_entry.runtime_data
    cube.store_writes = False
    await _write_monday(hass, _entity_id(hass, "climate", RADIATOR), 18.0)
    assert first._verify_timers

    # Reload: the old coordinator is shut down completely, a new one runs.
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data is not first
    assert not first._verify_timers and not first._listeners

    # Home Assistant stops, then the entries are unloaded.
    second = config_entry.runtime_data
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert not second._verify_timers and not second._listeners
    assert second._unsub_refresh is None
    assert not [1 for (domain, _) in ir.async_get(hass).issues if domain == DOMAIN]


async def test_a_low_battery_report_that_comes_and_goes_does_not_flap(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube, freezer
) -> None:
    """The Cube reports the flag unevenly; the sensor stays on through a short gap and then clears."""
    cube.devices[0].battery = 1
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    entity_id = _entity_id(hass, "binary_sensor", f"{RADIATOR}_battery")
    assert hass.states.get(entity_id).state == "on"

    cube.devices[0].battery = 0  # a gap of a few minutes, as measured on a real thermostat
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"

    cube.devices[0].battery = 1
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"

    cube.devices[0].battery = 0  # the batteries were changed: the flag stays away
    freezer.tick(timedelta(minutes=14))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"

    freezer.tick(timedelta(minutes=2))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"
