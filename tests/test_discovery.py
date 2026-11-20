"""Tests for the address helpers of the discovery module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from maxcube_local import discovery

CUBES = [
    {"host": "192.168.0.222", "serial": "JEQ0355273"},
    {"host": "192.168.10.60", "serial": "JEQ0355273"},
    {"host": "192.168.10.61", "serial": "KEQ0999999"},
]


def test_every_address_of_a_serial_is_returned() -> None:
    assert discovery.hosts_for_serial(CUBES, "JEQ0355273") == ["192.168.0.222", "192.168.10.60"]
    assert discovery.hosts_for_serial(CUBES, "KEQ0000000") == []
    assert discovery.hosts_for_serial([], "JEQ0355273") == []


def test_a_reachable_address_is_recognised_and_the_connection_is_closed() -> None:
    connection = MagicMock()
    with patch.object(discovery.socket, "create_connection", return_value=connection) as connect:
        assert discovery.is_reachable("192.168.10.60", 62910, timeout=1.0)
    connect.assert_called_once_with(("192.168.10.60", 62910), timeout=1.0)
    connection.__exit__.assert_called_once()


def test_an_address_that_times_out_is_not_reachable() -> None:
    with patch.object(discovery.socket, "create_connection", side_effect=TimeoutError):
        assert not discovery.is_reachable("192.168.0.222", 62910)
