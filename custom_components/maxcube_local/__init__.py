"""The eQ-3 MAX! Cube integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import discovery_flow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from maxcube.device import MaxDevice

from .card import async_register_card
from .const import (
    CONF_CUBE_SERIAL,
    CONF_SCAN_INTERVAL,
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SERVICE_COPY_SCHEDULE,
    SERVICE_RECONNECT,
)
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .discovery import discover_cubes, is_reachable
from .identity import cube_title, is_generated_title
from .issues import async_setup_issues
from .schedule import WEEK_DAYS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.SENSOR,
]


_RECONNECT_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})
_COPY_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("source"): cv.entity_id,
        vol.Required("targets"): vol.All(cv.ensure_list, [cv.entity_id], vol.Length(min=1)),
        vol.Optional("days", default=list(WEEK_DAYS)): vol.All(
            cv.ensure_list, [vol.In(WEEK_DAYS)], vol.Length(min=1)
        ),
    }
)


def _maxcube_device(
    hass: HomeAssistant, entity_id: str
) -> tuple[str, MaxCubeCoordinator, MaxDevice]:
    """Return the entry id, coordinator and device behind a climate entity of this integration."""
    entity = er.async_get(hass).async_get(entity_id)
    if entity is not None and entity.platform == DOMAIN and entity.config_entry_id:
        entry = hass.config_entries.async_get_entry(entity.config_entry_id)
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            device = coordinator.cube.device_by_rf(entity.unique_id)
            if device is not None:
                return entity.config_entry_id, coordinator, device
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="schedule_not_a_device",
        translation_placeholders={"entity": entity_id},
    )


async def _async_copy_schedule(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Copy the weekly programme of one radiator thermostat to others of the same Cube."""
    source_entry, coordinator, source = _maxcube_device(hass, call.data["source"])
    found = {
        entity_id: _maxcube_device(hass, entity_id)
        for entity_id in dict.fromkeys(call.data["targets"])
    }
    if any(entry_id != source_entry for entry_id, _, _ in found.values()):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="schedule_other_cube"
        )
    results = await coordinator.async_copy_schedule(
        source, [device for _, _, device in found.values()], call.data["days"]
    )
    return {
        entity_id: {"result": results[device.rf_address]}
        for entity_id, (_, _, device) in found.items()
    }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide service and the weekly-programme card."""

    async def _handle_reconnect(call: ServiceCall) -> None:
        """Close the connection to the Cube and read everything again."""
        wanted = call.data.get("entry_id")
        entries = [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if wanted in (None, entry.entry_id)
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_cube_configured"
            )
        for entry in entries:
            await entry.runtime_data.async_reconnect()

    hass.services.async_register(
        DOMAIN, SERVICE_RECONNECT, _handle_reconnect, schema=_RECONNECT_SCHEMA
    )

    async def _handle_copy_schedule(call: ServiceCall) -> ServiceResponse:
        return await _async_copy_schedule(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        _handle_copy_schedule,
        schema=_COPY_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    await async_register_card(hass)
    # Offer Cubes on the network that are not set up yet (and update the address of known ones).
    async_at_started(hass, _async_scan_for_cubes)
    return True


async def _async_scan_for_cubes(hass: HomeAssistant) -> None:
    """Broadcast once after startup and start a discovery flow for every Cube that answers."""
    cubes = await hass.async_add_executor_job(discover_cubes)
    for cube in cubes:
        if _is_known_unchanged(hass, cube):
            continue  # nothing to do, and the Cube need not be disturbed
        if await hass.async_add_executor_job(is_reachable, cube["host"], DEFAULT_PORT):
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: cube["host"], CONF_CUBE_SERIAL: cube["serial"]},
            )


def _is_known_unchanged(hass: HomeAssistant, cube: dict[str, str]) -> bool:
    """Return True if an entry already manages this Cube under this address."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if cube["serial"] in (entry.unique_id, entry.data.get(CONF_CUBE_SERIAL)):
            return bool(entry.data.get(CONF_HOST) == cube["host"])
    return False


