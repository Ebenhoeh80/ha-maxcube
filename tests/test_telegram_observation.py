"""Tests that the Cube's answers are wired into the observation log."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from maxcube_local import cube as cube_module

ADDR = bytes.fromhex("0A1B2C")
TELEGRAM = "0004400000000A1B2C010E"


def _cube() -> cube_module.MaxCubeWithStatus:
    instance = object.__new__(cube_module.MaxCubeWithStatus)
    instance.telegram_log = cube_module.TelegramLog()  # type: ignore[assignment]
    instance._now = lambda: datetime(2026, 11, 27, 12, 0, tzinfo=UTC)  # type: ignore[method-assign]
    instance.devices = []
    return instance


class _Commander:
    def __init__(self, ok: bool = True) -> None:
        self.messages: list[str] = []
        self.ok = ok

    def send_radio_msg(self, message: str) -> bool:
        self.messages.append(message)
        return self.ok


def _install_commander(instance: cube_module.MaxCubeWithStatus, commander: _Commander) -> None:
    instance._MaxCube__commander = commander  # type: ignore[attr-defined]


def test_a_sent_setpoint_is_recorded_as_pending() -> None:
    instance = _cube()
    commander = _Commander()
    _install_commander(instance, commander)
    device = object.__new__(cube_module.MaxDevice)
    device.rf_address = "0A1B2C"
    device.room_id = 1
    device.mode = 1
    device.target_temperature = 21.0
    device.is_thermostat = lambda: True  # type: ignore[method-assign]
    device.is_wallthermostat = lambda: False  # type: ignore[method-assign]

    assert instance.set_temperature_mode(device, 21.0, None) is True
    assert commander.messages == ["0004400000000A1B2C016A"]
    assert instance.telegram_log.summary() == {
        "sent": 1,
        "acknowledged": 0,
        "rejected": 0,
        "pending": 1,
    }


def test_an_l_frame_acknowledges_the_pending_setpoint() -> None:
    instance = _cube()
    record = instance.telegram_log.record_sent(
        TELEGRAM, now=datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
    )
    entry = bytes([11]) + ADDR + b"\x09\x02\x00" + bytes(5)
    encoded = base64.b64encode(entry).decode()

    # The library part needs a real MaxCube; only the correlation is under test here.
    original = cube_module.MaxCube.parse_l_message
    cube_module.MaxCube.parse_l_message = lambda self, message: None  # type: ignore[assignment,method-assign]
    try:
        instance.parse_l_message(encoded)
    finally:
        cube_module.MaxCube.parse_l_message = original  # type: ignore[method-assign]

    assert record.status == "acknowledged"


def test_an_s_message_with_status_one_is_recorded_and_warned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instance = _cube()
    record = instance.telegram_log.record_sent(TELEGRAM)

    instance._parse_s_message("01,32,0F,02")

    assert record.status == "rejected"
    assert instance.telegram_log.queue_status["status"] == 1
    assert instance.telegram_log.queue_status["queued_telegrams"] == 2
    assert "discarded a radio command" in caplog.text


def test_h_status_updates_the_queue_view() -> None:
    instance = _cube()
    instance.telegram_log.record_status(0, 90, 3, free_slots=4)
    instance.telegram_log.record_h_status(12, 15)
    assert instance.telegram_log.queue_status["duty_cycle"] == 12
    assert instance.telegram_log.queue_status["free_memory_slots"] == 15
