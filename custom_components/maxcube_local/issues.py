"""Repair hints in Home Assistant for devices that need attention."""

from __future__ import annotations

from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .coordinator import MaxCubeConfigEntry
from .health import (
    ISSUE_RADIO_BUSY,
    ISSUE_UNREACHABLE,
    UNREACHABLE_AFTER,
    DutyCycleWatch,
    find_problems,
)


def _issue_id(entry: MaxCubeConfigEntry, kind: str, rf_address: str) -> str:
    return f"{entry.entry_id}_{kind}_{rf_address}"


@callback
def async_setup_issues(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
    """Keep the repair hints in step with the device states after every poll."""
    coordinator = entry.runtime_data
    known: set[str] = set()
    watch = DutyCycleWatch()
    state: dict[str, Any] = {"timer": None, "unreachable": False, "busy": False}

    def _set_cube_issue(kind: str, flag: str, wanted: bool) -> None:
        """Create or delete one of the two hints about the Cube itself (only on a change)."""
        if wanted and not state[flag]:
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry, kind, "cube"),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=kind,
                translation_placeholders={"title": entry.title},
            )
        elif not wanted and state[flag]:
            ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, kind, "cube"))
        state[flag] = wanted

    @callback
    def _cancel_timer() -> None:
        cancel = state["timer"]
        state["timer"] = None
        if cancel is not None:
            cancel()

    @callback
    def _unreachable_too_long(_now: object) -> None:
        state["timer"] = None
        _set_cube_issue(ISSUE_UNREACHABLE, "unreachable", True)

    @callback
    def _update() -> None:
        if coordinator.last_update_success:
            _cancel_timer()
            _set_cube_issue(ISSUE_UNREACHABLE, "unreachable", False)
            duty = getattr(coordinator.cube, "duty_cycle", None)
            _set_cube_issue(ISSUE_RADIO_BUSY, "busy", watch.update(duty, monotonic()))
        elif state["timer"] is None and not state["unreachable"]:
            # Listeners hear about the first failure only, so the clock runs from here.
            state["timer"] = async_call_later(hass, UNREACHABLE_AFTER, _unreachable_too_long)
        cube = coordinator.cube
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
        _cancel_timer()
        _set_cube_issue(ISSUE_UNREACHABLE, "unreachable", False)
        _set_cube_issue(ISSUE_RADIO_BUSY, "busy", False)

    entry.async_on_unload(coordinator.async_add_listener(_update))
    entry.async_on_unload(_remove_all)
    _update()
