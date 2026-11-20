"""Tests for finding Cubes by broadcast (the socket is replaced by a fake)."""

from __future__ import annotations

from unittest.mock import patch

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