@callback
def _async_apply_identity(hass: HomeAssistant, entry: MaxCubeConfigEntry, serial: str) -> None:
    """Make the serial number the identity of the entry (unique id), and name it after the Cube.

    The title is only replaced if the integration generated it; a name the user chose stays.
    Entities and devices are not touched: they are identified by the serial number and the radio
    addresses of the devices already.
    """
    other = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, serial)
    if other is not None and other.entry_id != entry.entry_id:
        return  # a second entry for the same Cube; its setup reports it (see async_setup_entry)
    hass.config_entries.async_update_entry(
        entry,
        unique_id=serial,
        title=cube_title(serial) if is_generated_title(entry.title) else entry.title,
        data={**entry.data, CONF_CUBE_SERIAL: serial},
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )


async def async_migrate_entry(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> bool:
    """Move an entry from "identified by its address" to "identified by the Cube's serial number".

    Version 1.1 entries stored the address as unique id. The serial number is known from the first
    successful setup (versions 1.1 and later saved it in the entry); an entry without it is finished
    at its next setup, when the Cube answers.
    """
    if entry.version > 1:
        return False  # created by a newer version of the integration
    if entry.minor_version < CONFIG_ENTRY_MINOR_VERSION:
        serial = entry.data.get(CONF_CUBE_SERIAL)
        if serial:
            _async_apply_identity(hass, entry, serial)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> bool:
    """Set up MAX! Cube from a config entry."""
    coordinator = MaxCubeCoordinator(
        hass,
        entry,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    cube = coordinator.cube
    if cube.serial:
        owner = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, cube.serial)
        if owner is not None and owner.entry_id != entry.entry_id:
            # One Cube, two entries would create every device twice. Only the first one runs.
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="duplicate_cube",
                translation_placeholders={"title": owner.title},
            )
        # An entry that could not be migrated yet (no serial number saved), or whose identity was
        # overwritten by an older version of the integration, is put right now.
        if (
            entry.minor_version < CONFIG_ENTRY_MINOR_VERSION
            or entry.unique_id != cube.serial
            or entry.data.get(CONF_CUBE_SERIAL) != cube.serial
            # a title the integration generated in an older form is brought to the current one
            or (is_generated_title(entry.title) and entry.title != cube_title(cube.serial))
        ):
            _async_apply_identity(hass, entry, cube.serial)

    # Register the Cube itself as the hub device, so the thermostats and
    # contacts group under it and the firmware version is visible.
    if cube.serial:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, cube.serial)},
            manufacturer=MANUFACTURER,
            name="MAX! Cube",
            model="MAX! Cube LAN Gateway",
            serial_number=cube.serial,
            sw_version=cube.firmware_version,
        )

    _remove_stale_devices(hass, entry)
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _remove_stale_devices(hass, entry))
    )

    # What this setup runs with (the address may have been replaced during the first refresh).
    applied = (dict(entry.options), entry.data[CONF_HOST])

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_issues(hass, entry)
    # Reload when the options or the address changed (the way Home Assistant wants it: the update
    # listener schedules the reload). A change of the identity or title does not need one.
    async def _reload_on_change(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
        if (dict(entry.options), entry.data[CONF_HOST]) != applied:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_reload_on_change))
    return True


def _current_identifiers(entry: MaxCubeConfigEntry) -> set[str] | None:
    """Return the addresses of the Cube and all its devices, or ``None`` if the list is not trustworthy."""
    cube = entry.runtime_data.cube
    if not cube.devices:
        # An empty list is more likely a failed read than a Cube without any device.
        return None
    current = {device.rf_address for device in cube.devices}
    if cube.serial:
        current.add(cube.serial)
    return current


@callback
def _remove_stale_devices(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
    """Delete the registry entries of devices that are no longer paired with the Cube."""
    current = _current_identifiers(entry)
    if current is None:
        return
    registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(registry, entry.entry_id):
        ours = {identifier for domain, identifier in device_entry.identifiers if domain == DOMAIN}
        if ours and not ours & current:
            _LOGGER.info("Removing %s: it is no longer paired with the Cube", device_entry.name)
            registry.async_remove_device(device_entry.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MaxCubeConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Let the user delete a device in the UI only when the Cube no longer lists it."""
    current = _current_identifiers(entry)
    if current is None:
        return False
    ours = {identifier for domain, identifier in device_entry.identifiers if domain == DOMAIN}
    return not ours & current


async def async_unload_entry(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
