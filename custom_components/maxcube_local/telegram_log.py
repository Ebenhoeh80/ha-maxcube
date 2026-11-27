"""Observe outgoing radio telegrams and the Cube's queue answers (pure logic).

A command sent to the Cube is *not* the same as a command carried out by a
thermostat.  The Cube answers with an ``L:`` frame when a device reports again,
and its ``S:`` line contains the queue state: duty cycle, free memory slots,
queued telegrams and a status byte (``1`` = the Cube discarded a command).
This module correlates the hex telegrams built by :mod:`cube` with those
answers so a waiting or rejected command is visible in diagnostics and in the
log instead of being mistaken for a lost setpoint.

It deliberately does **not** queue, resend or reorder commands.  The Cube owns
the queue; a second queue here would be a claim we cannot prove.  Keeping the
last few telegrams is only an observation aid.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

# The wire format is ``00 04 40 00 00 00 <rf address 3 bytes> <room> <value>``.
# In hex characters: 12 fixed characters, then 6 address characters.
_TELEGRAM_PREFIX_LENGTH = 12
_TELEGRAM_ADDRESS_LENGTH = 6
_TELEGRAM_ADDRESS_END = _TELEGRAM_PREFIX_LENGTH + _TELEGRAM_ADDRESS_LENGTH
_S_MESSAGE_FIELDS = 4
_BYTE_MAX = 0xFF
_DUTY_FULL = 100


@dataclass(slots=True)
class TelegramRecord:
    """One outgoing telegram and what the Cube told us about it so far."""

    telegram: str
    rf_address: str | None
    sent_at: datetime
    status: str = "pending"  # pending -> acknowledged | rejected

    def as_dict(self) -> dict[str, str | None]:
        """Return a redacted copy for diagnostics (no room names or serials)."""
        return {
            "telegram": self.telegram,
            "rf_address": self.rf_address,
            "sent_at": self.sent_at.isoformat(),
            "status": self.status,
        }


def rf_address_from_telegram(telegram: str) -> str | None:
    """Return the uppercase RF address from a command telegram, if it carries one."""
    if len(telegram) < _TELEGRAM_ADDRESS_END:
        return None
    address = telegram[_TELEGRAM_PREFIX_LENGTH:_TELEGRAM_ADDRESS_END].upper()
    return (
        address
        if len(address) == _TELEGRAM_ADDRESS_LENGTH
        and all(c in "0123456789ABCDEF" for c in address)
        else None
    )


def parse_s_status(message: str) -> tuple[int, int, int, int] | None:
    """Parse ``S:<status>,<duty>,<free>,<queued>``; all three counts are hex.

    Returns ``(status, duty_cycle, free_memory_slots, queued_telegrams)``.
    The status byte is ``1`` when the Cube discarded a command.  Values out of
    range are rejected: a wrong count must not be shown as a queue fact.
    """
    parts = message.strip().split(",")
    if len(parts) < _S_MESSAGE_FIELDS or not parts[0].startswith("S:"):
        return None
    try:
        values = tuple(int(part.strip().removeprefix("S:"), 16) for part in parts[:4])
    except ValueError:
        return None
    status, duty, free, queued = values
    if status not in (0, 1) or duty > _BYTE_MAX or max(free, queued) > _BYTE_MAX:
        return None
    # 0xFF is how the Cube reports a completely used radio budget. Keep the raw
    # value here; the H-message parser applies the same convention (100 %).
    return status, _DUTY_FULL if duty == _BYTE_MAX else duty, free, queued


class TelegramLog:
    """In-memory correlation of sent telegrams with ``L:`` and ``S:`` answers."""

    def __init__(self, limit: int = 20) -> None:
        """Keep at most ``limit`` recent telegrams."""
        self._records: deque[TelegramRecord] = deque(maxlen=limit)
        self.queue_status: dict[str, int | None] = {
            "status": None,
            "duty_cycle": None,
            "free_memory_slots": None,
            "queued_telegrams": None,
        }
        self.rejected_count = 0

    @property
    def records(self) -> tuple[TelegramRecord, ...]:
        """The recent telegrams, oldest first."""
        return tuple(self._records)

    def record_sent(self, telegram: str, now: datetime | None = None) -> TelegramRecord:
        """Record a telegram handed to the Cube; it stays pending until an answer arrives."""
        stamp = now or datetime.now(UTC)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        record = TelegramRecord(telegram, rf_address_from_telegram(telegram), stamp)
        self._records.append(record)
        return record

    def acknowledge(self, rf_address: str, now: datetime | None = None) -> int:
        """Mark the oldest pending telegram of a device as acknowledged by an ``L:`` frame."""
        rf_address = rf_address.upper()
        stamp = now or datetime.now(UTC)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        for record in self._records:
            if (
                record.rf_address == rf_address
                and record.status == "pending"
                and record.sent_at <= stamp
            ):
                record.status = "acknowledged"
                return 1
        return 0

    def record_status(
        self, status: int, duty_cycle: int, queued: int, *, free_slots: int | None = None
    ) -> bool:
        """Update queue values from an ``S:`` answer; return True when a command was rejected.

        A rejection is attributed to the oldest pending telegram, if there is
        one.  Without a tracked telegram the event is still counted: the queue
        status itself remains visible.
        """
        self.queue_status = {
            "status": status,
            "duty_cycle": duty_cycle,
            "free_memory_slots": free_slots,
            "queued_telegrams": queued,
        }
        if status != 1:
            return False
        self.rejected_count += 1
        for record in self._records:
            if record.status == "pending":
                record.status = "rejected"
                return True
        return True

    def record_h_status(self, duty_cycle: int | None, free_slots: int | None) -> None:
        """Fill missing queue values from the ``H:`` line of a poll."""
        if duty_cycle is not None:
            self.queue_status["duty_cycle"] = duty_cycle
        if free_slots is not None:
            self.queue_status["free_memory_slots"] = free_slots

    def summary(self) -> dict[str, int]:
        """Counts by state; ``sent`` is the total and ``pending`` the current state."""
        counts = {"sent": len(self._records), "acknowledged": 0, "rejected": 0, "pending": 0}
        for record in self._records:
            counts[record.status] += 1
        return counts

    def as_dict(self) -> dict[str, object]:
        """Return a diagnostics-friendly copy."""
        return {
            "queue_status": dict(self.queue_status),
            "telegrams": [record.as_dict() for record in self._records],
            "counts": self.summary(),
            "rejected_count": self.rejected_count,
        }
