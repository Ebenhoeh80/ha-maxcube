"""Tests for finding Cubes by broadcast (the socket is replaced by a fake)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from maxcube_local import discovery

ANSWER = b"eQ3MaxApKEQ0523864>I\x00\x09\x7f\x2c\x01\x13"

Packet = tuple[bytes, tuple[str, int]]


class FakeSocket:
    """Answers with the given packets, then times out."""

    def __init__(self, packets: list[Packet], bind_fails: bool = False) -> None:
        self.packets = list(packets)
        self.bind_fails = bind_fails
        self.sent: list[Packet] = []
        self.closed = False

    def setsockopt(self, *args: object) -> None:
        pass

    def bind(self, address: tuple[str, int]) -> None:
        if self.bind_fails:
            raise OSError("address in use")

    def settimeout(self, timeout: float) -> None:
        pass

    def sendto(self, data: bytes, address: tuple[str, int]) -> None:
        self.sent.append((data, address))

    def recvfrom(self, size: int) -> Packet:
        if not self.packets:
            raise TimeoutError
        return self.packets.pop(0)

    def close(self) -> None:
        self.closed = True


def run(packets: list[Packet], bind_fails: bool = False) -> tuple[list[dict[str, str]], FakeSocket]:
    fake = FakeSocket(packets, bind_fails)
    with patch.object(discovery.socket, "socket", return_value=fake):
        return discovery.discover_cubes(timeout=0.1), fake


def test_a_cube_that_answers_is_found_with_its_serial() -> None:
    cubes, fake = run([(ANSWER, ("192.168.1.50", 23272))])
    assert cubes == [{"host": "192.168.1.50", "serial": "KEQ0523864"}]
    assert fake.sent[0][1] == ("255.255.255.255", 23272)
    assert fake.closed


def test_other_packets_are_ignored_and_the_same_cube_counts_once() -> None:
    cubes, _ = run(
        [
            (b"something else", ("192.168.1.9", 23272)),
            (ANSWER, ("192.168.1.50", 23272)),
            (ANSWER, ("192.168.1.50", 40000)),
        ]
    )
    assert cubes == [{"host": "192.168.1.50", "serial": "KEQ0523864"}]


def test_a_busy_port_does_not_stop_the_search() -> None:
    cubes, _ = run([(ANSWER, ("192.168.1.50", 23272))], bind_fails=True)
    assert len(cubes) == 1


def test_nothing_answering_gives_an_empty_list() -> None:
    cubes, fake = run([])
    assert cubes == [] and fake.closed


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


def test_a_datagram_with_a_malformed_serial_is_ignored() -> None:
    packets = [
        b"eQ3MaxApKEQ05238",  # too short
        b"eQ3MaxApKEQ0523864X",  # the serial is the first ten characters: valid
        b"eQ3MaxApkeq0523864",  # lower case
        b"eQ3MaxAp<script>1",  # markup
        b"eQ3MaxApKEQ05238" + bytes([255, 254]),  # not ASCII
        b"eQ3MaxAp KEQ052386",  # blank inside
    ]
    cubes, _ = run([(p, (f"192.168.1.{i}", 23272)) for i, p in enumerate(packets, start=10)])
    assert cubes == [{"host": "192.168.1.11", "serial": "KEQ0523864"}]


def test_the_serial_shape_is_ten_capitals_or_digits() -> None:
    assert discovery.is_valid_serial("KEQ0523864")
    assert discovery.is_valid_serial("0123456789")
    arabic_digits = "".join(chr(0x663 + i % 2) for i in range(2))
    for bad in ("", "KEQ052386", "KEQ05238644", "keq0523864", "KEQ052386" + chr(10), "KEQ-523864", "KEQ05238" + arabic_digits):
        assert not discovery.is_valid_serial(bad), bad
