"""RF link status recovery for the eQ-3 MAX! Cube.

``maxcube-api`` 0.4.3 decodes the per-device status bytes of the Cube's ``L``
message but throws away the bits that describe the radio link.  This module
recovers them by subclassing :class:`~maxcube.cube.MaxCube` and re-reading the
submessages after the library has parsed them.  The library itself stays
untouched, so upstream updates keep working.

Bit mapping was verified against a real Cube (eQ-3, firmware 01.13, 16 devices,
8 rooms) on 2026-11-17.  What the hardware shows:

* ``Link_Error`` (bits2 bit 6) stayed ``0`` for all 16 devices, including one
  thermostat that had visibly stopped reporting.  This Cube does not appear to
  set it, so it cannot be the primary reachability signal.
* ``Error`` (bits1 bit 3) was set on exactly that one dead thermostat — the only
  device without ``valve_position``/``target_temperature``.  ``Error`` is the
  usable "device is not answering" flag on this firmware.
* ``Initialized`` (bits1 bit 1) was clear on four window contacts that are
  paired and polled fine.  A window contact submessage is only 6 bytes long, so
  it carries no payload; ``Initialized`` clear means "never delivered a
  configuration", not "unreachable".
* Bits1 bit 4 is set for most devices but not for all, and one contact had
  ``0x02`` (bit 1 only).  It is not an "uptodate" flag in any usable sense and
  is left unread, matching the Ada reference implementation.

Because no single bit is authoritative, the integration exposes both the raw
bits and a staleness sensor derived from when each device was last seen.  A
device that stops appearing in any frame is caught by ``stale`` regardless of
what the Cube puts in the flags.

Bit layout per submessage (byte offsets from the start of the submessage)::

    +0      length of the submessage, counted from offset 1
    +1..+3  device RF address
    +4      unknown
    +5      bits1:  bit 4 (set for most devices), bit 3 error,
                   bit 2, bit 1 initialized
    +6      bits2:  bit 7 battery low, bit 6 link error, bit 5 panel locked,
                   bit 4 gateway known, bit 3 dst, bits 1-0 mode
                   (absent on 6-byte submessages, e.g. window contacts)

Sources
-------
* Dmitry A. Kazakov, *MAX! home automation*, ``Get_L`` in
  ``gnat-sockets-connection_state_machine-elv_max_cube_client.adb``
  (fields ``Initialized``, ``Error``, ``Link_Error``).
* FHEM ``10_MAX.pm`` (``.rferror`` = "communication with link partner - if
  device is not accessible over the air from the cube").
* ``max-cube-protocol`` L-message description (flag layout).
* Empirical check against a live Cube, see the notes above.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from maxcube.cube import DEFAULT_PORT

from .cube import MaxCubeWithStatus

# bits1 (offset +5)
BIT_INITIALIZED = 1 << 1
BIT_ERROR = 1 << 3

# bits2 (offset +6)
BIT_LINK_ERROR = 1 << 6

# The library never flags a submessage shorter than this as malformed; it just
# indexes into it.  Six bytes are the minimum that carries both flag bytes.
MIN_SUBMESSAGE_LENGTH = 6


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """RF link state of a single MAX! device, as recovered from the last frame.

    ``None`` means "no frame seen yet" — distinct from ``False``, which means
    "the Cube explicitly reported this bit as clear".
    """

    initialized: bool | None
    error: bool | None
    link_error: bool | None
    last_heard: datetime | None
    stale: bool


class LinkStatusMaxCube(MaxCubeWithStatus):
    """``MaxCube`` that keeps the RF link bits the library discards.

    The dictionaries are keyed by RF address.  They are populated by
    :meth:`parse_l_message`, which runs during ``super().__init__()`` — so they
    must exist before that call.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        # Must be set before super().__init__(): it calls update(), which calls
        # parse_l_message(), which writes into these dictionaries.
        self.initialized: dict[str, bool] = {}
        self.device_error: dict[str, bool] = {}
        self.link_error: dict[str, bool] = {}
        self.last_heard: dict[str, datetime] = {}
        super().__init__(host, port, now)

    def parse_l_message(self, message: str) -> None:
        """Parse an ``L`` message, then recover the discarded flag bits."""
        # Decode first: the library's own parse raises on malformed base64, and
        # that exception must not escape this override.
        try:
            data = bytearray(base64.b64decode(message))
        except (binascii.Error, ValueError):
            return

        super().parse_l_message(message)

        stamp = datetime.now(UTC)
        pos = 0
        while pos < len(data):
            length = data[pos]
            if length < 4 or pos + length >= len(data):
                break
            rf_address = self.parse_rf_address(data[pos + 1 : pos + 4])
            self.last_heard[rf_address] = stamp
            if length >= MIN_SUBMESSAGE_LENGTH:
                bits1 = data[pos + 5]
                bits2 = data[pos + 6]
                self.initialized[rf_address] = bool(bits1 & BIT_INITIALIZED)
                self.device_error[rf_address] = bool(bits1 & BIT_ERROR)
                self.link_error[rf_address] = bool(bits2 & BIT_LINK_ERROR)
            pos += length + 1

    def device_status(self, rf_address: str, stale_after: float) -> DeviceStatus:
        """Return the cached status for one device.

        ``stale_after`` is the age in seconds after which a device that has not
        been seen in any frame counts as stale.
        """
        last_heard = self.last_heard.get(rf_address)
        if last_heard is None:
            stale = True
        else:
            age = (datetime.now(UTC) - last_heard).total_seconds()
            stale = age > stale_after

        return DeviceStatus(
            initialized=self.initialized.get(rf_address),
            error=self.device_error.get(rf_address),
            link_error=self.link_error.get(rf_address),
            last_heard=last_heard,
            stale=stale,
        )
