"""Diagnostics download for the eQ-3 MAX! Cube (private values are redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CUBE_SERIAL
from .coordinator import MaxCubeConfigEntry

# The title and the unique id of an entry contain the serial number of the Cube; they are not part
# of the report today, but would be hidden if they ever were.
TO_REDACT = {CONF_HOST, CONF_CUBE_SERIAL, "serial", "name", "room", "title", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MaxCubeConfigEntry
) -> dict[str, Any]:
    """Return what helps to find a problem, without addresses or names."""
    coordinator = entry.runtime_data
    snapshot = coordinator.data
    devices = []
    for state in snapshot.devices.values():
        status = state.status
        devices.append(
            {
                "type": state.kind,
                "serial": state.serial,
                "name": state.name,
                "battery_low": bool(state.battery_raw),
                "mode": state.mode,
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
                "serial": snapshot.serial,
                "firmware": snapshot.firmware_version,
                "duty_cycle": snapshot.duty_cycle,
                "free_memory_slots": snapshot.free_memory_slots,
                "queue_status": snapshot.queue_status,
                "queued_telegrams": snapshot.queued_telegrams,
                "pending_telegrams": snapshot.pending_telegrams,
                "rejected_commands": snapshot.rejected_commands,
            },
            # Only telegram hex and RF addresses: no room names, titles or cube serial.
            # ``getattr`` keeps the download useful for a Cube object that does not
            # expose the observation log (older library builds, test doubles).
            "telegram_observation": (
                log.as_dict()
                if getattr(coordinator, "_cube", None) is not None
                and (log := getattr(coordinator.cube, "telegram_log", None)) is not None
                else None
            ),
            "last_update_success": coordinator.last_update_success,
            "polls": {
                "total": coordinator.polls,
                "failed": coordinator.failed_polls,
                "last_duration_ms": coordinator.last_poll_ms,
                "interval_s": coordinator.scan_interval,
                "connect_backoff": coordinator.connect_backoff.as_dict(),
                "blocked_connects": coordinator.blocked_connects,
            },
            "devices": devices,
        },
        TO_REDACT,
    )
