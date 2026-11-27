"""``MaxCube`` that also keeps the status values from the Cube's ``H:`` message.

The Cube starts every connection with an ``H:`` line: serial, RF address, firmware, an unknown
field, the HTTP connection id, the **duty cycle** (share of the radio time budget already used,
hex), the **number of free memory slots** (hex), then the date and time. The Cube may only send a
limited share of the time; at 100 % it stops sending radio commands for about an hour. The
``maxcube-api`` library reads only the first three fields, so they are picked up here.
"""

from __future__ import annotations

import base64
import binascii
import logging
import struct
from collections.abc import Callable, Iterable
from datetime import datetime

from maxcube.cube import DEFAULT_PORT, MaxCube
from maxcube.device import MAX_DEVICE_MODE_AUTOMATIC, MAX_DEVICE_MODE_MANUAL, MaxDevice
from maxcube.thermostat import MaxThermostat

from .display import encode_display_setting
from .schedule import (
    PROGRAMME_OFFSET,
    encode_set_programme,
    parse_week_program,
    scheduled_temperature,
)
from .telegram_log import TelegramLog, parse_s_status

_LOGGER = logging.getLogger(__name__)

_DUTY_CYCLE_FIELD = 5
_FREE_SLOTS_FIELD = 6
_MAX_DUTY_CYCLE = 100  # percent
# An L entry needs its length byte and the three address bytes.
_MIN_L_ENTRY_LENGTH = 4
# Offsets in an L entry, counted from the length byte (see ``_apply_l_entry``).
_L_BITS2 = 6
_L_VALVE = 7
_L_SETPOINT = 8
_L_ACTUAL_HIGH = 9
_L_ACTUAL_LOW = 10
_L_WALL_ACTUAL_LOW = 12


def split_l_entries(data: bytes) -> list[bytes]:
    """Split the bytes of an ``L`` message into device entries, each limited by its own length byte.

    The length byte counts the bytes after itself, so an entry covers ``length + 1`` bytes. Entries
    that are too short for an address, or that run past the end of the message, are left out. A bad
    length stops the scan: there is no safe resync point, so the remaining entries are discarded.
    The library does not limit its reads like this: a short last entry makes it read past the end
    and raise, which drops the status of every device in the message.
    """
    entries = []
    pos = 0
    while pos < len(data):
        end = pos + data[pos] + 1
        if data[pos] < _MIN_L_ENTRY_LENGTH or end > len(data):
            break
        entries.append(data[pos:end])
        pos = end
    return entries


def _hex_field(tokens: list[str], index: int) -> int | None:
    """Return a hex field of the H message as an integer, or ``None`` if it is missing or bad."""
    try:
        return int(tokens[index], 16)
    except (IndexError, ValueError):
        return None


def parse_h_status(message: str) -> tuple[int | None, int | None]:
    """Return ``(duty_cycle_percent, free_memory_slots)`` from the argument of an H message."""
    tokens = message.strip().split(",")
    duty = _hex_field(tokens, _DUTY_CYCLE_FIELD)
    if duty is not None and not 0 <= duty <= _MAX_DUTY_CYCLE:
        duty = None
    return duty, _hex_field(tokens, _FREE_SLOTS_FIELD)


# The library reads only the third field of the M argument (``index,count,data``).
_M_ARGUMENT_PREFIX = "0,1,"
_M_FIELD_INDEX = 2  # the Base64 data is the third field


def parse_m_envelope(argument: str) -> tuple[int, int] | None:
    """Return ``(index, total)`` from an M argument; ``None`` for a broken envelope.

    The Cube sends ``<index>,<total>,<base64>``. Only a complete message
    (``index == total``) may replace the remembered configuration: a fragment
    with a smaller index is valid data but not a new full configuration.
    """
    parts = argument.split(",")
    if len(parts) <= _M_FIELD_INDEX:
        return None
    try:
        index, total = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if total < 1 or not 0 <= index < total:
        return None
    return index, total


def is_complete_m_message(argument: str) -> bool:
    """Return True only for a readable, complete M message (last fragment)."""
    envelope = parse_m_envelope(argument)
    if envelope is None or envelope[0] != envelope[1] - 1:
        return False
    return _readable_m_payload(argument.split(",")[_M_FIELD_INDEX])


def _readable_m_payload(payload: str) -> bool:
    """Return True if the Base64 part of an M message decodes to some bytes."""
    if not payload:
        return False
    try:
        return len(base64.b64decode(payload, validate=True)) > 0
    except ValueError:  # binascii.Error is a ValueError
        return False


