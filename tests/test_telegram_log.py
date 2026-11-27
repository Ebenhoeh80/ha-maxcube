"""Regression tests for observing outgoing telegrams and the Cube's queue answers.

The Cube acknowledges a radio telegram with an ``L:`` frame and reports rejected
commands in its ``S:`` answer.  Nothing here promises a root-cause fix for the
live cross-talk observation: it only makes sent, acknowledged and rejected
commands visible.
"""

from __future__ import annotations

from datetime import UTC, datetime

from maxcube_local import telegram_log


def test_a_sent_telegram_is_pending_until_an_l_frame_acknowledges_it() -> None:
    log = telegram_log.TelegramLog()
    now = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)

    record = log.record_sent("0004400000000A1B2C010E", now=now)
    assert record.status == "pending"
    assert log.summary() == {"sent": 1, "acknowledged": 0, "rejected": 0, "pending": 1}

    assert log.acknowledge("0A1B2C", now=now) == 1
    assert record.status == "acknowledged"
    assert log.summary() == {"sent": 1, "acknowledged": 1, "rejected": 0, "pending": 0}


def test_an_unknown_rf_address_does_not_acknowledge_another_device() -> None:
    log = telegram_log.TelegramLog()
    log.record_sent("0004400000000A1B2C010E")
    assert log.acknowledge("0A1B2D") == 0
    assert log.summary()["pending"] == 1


def test_a_recent_frame_acknowledges_at_most_one_telegram_per_device() -> None:
    """One L frame is one answer: two queued commands must not be cleared by one frame."""
    log = telegram_log.TelegramLog()
    first = log.record_sent("0004400000000A1B2C010E")
    second = log.record_sent("0004400000000A1B2C010F")

    assert log.acknowledge("0A1B2C") == 1
    assert [first.status, second.status] == ["acknowledged", "pending"]


def test_a_s_status_of_one_marks_the_matching_telegram_as_rejected() -> None:
    log = telegram_log.TelegramLog()
    record = log.record_sent("0004400000000A1B2C010E")

    assert log.record_status(1, 30, 2, free_slots=4) is True
    assert record.status == "rejected"
    assert log.summary() == {"sent": 1, "acknowledged": 0, "rejected": 1, "pending": 0}
    assert log.queue_status == {
        "status": 1,
        "duty_cycle": 30,
        "free_memory_slots": 4,
        "queued_telegrams": 2,
    }


def test_a_s_status_of_zero_only_updates_the_queue_information() -> None:
    log = telegram_log.TelegramLog()
    record = log.record_sent("0004400000000A1B2C010E")
    assert log.record_status(0, 33, 0, free_slots=15) is False
    assert record.status == "pending"
    assert log.queue_status["status"] == 0
    assert log.queue_status["queued_telegrams"] == 0
    assert log.queue_status["duty_cycle"] == 33
    assert log.queue_status["free_memory_slots"] == 15


def test_the_s_status_is_parsed_from_a_raw_cube_message() -> None:
    # S:<status>,<duty cycle>,<free slots>,...
    assert telegram_log.parse_s_status("S:00,32,0F,00") == (0, 50, 15, 0)
    assert telegram_log.parse_s_status("S:01,FF,00,03") == (1, 100, 0, 3)
    assert telegram_log.parse_s_status("") is None
    assert telegram_log.parse_s_status("S:xx,32,0F,00") is None
    assert telegram_log.parse_s_status("S:00,32") is None


def test_the_rf_address_is_taken_from_the_wire_format() -> None:
    assert telegram_log.rf_address_from_telegram("0004400000000A1B2C010E") == "0A1B2C"
    assert telegram_log.rf_address_from_telegram("0004400000000a1b2c010e") == "0A1B2C"
    assert telegram_log.rf_address_from_telegram("short") is None
    assert telegram_log.rf_address_from_telegram("") is None


def test_an_s_rejection_without_a_tracked_telegram_is_still_visible() -> None:
    log = telegram_log.TelegramLog()
    assert log.record_status(1, 90, 0, free_slots=0) is True
    assert log.summary() == {"sent": 0, "acknowledged": 0, "rejected": 0, "pending": 0}
    assert log.queue_status["status"] == 1


def test_the_log_keeps_only_a_bounded_number_of_recent_telegrams() -> None:
    log = telegram_log.TelegramLog(limit=2)
    first = log.record_sent("0004400000000A1B2C010E")
    second = log.record_sent("0004400000000A1B2C010F")
    third = log.record_sent("0004400000000A1B2C0110")
    assert len(log.records) == 2
    assert first not in log.records
    assert second in log.records and third in log.records


def test_an_h_status_updates_queue_values_without_erasing_a_rejection() -> None:
    log = telegram_log.TelegramLog()
    log.record_status(1, 90, 0, free_slots=0)
    log.record_h_status(12, 15)
    assert log.queue_status["duty_cycle"] == 12
    assert log.queue_status["free_memory_slots"] == 15
    assert log.queue_status["status"] == 1
