"""The eQ-3 MAX! Cube integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CUBE_SERIAL,
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SERVICE_RECONNECT,
)
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .discovery import discover_cubes, is_reachable
from .identity import cube_title, is_generated_title

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
]


_RECONNECT_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide service."""

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
        if entry.minor_version < CONFIG_ENTRY_MINOR_VERSION or entry.unique_id != cube.serial:
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload when the options or the address changed (the way Home Assistant wants it: the update
    # listener schedules the reload). A change of the identity or title does not need one.
    applied = (dict(entry.options), entry.data[CONF_HOST])

    async def _reload_on_change(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
        if (dict(entry.options), entry.data[CONF_HOST]) != applied:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_reload_on_change))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