class MaxCubeWithStatus(MaxCube):
    """A ``MaxCube`` that exposes ``duty_cycle``, ``free_memory_slots`` and exact schedules.

    It also keeps the last readable M message (rooms and devices). Some Cubes send ``M:`` with no
    argument; the library then reads no rooms and no devices, so the remembered message is used.
    ``last_m_message`` is the Base64 part only; the integration saves it between restarts.
    """

    duty_cycle: int | None = None
    free_memory_slots: int | None = None
    last_m_message: str | None = None
    # True when the last M message was empty or unreadable (see ``parse_m_message``).
    m_message_missing: bool = False
    # Correlation of outgoing telegrams with the Cube's answers. The class-level
    # instance keeps pure tests working that construct the object without __init__;
    # __init__ replaces it with a fresh one per real Cube.
    telegram_log: TelegramLog = TelegramLog()

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        now: Callable[[], datetime] = datetime.now,
        last_m_message: str | None = None,
    ) -> None:
        # Set before super().__init__(): it reads the Cube, and the M message is parsed then.
        self.last_m_message = last_m_message
        self._now = now
        self.telegram_log = TelegramLog()
        super().__init__(host, port, now)

    def _send(self, message: str) -> bool:
        """Send a radio telegram and record it for correlation with the Cube's answers."""
        commander = self._MaxCube__commander  # the library's private connection handler
        sent = bool(commander.send_radio_msg(message))
        if sent:
            now = getattr(self, "_now", datetime.now)
            self.telegram_log.record_sent(message, now=now())
        return sent

    def _MaxCube__parse_responses(self, messages: Iterable[object]) -> None:
        """Let the library parse its messages, but evaluate ``S:`` answers as well.

        The library silently ignores ``S:``, which is the only real-time hint that
        the Cube discarded a command.  We do not replace its dispatch: the same
        message list is passed on unchanged after the ``S:`` values are recorded.
        """
        for msg in messages:
            if getattr(msg, "cmd", "") == "S":
                self._parse_s_message(getattr(msg, "arg", ""))
        super()._MaxCube__parse_responses(messages)

    def _parse_s_message(self, argument: str) -> None:
        """Record the values of an ``S:`` line and warn when a command was discarded."""
        parsed = parse_s_status(f"S:{argument}")
        if parsed is None:
            return
        status, duty, free = parsed
        if self.telegram_log.record_status(status, duty, free_slots=free):
            _LOGGER.warning(
                "MAX! Cube discarded a radio command (duty cycle %d%%, free slots %d). "
                "Wait at least 60 seconds between changes to several rooms.",
                duty,
                free,
            )

    def write_day_schedule(
        self, thermostat: MaxThermostat, day: str, slots: list[dict]
    ) -> bool:
        """Send the programme of one day to a radiator thermostat; True if the Cube took it.

        ``slots`` is ``[{"until": "HH:MM", "temp": 21.0}, ...]`` (see ``validate_periods``). The
        message is built in ``schedule.py`` instead of using the library's ``set_programme``: that
        one compares with its own lossy copy of the programme (it cuts half degrees) and pads a
        short day with one byte instead of two, so the message would be too short.
        """
        message = encode_set_programme(thermostat.rf_address, thermostat.room_id, day, slots)
        return self._send(message)

    def set_temperature_mode(
        self, thermostat: MaxDevice, temperature: float | None, mode: int | None
    ) -> bool:
        """Keep the library's combined command, but record it for correlation."""
        if not thermostat.is_thermostat() and not thermostat.is_wallthermostat():
            return False
        resolved_mode = thermostat.mode if mode is None else mode
        resolved_temperature = (
            0
            if resolved_mode == MAX_DEVICE_MODE_AUTOMATIC
            else thermostat.target_temperature
            if temperature is None
            else temperature
        )
        value = int(resolved_temperature * 2) + (resolved_mode << 6)
        message = (
            "000440000000"
            + thermostat.rf_address.upper()
            + f"{thermostat.room_id:02X}"
            + f"{value:02X}"
        )
        if not self._send(message):
            return False
        self._apply_mode_state(thermostat, resolved_mode, resolved_temperature)
        return True

    def set_mode(self, thermostat: MaxDevice, mode: int) -> bool:
        """Set a mode without the library's wall-thermostat ``AttributeError``.

        ``MaxCube.set_mode`` delegates to ``set_temperature_mode`` with no temperature. After a
        successful AUTO telegram the library calls ``thermostat.get_programmed_temp_at()``, but
        that method exists only on radiator thermostats (upstream issue #45): switching a wall
        thermostat to AUTO raises ``AttributeError`` after the telegram was already sent. This
        sends the byte-identical telegram and takes the programme temperature from the exact
        programme this integration decodes, so the entity state stays correct on both device types.
        """
        if not thermostat.is_thermostat() and not thermostat.is_wallthermostat():
            return False
        temperature = (
            0
            if mode == MAX_DEVICE_MODE_AUTOMATIC
            else (thermostat.target_temperature or 0)
        )
        value = int(temperature * 2) + (mode << 6)
        message = (
            "000440000000"
            + thermostat.rf_address.upper()
            + f"{thermostat.room_id:02X}"
            + f"{value:02X}"
        )
        if not self._send(message):
            return False
        self._apply_mode_state(thermostat, mode, temperature)
        return True

    def _programme_for(self, thermostat: MaxDevice) -> dict | None:
        """Return the exact programme of the device or of another device in the same room."""
        schedule = getattr(thermostat, "schedule", None)
        if schedule:
            return schedule
        if thermostat.room_id is None:
            return None
        for device in self.devices:
            if device.room_id == thermostat.room_id:
                schedule = getattr(device, "schedule", None)
                if schedule:
                    return schedule
        return None

    def _apply_mode_state(self, thermostat: MaxDevice, mode: int, temperature: float) -> None:
        """Update the local setpoint after a successful mode telegram."""
        thermostat.mode = mode
        if temperature > 0:
            thermostat.target_temperature = int(temperature * 2) / 2.0
            return
        if mode != MAX_DEVICE_MODE_AUTOMATIC:
            return
        schedule = self._programme_for(thermostat)
        if not schedule:
            return
        programmed = scheduled_temperature(schedule, self._now())
        if programmed is not None:
            thermostat.target_temperature = programmed

    def write_display_setting(self, rf_address: str, show_actual: bool) -> bool:
        """Send the display setting to a wall thermostat; True if the Cube took the telegram.

        ``show_actual`` True shows the measured room temperature, False the setpoint (see ``display.py``).
        Nothing is sent to an address that is not a wall thermostat of the Cube.
        """
        device = self.device_by_rf(rf_address)
        if device is None or not device.is_wallthermostat():
            return False
        message = encode_display_setting(rf_address, show_actual)
        return self._send(message)

    def parse_c_message(self, message: str) -> None:
        """Parse the C message as the library does, and keep the exact weekly programme.

        The programme is stored as ``device.schedule`` (see ``schedule.py``) for radiator
        thermostats; the library's own ``device.programme`` cuts half degrees.
        """
        super().parse_c_message(message)
        try:
            address, payload = message.split(",")[:2]
            device = self.device_by_rf(address.upper())
            if device is not None and device.is_thermostat():
                device.schedule = parse_week_program(base64.b64decode(payload)[PROGRAMME_OFFSET:])
        except (ValueError, binascii.Error):
            pass  # a message we cannot read leaves the previous schedule in place

    def parse_m_message(self, message: str) -> None:
        """Parse the M message; if it is empty or unreadable, use the remembered one.

        A readable message is parsed as the library does and remembered. The library updates the
        rooms and devices it finds by id and address, so parsing a message again does not create
        them twice and keeps the values already read. An empty or unreadable message (or one the
        library cannot parse) leaves ``m_message_missing`` set; the remembered message is parsed
        instead, if there is one, and nothing at all if there is none.
        """
        parts = message.split(",")
        payload = parts[_M_FIELD_INDEX] if len(parts) > _M_FIELD_INDEX else ""
        # A fragment is valid data, but only the last one is a full configuration.
        complete = is_complete_m_message(message)
        if _readable_m_payload(payload):
            try:
                super().parse_m_message(message)
            except (IndexError, ValueError, struct.error, UnicodeDecodeError):
                pass  # decodes, but its content is not an M message: treat it as unreadable
            else:
                if complete:
                    self.last_m_message = payload
                self.m_message_missing = not complete
                if complete:
                    return
        self.m_message_missing = True
        if self.last_m_message:
            try:
                super().parse_m_message(_M_ARGUMENT_PREFIX + self.last_m_message)
            except (IndexError, ValueError, struct.error, binascii.Error, UnicodeDecodeError):
                # A damaged message from storage must not fail the whole poll. Drop it so the next
                # readable live message can replace it.
                self.last_m_message = None

    def parse_h_message(self, message: str) -> None:
        """Parse the H message as the library does, and keep the Cube's status values."""
        super().parse_h_message(message)
        self.duty_cycle, self.free_memory_slots = parse_h_status(message)
        self.telegram_log.record_h_status(self.duty_cycle, self.free_memory_slots)

    def parse_l_message(self, message: str) -> None:
        """Parse the L message entry by entry; every value is read within its own entry.

        Replaces the library's loop, which reads bytes +5 and +6 of every entry and, for thermostats,
        up to +10, even when the entry is shorter (length byte 4 or 5). Those reads land in the next
        entry or past the end of the message. A value that an entry does not carry is set to ``None``
        (unknown), not taken from a neighbouring entry.
        """
        try:
            data = base64.b64decode(message)
        except (binascii.Error, ValueError):
            return
        for entry in split_l_entries(data):
            rf_address = self.parse_rf_address(entry[1:4])
            # A device report can be the answer to a command we sent earlier.
            self.telegram_log.acknowledge(rf_address, now=getattr(self, "_now", datetime.now)())
            device = self.device_by_rf(rf_address)
            if device is not None:
                self._apply_l_entry(device, entry)

    def _apply_l_entry(self, device: MaxDevice, entry: bytes) -> None:
        """Set the values of one device from its L entry.

        Offsets count from the length byte. Bits2 (+6, mode in bits 1-0, battery low in bit 7) exists
        only if the length byte is 6 or more. An entry with length byte 4 (5 bytes, address only)
        and one with length byte 5 (6 bytes, e.g. a window contact, bits1 at +5 but no bits2) leave
        mode, battery and valve unknown (``None``). Offsets as in the library's ``parse_l_message``.
        """
        has_bits2 = len(entry) > _L_BITS2
        device.battery = self.resolve_device_battery(entry[_L_BITS2]) if has_bits2 else None
        if device.is_thermostat():
            _apply_thermostat_values(self, device, entry)
        elif device.is_wallthermostat():
            _apply_wall_thermostat_values(self, device, entry)
        elif device.is_windowshutter():
            _apply_window_value(device, entry)


