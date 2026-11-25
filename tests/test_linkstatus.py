"""Tests for the RF link bits recovered from the L message (built without a real Cube)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from maxcube_local import linkstatus

ADDR = bytes.fromhex("0fdaed")
OTHER = bytes.fromhex("0fc373")


def submessage(addr: bytes, bits1: int, bits2: int, *, length: int = 11) -> bytes:
    """Build one L sub-message: length byte, address, unknown byte, two flag bytes, padding."""
    body = addr + b"\x09" + bytes([bits1, bits2]) + bytes(length - 6)
    return bytes([length]) + body


def make_cube() -> linkstatus.LinkStatusMaxCube:
    """A cube object without a connection (the constructor would open one)."""
    cube = object.__new__(linkstatus.LinkStatusMaxCube)
    cube.initialized, cube.device_error, cube.link_error = {}, {}, {}
    cube.last_heard, cube.raw_flags = {}, {}
    cube.parse_rf_address = lambda raw: raw.hex()  # type: ignore[method-assign]
    cube._now = lambda: datetime.now(UTC)
    return cube


def feed(cube: linkstatus.LinkStatusMaxCube, *messages: bytes) -> None:
    """Run only the recovery part of ``parse_l_message`` (the library part needs the real class)."""
    encoded = base64.b64encode(b"".join(messages)).decode()
    parent = linkstatus.MaxCubeWithStatus
    original = parent.parse_l_message
    parent.parse_l_message = lambda self, message: None  # type: ignore[method-assign]
    try:
        cube.parse_l_message(encoded)
    finally:
        parent.parse_l_message = original  # type: ignore[method-assign]


def test_clear_bits_are_reported_as_false() -> None:
    cube = make_cube()
    feed(cube, submessage(ADDR, linkstatus.BIT_INITIALIZED, 0))
    status = cube.device_status("0fdaed", 90)
    assert (status.initialized, status.error, status.link_error) == (True, False, False)


def test_each_bit_is_read_on_its_own() -> None:
    cube = make_cube()
    feed(
        cube,
        submessage(ADDR, linkstatus.BIT_ERROR, 0),
        submessage(OTHER, linkstatus.BIT_INITIALIZED, linkstatus.BIT_LINK_ERROR),
    )
    first, second = cube.device_status("0fdaed", 90), cube.device_status("0fc373", 90)
    assert (first.initialized, first.error, first.link_error) == (False, True, False)
    assert (second.initialized, second.error, second.link_error) == (True, False, True)


def test_the_raw_flag_bytes_are_kept_as_hex() -> None:
    cube = make_cube()
    feed(cube, submessage(ADDR, 0x12, 0x18))
    assert cube.device_status("0fdaed", 90).raw_flags == "1218"


def test_an_unknown_device_is_unknown_and_stale() -> None:
    status = make_cube().device_status("aaaaaa", 90)
    assert (status.initialized, status.error, status.link_error, status.raw_flags) == (None,) * 4
    assert status.stale is True


def test_a_device_heard_recently_is_not_stale_but_an_old_one_is() -> None:
    cube = make_cube()
    feed(cube, submessage(ADDR, 0, 0))
    assert cube.device_status("0fdaed", 90).stale is False
    cube.last_heard["0fdaed"] = datetime.now(UTC) - timedelta(seconds=300)
    assert cube.device_status("0fdaed", 90).stale is True


def test_malformed_input_is_ignored() -> None:
    cube = make_cube()
    cube.parse_l_message("!!! not base64 !!!")
    assert cube.last_heard == {}


def test_a_truncated_submessage_does_not_crash() -> None:
    cube = make_cube()
    feed(cube, bytes([11]) + ADDR)
    assert cube.initialized == {}


def test_a_short_submessage_without_flag_bytes_only_counts_as_heard() -> None:
    cube = make_cube()
    feed(cube, bytes([4]) + ADDR + b"\x00")
    assert "0fdaed" in cube.last_heard and "0fdaed" not in cube.initialized


def test_the_injected_clock_drives_timestamps_and_staleness() -> None:
    cube = make_cube()
    first = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    cube._now = lambda: first
    feed(cube, submessage(ADDR, 0, 0))
    assert cube.last_heard["0fdaed"] == first
    assert cube.device_status("0fdaed", 90).stale is False
    cube._now = lambda: first + timedelta(seconds=91)
    assert cube.device_status("0fdaed", 90).stale is True
