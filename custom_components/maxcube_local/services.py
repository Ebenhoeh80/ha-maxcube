"""Actions of the eQ-3 MAX! Cube integration.

Home Assistant requires integration actions to be registered from an
``async_setup_services`` function in this module, called from ``async_setup``.
Entity actions for the weekly programme stay with their platform on the
declared minimum version (Home Assistant 2025.3): the newer
``async_register_platform_entity_service`` helper only exists from 2025.10, and
a fallback that registers entities at setup time would change targeting.

The actions do not start a Cube connection: they need a loaded config entry.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service as ha_service
from homeassistant.helpers.service import async_register_admin_service
from maxcube.device import MaxDevice

from .button import async_send_reboot
from .const import DOMAIN, SERVICE_COPY_SCHEDULE, SERVICE_RECONNECT
from .coordinator import MaxCubeCoordinator
from .schedule import WEEK_DAYS

SERVICE_REBOOT = "reboot"
_RECONNECT_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})
_REBOOT_SCHEMA = vol.Schema({vol.Required("entry_id"): str})
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
        if coordinator is not None and entity.unique_id in coordinator.data.devices:
            # The device is listed in the snapshot; the library object is only the write target.
            device = coordinator.cube.device_by_rf(entity.unique_id)
            if device is not None:
                return entity.config_entry_id, coordinator, device
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="schedule_not_a_device",
        translation_placeholders={"entity": entity_id},
    )


async def _async_copy_schedule(hass: HomeAssistant, data: dict[str, Any]) -> ServiceResponse:
    """Copy the weekly programme of one radiator thermostat to others of the same Cube."""
    source_entry, coordinator, source = _maxcube_device(hass, data["source"])
    found = {
        entity_id: _maxcube_device(hass, entity_id)
        for entity_id in dict.fromkeys(data["targets"])
    }
    if any(entry_id != source_entry for entry_id, _, _ in found.values()):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="schedule_other_cube"
        )
    results = await coordinator.async_copy_schedule(
        source.rf_address,
        [device.rf_address for _, _, device in found.values()],
        data["days"],
    )
    response: dict[str, Any] = {}
    for entity_id, (_, _, device) in found.items():
        response[entity_id] = {"result": dict(results[device.rf_address])}
    return response


async def _handle_reconnect(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Close the connection to the Cube and read everything again."""
    wanted = data.get("entry_id")
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


async def _handle_reboot(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Restart a Cube after an explicit admin check, using its read identity."""
    entry = hass.config_entries.async_get_entry(data["entry_id"])
    coordinator = getattr(entry, "runtime_data", None)
    if entry is None or coordinator is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_cube_configured"
        )
    serial = coordinator.data.serial or ""
    if not await async_send_reboot(hass, serial):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="reboot_no_serial"
        )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all integration-wide actions (synchronous, as Home Assistant requires)."""
    hass.services.async_register(
        DOMAIN, SERVICE_RECONNECT, _handle_reconnect, schema=_RECONNECT_SCHEMA
    )
    # Reboot interrupts every device for a moment: only an administrator may call it.
    async_register_admin_service(hass, DOMAIN, SERVICE_REBOOT, _handle_reboot, _REBOOT_SCHEMA)

    async def _handle_copy_schedule(data: dict[str, Any]) -> ServiceResponse:
        return await _async_copy_schedule(hass, data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        _handle_copy_schedule,
        schema=_COPY_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    _register_entity_actions(hass)


def _register_entity_actions(hass: HomeAssistant) -> None:
    """Use the official helper where available; older cores keep the platform registration."""
    helper = getattr(ha_service, "async_register_platform_entity_service", None)
    if helper is None:
        return

    from .climate import _SET_SCHEDULE_SCHEMA  # noqa: PLC0415  (avoids an import cycle)

    helper(
        hass,
        DOMAIN,
        "get_schedule",
        entity_domain=Platform.CLIMATE,
        func="async_get_schedule",
        schema=cv.make_entity_service_schema({}),
        supports_response=SupportsResponse.ONLY,
    )
    helper(
        hass,
        DOMAIN,
        "set_schedule",
        entity_domain=Platform.CLIMATE,
        func="async_set_schedule",
        schema=cv.make_entity_service_schema(_SET_SCHEDULE_SCHEMA),
        supports_response=SupportsResponse.OPTIONAL,
    )
