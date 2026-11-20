"""The identity of a Cube is its serial number: entry, title, discovery, migration (real Home Assistant core)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.maxcube_local import async_migrate_entry, config_flow
from custom_components.maxcube_local.const import CONF_CUBE_SERIAL, DOMAIN

from .conftest import CUBE_SERIAL, HOST, FakeCube

NEW_HOST = "192.168.10.99"
TITLE = f"MAX! Cube {CUBE_SERIAL}"
CONNECT = "custom_components.maxcube_local.config_flow._try_connect"
FLOW_DISCOVER = "custom_components.maxcube_local.config_flow.discover_cubes"
COORD_DISCOVER = "custom_components.maxcube_local.coordinator.discover_cubes"
COORD_REACHABLE = "custom_components.maxcube_local.coordinator.is_reachable"


def _legacy(*, with_serial: bool = True, title: str | None = None) -> MockConfigEntry:
    """An entry as versions up to 1.3.2 made it: identified by its address, title with the address."""
    data = {CONF_HOST: HOST, CONF_PORT: 62910}
    if with_serial:
        data[CONF_CUBE_SERIAL] = CUBE_SERIAL
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=HOST,
        title=title or f"MAX! Cube ({HOST})",
        data=data,
        version=1,
        minor_version=1,
    )


def _modern(host: str = HOST) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=CUBE_SERIAL,
        title=TITLE,
        data={CONF_HOST: host, CONF_PORT: 62910, CONF_CUBE_SERIAL: CUBE_SERIAL},
        version=1,
        minor_version=2,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _snapshot(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[set[str], set[str]]:
    entities = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    devices = {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)}
    return entities, devices


# ------------------------------------------------------------------ migration


async def test_an_entry_with_a_serial_is_migrated_without_losing_entities_or_devices(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    entry = _legacy()
    await _setup(hass, entry)  # first run: creates the registry entries (and migrates)
    entities, devices = _snapshot(hass, entry)
    assert entities and devices

    # Put the entry back into the old shape and load it again, as after an update of the integration.
    hass.config_entries.async_update_entry(entry, unique_id=HOST, title=f"MAX! Cube ({HOST})", minor_version=1)
    await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.unique_id, entry.title, entry.minor_version) == (CUBE_SERIAL, TITLE, 2)
    assert entry.data[CONF_CUBE_SERIAL] == CUBE_SERIAL
    assert _snapshot(hass, entry) == (entities, devices)


async def test_a_title_chosen_by_the_user_survives_the_migration(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    entry = _legacy(title="Heizung Erdgeschoss")
    await _setup(hass, entry)
    assert entry.title == "Heizung Erdgeschoss"
    assert entry.unique_id == CUBE_SERIAL


async def test_an_entry_without_a_saved_serial_is_finished_at_its_first_setup(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    entry = _legacy(with_serial=False)
    await _setup(hass, entry)
    assert (entry.unique_id, entry.title, entry.minor_version) == (CUBE_SERIAL, TITLE, 2)
    assert entry.data[CONF_CUBE_SERIAL] == CUBE_SERIAL


async def test_an_entry_of_a_newer_major_version_is_refused(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=CUBE_SERIAL, data={CONF_HOST: HOST, CONF_PORT: 62910}, version=2)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_a_second_entry_for_the_same_cube_does_not_run(hass: HomeAssistant, cube: FakeCube) -> None:
    """One Cube under two entries would create every device twice."""
    first = _modern()
    await _setup(hass, first)
    second = _legacy()
    second.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(second.entry_id)
    assert second.state is ConfigEntryState.SETUP_ERROR
    assert first.state is ConfigEntryState.LOADED
    assert dr.async_entries_for_config_entry(dr.async_get(hass), second.entry_id) == []
    assert er.async_entries_for_config_entry(er.async_get(hass), second.entry_id) == []
    assert second.unique_id == HOST  # not taken over; the first entry owns the serial number
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), first.entry_id)
    assert devices and all(device.config_entries == {first.entry_id} for device in devices)

    # removing the duplicate leaves the devices and entities of the first entry as they are
    before = _snapshot(hass, first)
    assert await hass.config_entries.async_remove(second.entry_id)
    await hass.async_block_till_done()
    assert _snapshot(hass, first) == before
    assert first.state is ConfigEntryState.LOADED


async def test_a_legacy_entry_is_migrated_even_while_the_cube_is_offline(hass: HomeAssistant) -> None:
    """The live case of 2026-11-20: the Cube did not answer, the entry was in retry."""
    entry = _legacy()
    entry.add_to_hass(hass)
    with (
        patch("custom_components.maxcube_local.coordinator.MaxCubeWithStatus", side_effect=OSError("timed out")),
        patch(COORD_DISCOVER, return_value=[]),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert (entry.unique_id, entry.title, entry.minor_version) == (CUBE_SERIAL, TITLE, 2)


async def test_an_entry_without_a_serial_is_finished_when_the_cube_answers_later(
    hass: HomeAssistant, cube: FakeCube
) -> None:
    entry = _legacy(with_serial=False)
    entry.add_to_hass(hass)
    attempts = []

    def build(host: str, port: int, *args: object, **kwargs: object) -> FakeCube:
        attempts.append(host)
        if len(attempts) == 1:
            raise OSError("timed out")
        return cube

    with (
        patch("custom_components.maxcube_local.coordinator.MaxCubeWithStatus", build),
        patch(COORD_DISCOVER, return_value=[]),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert (entry.unique_id, entry.minor_version) == (HOST, 1)  # nothing to migrate to yet
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert (entry.unique_id, entry.minor_version) == (CUBE_SERIAL, 2)


async def test_an_identity_overwritten_by_an_older_version_is_put_right(hass: HomeAssistant, cube: FakeCube) -> None:
    """Version 1.3.2 wrote the address back into the unique id after a downgrade and a new address."""
    entry = _modern()
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, unique_id=NEW_HOST)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (entry.unique_id, entry.minor_version) == (CUBE_SERIAL, 2)


async def test_migrating_twice_changes_nothing_more(hass: HomeAssistant) -> None:
    entry = _legacy()
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    first = (entry.unique_id, entry.title, entry.minor_version, dict(entry.data))
    assert await async_migrate_entry(hass, entry)
    assert (entry.unique_id, entry.title, entry.minor_version, dict(entry.data)) == first


# ------------------------------------------------------------------ the address changes, the identity does not


async def test_a_new_address_changes_neither_identity_nor_title(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    cube.fail_updates = 1
    with (
        patch(COORD_DISCOVER, return_value=[{"host": NEW_HOST, "serial": CUBE_SERIAL}]),
        patch(COORD_REACHABLE, return_value=True),
    ):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert entry.data[CONF_HOST] == NEW_HOST
    assert (entry.unique_id, entry.title) == (CUBE_SERIAL, TITLE)
    assert entry.state is ConfigEntryState.LOADED


async def test_another_cube_at_the_saved_address_is_not_taken_for_ours(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    entry.add_to_hass(hass)
    cube.serial = "KEQ9999999"  # a different Cube answers at the saved address
    with (
        patch(COORD_DISCOVER, return_value=[]),
        patch.object(config_flow, "discover_cubes", return_value=[]),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.unique_id == CUBE_SERIAL


async def test_a_cube_that_is_replaced_while_running_is_noticed(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    cube.serial = "KEQ9999999"
    with patch(COORD_DISCOVER, return_value=[]):
        await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success is False


async def test_the_address_is_found_when_another_cube_took_the_old_one(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    entry.add_to_hass(hass)
    seen: list[str] = []

    def build(host: str, port: int, *args: object, **kwargs: object) -> FakeCube:
        seen.append(host)
        cube.serial = "KEQ9999999" if host == HOST else CUBE_SERIAL
        return cube

    with (
        patch("custom_components.maxcube_local.coordinator.MaxCubeWithStatus", build),
        patch(COORD_DISCOVER, return_value=[{"host": NEW_HOST, "serial": CUBE_SERIAL}]),
        patch(COORD_REACHABLE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert seen == [HOST, NEW_HOST]
    assert entry.data[CONF_HOST] == NEW_HOST


# ------------------------------------------------------------------ the user flow


async def test_the_user_flow_identifies_the_cube_by_its_serial(hass: HomeAssistant, cube: FakeCube) -> None:
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 62910})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: 62910, CONF_CUBE_SERIAL: CUBE_SERIAL}
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert (entry.unique_id, entry.minor_version) == (CUBE_SERIAL, 2)


async def test_adding_a_known_cube_under_another_address_updates_the_address(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST, CONF_PORT: 62910})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_cube_set_up_by_an_old_version_is_not_added_a_second_time(hass: HomeAssistant) -> None:
    _legacy(with_serial=False).add_to_hass(hass)
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 62910})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_a_cube_without_a_serial_number_is_not_accepted(hass: HomeAssistant) -> None:
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 62910})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_the_address_prefilled_by_the_search_skips_cubes_that_are_set_up(hass: HomeAssistant) -> None:
    _modern().add_to_hass(hass)
    found = [
        {"host": "192.168.10.60", "serial": CUBE_SERIAL},
        {"host": "192.168.10.61", "serial": "KEQ0999999"},
    ]
    with patch(FLOW_DISCOVER, return_value=found):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["data_schema"]({CONF_PORT: 62910})[CONF_HOST] == "192.168.10.61"


def test_the_connection_test_closes_the_connection() -> None:
    fake = MagicMock(serial=CUBE_SERIAL)
    with patch.object(config_flow, "MaxCube", return_value=fake):
        assert config_flow._try_connect(HOST, 62910) == CUBE_SERIAL
    fake.disconnect.assert_called_once()


# ------------------------------------------------------------------ discovery


async def test_a_new_cube_is_offered_in_the_discovered_list(hass: HomeAssistant, cube: FakeCube) -> None:
    info = {CONF_HOST: HOST, CONF_CUBE_SERIAL: CUBE_SERIAL}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_INTEGRATION_DISCOVERY}, data=info
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"serial": CUBE_SERIAL, "host": HOST}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (result["title"], result["data"][CONF_HOST]) == (TITLE, HOST)
    assert hass.config_entries.async_entries(DOMAIN)[0].unique_id == CUBE_SERIAL


async def test_discovery_updates_the_address_of_a_cube_that_is_set_up(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    first = entry.runtime_data
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: NEW_HOST, CONF_CUBE_SERIAL: CUBE_SERIAL},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not first  # reloaded once with the new address


async def test_discovery_recognises_an_entry_that_is_not_migrated_yet(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _legacy()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: NEW_HOST, CONF_CUBE_SERIAL: CUBE_SERIAL},
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_the_scan_after_startup_starts_a_flow_for_a_reachable_cube(hass: HomeAssistant) -> None:
    from homeassistant.setup import async_setup_component

    found = [{"host": HOST, "serial": CUBE_SERIAL}, {"host": "192.168.0.222", "serial": "KEQ0999999"}]
    with (
        patch("custom_components.maxcube_local.discover_cubes", return_value=found),
        patch("custom_components.maxcube_local.is_reachable", side_effect=lambda host, port: host == HOST),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["unique_id"] for flow in flows] == [CUBE_SERIAL]  # the factory address is not offered


# ------------------------------------------------------------------ reloads


async def test_a_changed_address_or_changed_options_reload_the_entry_once(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    first = entry.runtime_data
    hass.config_entries.async_update_entry(entry, title="Heizung")  # a title is not a reason to reload
    await hass.async_block_till_done()
    assert entry.runtime_data is first

    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HOST: NEW_HOST})
    await hass.async_block_till_done()
    second = entry.runtime_data
    assert second is not first and entry.state is ConfigEntryState.LOADED

    hass.config_entries.async_update_entry(entry, options={"scan_interval": 120})
    await hass.async_block_till_done()
    assert entry.runtime_data is not second


async def test_a_waiting_discovery_does_not_block_adding_the_cube_by_hand(hass: HomeAssistant, cube: FakeCube) -> None:
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: HOST, CONF_CUBE_SERIAL: CUBE_SERIAL},
    )
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 62910})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_adding_a_cube_by_hand_updates_the_address_of_an_old_entry(hass: HomeAssistant) -> None:
    legacy = _legacy()
    legacy.add_to_hass(hass)
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST, CONF_PORT: 62910})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert legacy.data[CONF_HOST] == NEW_HOST


async def test_an_unexpected_error_is_shown_as_unknown(hass: HomeAssistant) -> None:
    with patch(FLOW_DISCOVER, return_value=[]), patch(CONNECT, side_effect=ValueError("garbled")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 62910})
    assert result["errors"] == {"base": "unknown"}


# ------------------------------------------------------------------ DHCP discovery (the first Cube, and a new address)


def _dhcp(ip: str) -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="max", macaddress="001a220230c2")


async def test_dhcp_offers_a_new_cube(hass: HomeAssistant) -> None:
    with patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(HOST))
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"serial": CUBE_SERIAL, "host": HOST}


async def test_dhcp_ignores_another_eq3_device(hass: HomeAssistant) -> None:
    with patch(CONNECT, side_effect=OSError("refused")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(HOST))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "cannot_connect"


async def test_dhcp_follows_a_cube_to_its_new_address(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = _modern()
    await _setup(hass, entry)
    with patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(NEW_HOST))
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST and entry.state is ConfigEntryState.LOADED


async def test_an_entry_without_a_serial_is_matched_by_its_address_but_left_unchanged(hass: HomeAssistant) -> None:
    """Another Cube could have taken the address; the migration decides at the next setup."""
    legacy = _legacy(with_serial=False)
    legacy.add_to_hass(hass)
    with patch(CONNECT, return_value=CUBE_SERIAL):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(HOST))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert CONF_CUBE_SERIAL not in legacy.data and legacy.unique_id == HOST


async def test_the_scan_does_not_touch_a_cube_that_is_set_up_at_the_same_address(hass: HomeAssistant, cube: FakeCube) -> None:
    from homeassistant.setup import async_setup_component

    _modern().add_to_hass(hass)
    found = [{"host": HOST, "serial": CUBE_SERIAL}, {"host": "192.168.10.77", "serial": "KEQ0999999"}]
    reachable = MagicMock(return_value=True)
    with (
        patch("custom_components.maxcube_local.discover_cubes", return_value=found),
        patch("custom_components.maxcube_local.is_reachable", reachable),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    assert [call.args[0] for call in reachable.call_args_list] == ["192.168.10.77"]


async def test_an_entry_without_the_serial_in_its_data_gets_it(hass: HomeAssistant, cube: FakeCube) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CUBE_SERIAL,
        title=TITLE,
        data={CONF_HOST: HOST, CONF_PORT: 62910},
        version=1,
        minor_version=2,
    )
    await _setup(hass, entry)
    assert entry.data[CONF_CUBE_SERIAL] == CUBE_SERIAL


async def test_dhcp_does_not_contact_a_cube_at_an_address_that_is_set_up(hass: HomeAssistant, cube: FakeCube) -> None:
    await _setup(hass, _modern())
    connect = MagicMock(return_value=CUBE_SERIAL)
    with patch(CONNECT, connect):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(HOST))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    connect.assert_not_called()
