"""The eQ-3 MAX! Cube integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CUBE_SERIAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SERVICE_RECONNECT,
)
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .issues import async_setup_issues

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
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
    # Remember the Cube's serial number: it identifies the Cube if its IP address changes.
    # (Saved before the update listener below is registered, so this does not reload the entry.)
    if cube.serial and entry.data.get(CONF_CUBE_SERIAL) != cube.serial:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CUBE_SERIAL: cube.serial}
        )

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
    async_setup_issues(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: MaxCubeConfigEntry
) -> None:
    """Reload the entry when options (e.g. the poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