def _apply_setpoint_and_mode(cube: MaxCubeWithStatus, device: MaxDevice, entry: bytes) -> None:
    """Set the mode and target temperature of a thermostat or wall thermostat."""
    has_bits2 = len(entry) > _L_BITS2
    device.mode = cube.resolve_device_mode(entry[_L_BITS2]) if has_bits2 else None
    has_setpoint = len(entry) > _L_SETPOINT
    device.target_temperature = (entry[_L_SETPOINT] & 0x7F) / 2.0 if has_setpoint else None


def _apply_thermostat_values(cube: MaxCubeWithStatus, device: MaxDevice, entry: bytes) -> None:
    """Set the values of a radiator thermostat: valve, setpoint, mode and actual temperature.

    The actual temperature is at +9/+10 (big endian, tenths of a degree, 0 = none). The library
    sets it only in auto and manual mode and this code does the same: in boost or vacation mode
    the library sets ``actual_temperature`` to ``None``. The public description of the L message
    (Bouni, max-cube-protocol, ``L-Message.md``) names +9/+10 "date until" for the set temperature
    and says the actual temperature is "sometimes" there in auto mode. No real Cube has confirmed
    what +9/+10 hold in boost or vacation, so they are not read there.
    """
    _apply_setpoint_and_mode(cube, device, entry)
    device.valve_position = entry[_L_VALVE] if len(entry) > _L_VALVE else None
    device.actual_temperature = _thermostat_actual_temperature(entry, device.mode)


