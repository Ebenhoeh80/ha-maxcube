"""Repair hints in Home Assistant for devices that need attention."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .coordinator import MaxCubeConfigEntry
from .health import ISSUE_BATTERY, ISSUE_ERROR, find_problems


def _issue_id(entry: MaxCubeConfigEntry, kind: str, rf_address: str) -> str:
    return f"{entry.entry_id}_{kind}_{rf_address}"


@callback
def async_setup_issues(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
    """Keep the repair hints in step with the device states after every poll."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _update() -> None:
        cube = coordinator.cube
        if cube is None:
            return
        current: dict[str, tuple[str, str]] = {}
        for finding in find_problems(cube.devices, coordinator.device_status):
            current[_issue_id(entry, finding.kind, finding.rf_address)] = (
                finding.kind,
                finding.name,
            )
        for issue_id, (kind, name) in current.items():
            if issue_id in known:
                continue
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=kind,
                translation_placeholders={"name": name},
            )
        for issue_id in known - current.keys():
            ir.async_delete_issue(hass, DOMAIN, issue_id)
        known.clear()
        known.update(current)

    @callback
    def _remove_all() -> None:
        for issue_id in known:
            ir.async_delete_issue(hass, DOMAIN, issue_id)

    entry.async_on_unload(coordinator.async_add_listener(_update))
    entry.async_on_unload(_remove_all)
    _update()
