"""The eQ-3 MAX! Cube integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MANUFACTURER
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.SENSOR,
]


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

    # Register the Cube itself as the hub device, so the thermostats and
    # contacts group under it and the firmware version is visible.
    cube = coordinator.cube
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
