"""Repair hints in Home Assistant for devices and for the Cube itself that need attention."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

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


class _IssueKeeper:
    """Keeps the repair hints of one entry in step with the Cube after every poll."""

    def __init__(self, hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = entry.runtime_data
        self._devices: set[str] = set()  # ids of the hints for single devices
        self._watch = DutyCycleWatch()
        self._cancel_timer: Callable[[], None] | None = None
        self._unreachable = False
        self._busy = False

    @callback
    def update(self) -> None:
        """Bring all hints up to date (called after every poll, successful or not)."""
        if self._coordinator.last_update_success:
            self._clear_timer()
            self._set_unreachable(False)
            duty = getattr(self._coordinator.cube, "duty_cycle", None)
            self._set_busy(self._watch.update(duty, monotonic()))
        elif self._cancel_timer is None and not self._unreachable:
            # Listeners hear about the first failure only, so the clock runs from here.
            self._cancel_timer = async_call_later(
                self._hass, UNREACHABLE_AFTER, self._unreachable_too_long
            )
        self._update_device_hints()

    @callback
    def remove_all(self) -> None:
        """Delete every hint of this entry (the entry is unloaded)."""
        for issue_id in self._devices:
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
        self._devices.clear()
        self._clear_timer()
        self._set_unreachable(False)
        self._set_busy(False)

    def _clear_timer(self) -> None:
        cancel, self._cancel_timer = self._cancel_timer, None
        if cancel is not None:
            cancel()

    @callback
    def _unreachable_too_long(self, _now: object) -> None:
        self._cancel_timer = None
        self._set_unreachable(True)

    def _set_unreachable(self, wanted: bool) -> None:
        self._set_cube_issue(ISSUE_UNREACHABLE, self._unreachable, wanted)
        self._unreachable = wanted

    def _set_busy(self, wanted: bool) -> None:
        self._set_cube_issue(ISSUE_RADIO_BUSY, self._busy, wanted)
        self._busy = wanted

    def _set_cube_issue(self, kind: str, present: bool, wanted: bool) -> None:
        """Create or delete one of the hints about the Cube itself (only on a change)."""
        issue_id = _issue_id(self._entry, kind, "cube")
        if wanted and not present:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=kind,
                translation_placeholders={"title": self._entry.title},
            )
        elif present and not wanted:
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)

    def _update_device_hints(self) -> None:
        coordinator = self._coordinator
        current: dict[str, tuple[str, str]] = {}
        for finding in find_problems(
            coordinator.cube.devices, coordinator.device_status, coordinator.battery_low
        ):
            issue_id = _issue_id(self._entry, finding.kind, finding.rf_address)
            current[issue_id] = (finding.kind, finding.name)
        for issue_id, (kind, name) in current.items():
            if issue_id in self._devices:
                continue
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=kind,
                translation_placeholders={"name": name},
            )
        for issue_id in self._devices - current.keys():
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
        self._devices = set(current)


@callback
def async_setup_issues(hass: HomeAssistant, entry: MaxCubeConfigEntry) -> None:
    """Keep the repair hints in step with the Cube after every poll."""
    keeper = _IssueKeeper(hass, entry)
    entry.async_on_unload(entry.runtime_data.async_add_listener(keeper.update))
    entry.async_on_unload(keeper.remove_all)
    keeper.update()
