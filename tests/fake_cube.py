"""A fake MAX! Cube for tests: a TCP server that answers with synthetic frames.

The fake speaks the line protocol that ``maxcube-api`` 0.4.3 reads: after a connection it sends
``H``, ``M``, ``C`` and ``L`` lines, answers ``l:`` with a fresh ``L`` line, answers ``s:`` (radio
command) with an ``S`` line and closes the connection on ``q:``. The sub-message layout follows the
offsets the library and ``linkstatus.py`` read (the length byte counts the bytes after itself).

Every value is made up: serial ``ZZZ0000001``, addresses such as ``0A1B2C``, names such as
``Living room``. The fake shows that the code under test reads the layout the fake writes; it does
not show that a real Cube writes the same layout.
"""

from __future__ import annotations

import base64
import socket
import threading
from dataclasses import dataclass
from typing import Any

SERIAL = "ZZZ0000001"
CUBE_RF_ADDRESS = "0A1B2C"

MODE_AUTO = 0
MODE_MANUAL = 1
MODE_VACATION = 2
MODE_BOOST = 3

_TYPE_CODES = {"thermostat": 1, "wall": 3, "window": 4}
# Days in the order the C message uses (Saturday first).
_CUBE_DAYS = ("saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday")
_DEFAULT_DAY: tuple[tuple[str, float], ...] = (("24:00", 20.0),)
_DAY_BYTES = 26
_BIT_CONSTANT = 0x10  # bits1 bit 4, set on most devices
_BIT_INITIALIZED = 0x02
_BIT_ERROR = 0x08
_BIT_LINK_ERROR = 0x40
_BIT_BATTERY_LOW = 0x80


@dataclass(frozen=True)
class FakeRoom:
    """A room of the M message."""

    room_id: int
    name: str
    rf_address: str = "0A1B01"


@dataclass
class Submessage:
    """The fields of one device entry in the L message; ``build_l_submessage`` writes the bytes.

    ``kind`` is ``thermostat`` (12 bytes), ``wall`` (13 bytes, actual temperature in the last byte
    with the high bit in the setpoint byte), ``window`` (6 bytes, no bits2) or ``short`` (5 bytes,
    a "dead" telegram that carries only the address).
    """

    rf_address: str
    kind: str = "thermostat"
    bits1: int = _BIT_CONSTANT
    bits2: int = 0
    valve: int = 0
    setpoint: float = 0.0
    actual: float | None = None


@dataclass
class FakeDevice:
    """A paired device with the state the Cube reports for it."""

    rf_address: str
    name: str
    serial: str
    room_id: int = 1
    kind: str = "thermostat"
    mode: int = MODE_AUTO
    battery_low: bool = False
    initialized: bool = True
    error: bool = False
    link_error: bool = False
    valve: int = 0
    setpoint: float = 20.0
    actual: float | None = 20.0
    comfort: float = 21.0
    eco: float = 17.0
    max_temperature: float = 30.0
    min_temperature: float = 4.5
    short_telegram: bool = False
    # Day name (Monday first) -> [(until "HH:MM", temperature)]; days left out get 20 degrees all day.
    schedule: dict[str, list[tuple[str, float]]] | None = None

    def submessage(self) -> Submessage:
        """Return the L-message fields of this device."""
        bits1 = _BIT_CONSTANT
        bits1 |= _BIT_INITIALIZED if self.initialized else 0
        bits1 |= _BIT_ERROR if self.error else 0
        bits2 = self.mode & 3
        bits2 |= _BIT_BATTERY_LOW if self.battery_low else 0
        bits2 |= _BIT_LINK_ERROR if self.link_error else 0
        kind = "short" if self.short_telegram else self.kind
        return Submessage(
            self.rf_address, kind, bits1, bits2, self.valve, self.setpoint, self.actual
        )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _minutes(until: str) -> int:
    hours, minutes = until.split(":")
    return int(hours) * 60 + int(minutes)


def build_h_line(serial: str, firmware: str, duty_cycle: int, free_slots: int) -> str:
    """Return the ``H`` line; ``firmware`` is four hex digits (``0113`` is 01.13)."""
    fields = [
        serial,
        CUBE_RF_ADDRESS,
        firmware,
        "00000000",
        "00000001",
        f"{duty_cycle:02X}",
        f"{free_slots:02X}",
        "0B0C0F",
        "1000",
        "03",
        "0000",
        "04",
    ]
    return "H:" + ",".join(fields)