def _apply_wall_thermostat_values(cube: MaxCubeWithStatus, device: MaxDevice, entry: bytes) -> None:
    """Set the values of a wall thermostat: setpoint, mode and actual temperature.

    The actual temperature has a high bit (+8, bit 7) and a low byte (+12), in tenths of a degree.
    """
    _apply_setpoint_and_mode(cube, device, entry)
    if len(entry) > _L_WALL_ACTUAL_LOW:
        high = (entry[_L_SETPOINT] & 0x80) << 1
        device.actual_temperature = (high + entry[_L_WALL_ACTUAL_LOW]) / 10.0
    else:
        device.actual_temperature = None


def _apply_window_value(device: MaxDevice, entry: bytes) -> None:
    """Set ``is_open`` of a window contact from bits2 (+6, bits 1-0), if the entry carries it.

    A 6-byte contact entry has no bits2. Its open state is not in the frame, so it must be
    reported as unknown instead of falling back to the library's ``False`` default and claiming
    that every window is closed.
    """
    if len(entry) > _L_BITS2:
        device.is_open = (entry[_L_BITS2] & 0x03) > 0
    else:
        device.is_open = None


def _thermostat_actual_temperature(entry: bytes, mode: int | None) -> float | None:
    """Return the actual temperature of a thermostat entry, or ``None`` where the library reads none."""
    if mode not in (MAX_DEVICE_MODE_AUTOMATIC, MAX_DEVICE_MODE_MANUAL):
        return None
    if len(entry) <= _L_ACTUAL_LOW:
        return None
    tenths = entry[_L_ACTUAL_HIGH] * 256 + entry[_L_ACTUAL_LOW]
    return tenths / 10.0 if tenths else None
