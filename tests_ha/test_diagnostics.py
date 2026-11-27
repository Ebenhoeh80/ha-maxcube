"""Diagnostics download: private values are redacted, queue observations stay visible.

The report is checked key by key instead of by an external snapshot file: that
keeps the redaction contract explicit and needs no snapshot regeneration when a
diagnostic field is added deliberately. This is the same contract a snapshot
would assert.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.maxcube_local.diagnostics import async_get_config_entry_diagnostics

from .conftest import CUBE_SERIAL, HOST, FakeCube

REDACTED = "**REDACTED**"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_diagnostics_redact_address_serial_and_names(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """No host, serial, room or device name may leave the integration."""
    await _setup(hass, config_entry)
    report = await async_get_config_entry_diagnostics(hass, config_entry)

    assert report["entry"][CONF_HOST] == REDACTED
    assert report["cube"]["serial"] == REDACTED
    assert report["devices"][0]["serial"] == REDACTED
    assert report["devices"][0]["name"] == REDACTED
    assert report["telegram_observation"] is not None
    text = str(report)
    for secret in (HOST, CUBE_SERIAL, "Bad Thermostat", "Bad Wandthermostat", "Bad"):
        assert secret not in text, secret


async def test_diagnostics_show_queue_and_connection_observation(
    hass: HomeAssistant, config_entry: MockConfigEntry, cube: FakeCube
) -> None:
    """Queue, backoff and telegram counters are the values needed for a support case."""
    await _setup(hass, config_entry)
    cube.telegram_log.record_status(1, 50, 2, free_slots=15)
    report = await async_get_config_entry_diagnostics(hass, config_entry)

    observation = report["telegram_observation"]
    assert observation["queue_status"]["status"] == 1
    assert observation["queue_status"]["queued_telegrams"] == 2
    assert observation["queue_status"]["free_memory_slots"] == 15
    assert observation["counts"]["sent"] == 0
    assert observation["rejected_count"] == 1
    assert report["polls"]["connect_backoff"]["failures"] == 0
    assert report["polls"]["blocked_connects"] == 0
    assert "queue_status" in report["cube"]