def build_m_line(devices: list[FakeDevice], rooms: list[FakeRoom]) -> str:
    """Return the ``M`` line with the rooms and the devices (type, address, serial, name, room)."""
    data = bytearray([0, 0, len(rooms)])
    for room in rooms:
        name = room.name.encode("utf-8")
        data += bytes([room.room_id, len(name)]) + name + bytes.fromhex(room.rf_address)
    data.append(len(devices))
    for device in devices:
        name = device.name.encode("utf-8")
        data += bytes([_TYPE_CODES[device.kind]]) + bytes.fromhex(device.rf_address)
        data += device.serial.encode("ascii") + bytes([len(name)]) + name
        data.append(device.room_id)
    return f"M:00,01,{_b64(bytes(data))}"


def _encode_week(schedule: dict[str, list[tuple[str, float]]] | None) -> bytes:
    """Encode the weekly programme: seven blocks of 26 bytes, Saturday first, 2 bytes per setpoint."""
    week = bytearray()
    for day in _CUBE_DAYS:
        slots = (schedule or {}).get(day, _DEFAULT_DAY)
        block = b"".join(
            ((round(temp * 2) << 9) | (_minutes(until) // 5)).to_bytes(2, "big")
            for until, temp in slots
        )
        week += block.ljust(_DAY_BYTES, b"\x00")
    return bytes(week)


def build_c_line(device: FakeDevice) -> str:
    """Return the ``C`` line of a thermostat or wall thermostat (settings and weekly programme)."""
    header = bytearray(29)
    header[18] = round(device.comfort * 2)
    header[19] = round(device.eco * 2)
    header[20] = round(device.max_temperature * 2)
    header[21] = round(device.min_temperature * 2)
    payload = bytes(header) + _encode_week(device.schedule)
    return f"C:{device.rf_address},{_b64(payload)}"


def build_l_submessage(sub: Submessage) -> bytes:
    """Return the bytes of one device entry of the L message (see the layout in ``linkstatus.py``)."""
    rf = bytes.fromhex(sub.rf_address)
    if sub.kind == "window":
        return bytes([5]) + rf + bytes([0, sub.bits1])
    if sub.kind == "short":
        return bytes([4]) + rf + bytes([0])
    actual = round((sub.actual or 0) * 10)  # tenths of a degree
    setpoint = round(sub.setpoint * 2) & 0x7F
    if sub.kind == "wall":
        high = 0x80 if actual >= 256 else 0
        fields = [0, sub.bits1, sub.bits2, 0, setpoint | high, 0, 0, 0, actual & 0xFF]
        return bytes([12]) + rf + bytes(fields)
    fields = [0, sub.bits1, sub.bits2, sub.valve, setpoint, actual >> 8, actual & 0xFF, 0]
    return bytes([11]) + rf + bytes(fields)


def build_l_line(devices: list[FakeDevice]) -> str:
    """Return the ``L`` line with the status of all devices."""
    return "L:" + _b64(b"".join(build_l_submessage(d.submessage()) for d in devices))


def _wire(lines: list[str]) -> bytes:
    return "".join(line + "\r\n" for line in lines).encode("ascii")


class FakeCube:
    """A Cube on 127.0.0.1 with a free port that serves one client at a time, like the real one.

    Use it as a context manager. Add rooms and devices, then connect; ``set_*`` changes the state
    that the next connection (or the next ``l:``) reports. All state is guarded by one lock because
    the server runs in its own thread.
    """

    def __init__(self, serial: str = SERIAL, firmware: str = "0113") -> None:
        self.serial = serial
        self.firmware = firmware
        self.duty_cycle = 0
        self.free_slots = 50
        self.rooms: list[FakeRoom] = []
        self.devices: list[FakeDevice] = []
        # Payloads of the radio commands (``s:``) as hex, in the order the client sent them.
        self.radio_messages: list[str] = []
        self.port = 0
        self._lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- setting up --------------------------------------------------------------------------

    def add_room(self, room_id: int, name: str) -> None:
        """Add a room to the M message."""
        with self._lock:
            self.rooms.append(FakeRoom(room_id, name))

    def add_device(
        self, rf_address: str, name: str, kind: str = "thermostat", room_id: int = 1, **state: Any
    ) -> None:
        """Add a device; ``state`` takes the other ``FakeDevice`` fields (valve, setpoint, ...)."""
        serial = f"ZZZ{len(self.devices) + 10:07d}"
        device = FakeDevice(rf_address, name, serial, room_id, kind, **state)
        with self._lock:
            self.devices.append(device)

    def set_duty_cycle(self, duty_cycle: int, free_slots: int | None = None) -> None:
        """Set the radio duty cycle (percent) and the free memory slots of the H message."""
        with self._lock:
            self.duty_cycle = duty_cycle
            if free_slots is not None:
                self.free_slots = free_slots

    # --- changing the state of one device at run time -------------------------------------------

    def set_battery(self, rf_address: str, low: bool) -> None:
        """Set the low-battery flag (bits2 bit 7)."""
        self._change(rf_address, battery_low=low)

    def set_mode(self, rf_address: str, mode: int) -> None:
        """Set the mode: 0 auto, 1 manual, 2 vacation, 3 boost."""
        self._change(rf_address, mode=mode)

    def set_valve(self, rf_address: str, valve: int) -> None:
        """Set the valve position (0 to 100)."""
        self._change(rf_address, valve=valve)

    def set_setpoint(self, rf_address: str, temperature: float) -> None:
        """Set the target temperature (half degrees)."""
        self._change(rf_address, setpoint=temperature)

    def set_actual(self, rf_address: str, temperature: float | None) -> None:
        """Set the measured temperature; ``None`` sends 0, which the library treats as no value."""
        self._change(rf_address, actual=temperature)

    def set_flags(
        self,
        rf_address: str,
        *,
        initialized: bool | None = None,
        error: bool | None = None,
        link_error: bool | None = None,
    ) -> None:
        """Set the flags that ``linkstatus`` reads; a flag passed as ``None`` is left as it is."""
        changes = {
            "initialized": initialized,
            "error": error,
            "link_error": link_error,
        }
        self._change(rf_address, **{k: v for k, v in changes.items() if v is not None})

    def set_short_telegram(self, rf_address: str, short: bool) -> None:
        """Send only the address of the device (a "dead" telegram) or the full entry again."""
        self._change(rf_address, short_telegram=short)

    def _change(self, rf_address: str, **changes: Any) -> None:
        with self._lock:
            device = next(d for d in self.devices if d.rf_address == rf_address)
            for name, value in changes.items():
                setattr(device, name, value)

    # --- the frames ----------------------------------------------------------------------------

    def frames(self) -> list[str]:
        """Return the lines sent on a new connection (H, M, C, L), without line ends."""
        with self._lock:
            lines = [
                build_h_line(self.serial, self.firmware, self.duty_cycle, self.free_slots),
                build_m_line(self.devices, self.rooms),
            ]
            lines += [build_c_line(d) for d in self.devices if d.kind != "window"]
            lines.append(build_l_line(self.devices))
        return lines

    # --- the server -------------------------------------------------------------------------------

    def start(self) -> FakeCube:
        """Listen on a free port of 127.0.0.1 in a daemon thread and return the cube."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.05)
        self.port = listener.getsockname()[1]
        self._listener = listener
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve, args=(listener,), name="fake-cube", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the server thread, close the listener and free the port."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._listener is not None:
            self._listener.close()
            self._listener = None

    def __enter__(self) -> FakeCube:
        """Start the server."""
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        """Stop the server."""
        self.stop()

    def _serve(self, listener: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # the listener was closed
            with connection:
                self._talk(connection)

    def _talk(self, connection: socket.socket) -> None:
        connection.settimeout(0.1)
        try:
            connection.sendall(_wire(self.frames()))
            pending = b""
            while not self._stop.is_set():
                try:
                    chunk = connection.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    return
                pending += chunk
                while b"\r\n" in pending:
                    line, pending = pending.split(b"\r\n", 1)
                    if not self._answer(connection, line.decode("ascii", "replace")):
                        return
        except OSError:
            return  # the client went away

    def _answer(self, connection: socket.socket, line: str) -> bool:
        """Answer one command of the client; ``False`` closes the connection."""
        command, _, argument = line.partition(":")
        if command == "q":
            return False
        if command == "l":
            with self._lock:
                reply = build_l_line(self.devices)
            connection.sendall(_wire([reply]))
        elif command == "s":
            with self._lock:
                self.radio_messages.append(base64.b64decode(argument).hex().upper())
                reply = f"S:{self.duty_cycle:02X},0,{self.free_slots:02X}"
            connection.sendall(_wire([reply]))
        return True
