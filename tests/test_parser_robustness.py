"""Regression tests for the M/L parser hardening (P2-4)."""

from __future__ import annotations

from maxcube_local import cube

# A realistic H line followed by the first fields of an M message.
H_MESSAGE = "KEQ0523864,097f2c,0113,00000000,477719c0,32,0f,0d0c09,0900,03,0000,04"


def test_an_l_entry_cannot_read_past_the_message_end() -> None:
    # Length byte 11 but only three bytes follow: no safe resync point.
    data = bytes([11]) + bytes.fromhex("0A1B2C") + b"\x09"
    assert cube.split_l_entries(data) == []


def test_valid_entries_before_a_broken_one_are_kept() -> None:
    good = bytes([6]) + bytes.fromhex("0A1B2C") + b"\x09\x02\x00"
    broken = bytes([11]) + bytes.fromhex("0A1B2D")
    assert cube.split_l_entries(good + broken) == [good]


def test_the_m_index_is_checked_before_a_message_is_accepted() -> None:
    assert cube.parse_m_envelope("1,3,AAAA") == (1, 3)
    assert cube.parse_m_envelope("00,01,AAAA") == (0, 1)
    assert cube.parse_m_envelope("1,0,AAAA") is None  # zero total is impossible
    assert cube.parse_m_envelope("3,1,AAAA") is None  # index beyond total
    assert cube.parse_m_envelope("-1,1,AAAA") is None
    assert cube.parse_m_envelope("x,1,AAAA") is None
    assert cube.parse_m_envelope("") is None


def test_a_fragmented_m_message_is_not_mistaken_for_a_complete_cache() -> None:
    assert cube.is_complete_m_message("0,3,AAAA") is False
    assert cube.is_complete_m_message("2,3,AAAA") is True
    assert cube.is_complete_m_message("00,01,AAAA") is True
    assert cube.is_complete_m_message("broken") is False


def test_h_status_returns_no_values_for_garbage_without_changing_state() -> None:
    assert cube.parse_h_status(H_MESSAGE) == (50, 15)
    assert cube.parse_h_status("") == (None, None)
    assert cube.parse_h_status("a,b,c,d,e,zz,yy") == (None, None)
