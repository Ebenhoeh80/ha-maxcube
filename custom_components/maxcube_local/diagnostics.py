"""Diagnostics download for the eQ-3 MAX! Cube (private values are redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CUBE_SERIAL
from .coordinator import MaxCubeConfigEntry

TO_REDACT = {CONF_HOST, CONF_CUBE_SERIAL, "serial", "name", "room"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MaxCubeConfigEntry
) -> dict[str, Any]:
    """Return what helps to find a problem, without addresses or names."""
    coordinator = entry.runtime_data
    cube = coordinator.cube
    devices = []
    for device in getattr(cube, "devices", []):
        status = coordinator.device_status(device.rf_address)
        devices.append(
            {
                "type": device.type,
                "serial": device.serial,
                "name": device.name,
                "battery_low": bool(getattr(device, "battery", 0)),
                "mode": getattr(device, "mode", None),
                "initialized": status.initialized,
                "error": status.error,
                "link_error": status.link_error,
                "raw_flags": status.raw_flags,
                "last_heard": status.last_heard.isoformat() if status.last_heard else None,
            }
        )
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "options": dict(entry.options),
            "cube": {
                "serial": getattr(cube, "serial", None),
                "firmware": getattr(cube, "firmware_version", None),
                "duty_cycle": getattr(cube, "duty_cycle", None),
                "free_memory_slots": getattr(cube, "free_memory_slots", None),
            },
            "last_update_success": coordinator.last_update_success,
            "polls": {
                "total": coordinator.polls,
                "failed": coordinator.failed_polls,
                "last_duration_ms": coordinator.last_poll_ms,
                "interval_s": coordinator.scan_interval,
            },
            "devices": devices,
        },
        TO_REDACT,
    )
