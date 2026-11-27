"""Regression tests for the typed asyncio client building block (P2-2).

They use asyncio.run so the pure test suite needs no asyncio pytest plugin.
The critical case is cancellation: a cancelled request must not keep the serialisation
lock while the connection stays open.
"""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import patch

import pytest
from maxcube_local.async_client import AsyncCubeClient, AsyncCubeError


class FakeReader:
    """Just enough of StreamReader for one framed line."""

    def __init__(self, data: bytes = b"H:01,02\r\n") -> None:
        self._buffer = bytearray(data)

    async def readuntil(self, separator: bytes) -> bytes:
        index = self._buffer.find(separator)
        if index < 0:
            raise asyncio.IncompleteReadError(bytes(self._buffer), len(self._buffer) + 2)
        end = index + len(separator)
        result = bytes(self._buffer[:end])
        del self._buffer[:end]
        return result


class FakeWriter:
    """Just enough of StreamWriter to inspect what was sent."""

    def __init__(self, *, drain_error: OSError | None = None) -> None:
        self.written: list[bytes] = []
        self.closed = False
        self.drain_error = drain_error

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        if self.drain_error is not None:
            raise self.drain_error

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _client(
    data: bytes = b"H:01,02\r\n", *, drain_error: OSError | None = None
) -> tuple[AsyncCubeClient, FakeWriter]:
    reader, writer = FakeReader(data), FakeWriter(drain_error=drain_error)

    async def connector(_host: str, _port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return cast(asyncio.StreamReader, reader), cast(asyncio.StreamWriter, writer)

    client = AsyncCubeClient("127.0.0.1", connector=connector)
    asyncio.run(client.connect())
    return client, writer


def test_a_request_sends_crlf_and_returns_the_line_without_it() -> None:
    client, writer = _client()

    async def exercise() -> tuple[str, ...]:
        return await client.request("H:")

    assert asyncio.run(exercise()) == ("H:01,02",)
    assert writer.written == [b"H:\r\n"]


def test_close_sends_q_and_is_idempotent() -> None:
    client, writer = _client()

    async def exercise() -> None:
        await client.close()
        await client.close()

    asyncio.run(exercise())
    assert writer.written == [b"q:\r\n"]
    assert writer.closed is True
    assert client.connected is False


def test_the_lock_serialises_overlapping_requests() -> None:
    client, writer = _client(b"H:01\r\nH:02\r\n")
    second_started = asyncio.Event()

    async def exercise() -> None:
        async def first() -> None:
            await client.request("H:")
            second_started.set()

        async def second() -> None:
            await second_started.wait()
            assert writer.written == [b"H:\r\n"]  # first finished before second began
            await client.request("H:")

        await asyncio.gather(first(), second())

    asyncio.run(exercise())
    assert writer.written == [b"H:\r\n", b"H:\r\n"]


def test_a_cancelled_request_releases_the_lock() -> None:
    client, _writer = _client()
    gate = asyncio.Event()

    async def blocking_request() -> None:
        async with client._lock:  # noqa: SLF001  (the cancel behaviour is under test)
            await gate.wait()

    async def exercise() -> None:
        task = asyncio.create_task(blocking_request())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # A new request must be able to take the lock immediately.
        assert await asyncio.wait_for(client._lock.acquire(), 0.1)  # noqa: SLF001
        client._lock.release()  # noqa: SLF001

    asyncio.run(exercise())
    gate.set()


def test_an_incomplete_line_raises_the_typed_error() -> None:
    client, _writer = _client(data=b"H:01")

    with pytest.raises(AsyncCubeError, match="incomplete line"):
        asyncio.run(client.request("H:"))


def test_a_request_before_connect_is_rejected() -> None:
    client = AsyncCubeClient("127.0.0.1")
    with pytest.raises(AsyncCubeError, match="not connected"):
        asyncio.run(client.request("H:"))


def test_a_slow_reply_becomes_a_typed_timeout_error() -> None:
    class NeverReader(FakeReader):
        async def readuntil(self, separator: bytes) -> bytes:
            await asyncio.Event().wait()
            return b""

    reader, writer = NeverReader(), FakeWriter()

    async def connector(_host: str, _port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return cast(asyncio.StreamReader, reader), cast(asyncio.StreamWriter, writer)

    client = AsyncCubeClient("127.0.0.1", timeout=0.01, connector=connector)
    asyncio.run(client.connect())
    with pytest.raises(AsyncCubeError, match="did not answer in time"):
        asyncio.run(client.request("H:"))


def test_a_broken_teardown_does_not_hide_the_close() -> None:
    client, writer = _client(drain_error=OSError("gone"))
    asyncio.run(client.close())
    assert writer.closed is True
    assert client.connected is False


def test_the_context_manager_connects_and_tears_down() -> None:
    reader, writer = FakeReader(), FakeWriter()

    async def connector(_host: str, _port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return cast(asyncio.StreamReader, reader), cast(asyncio.StreamWriter, writer)

    async def exercise() -> None:
        async with AsyncCubeClient("127.0.0.1", connector=connector) as client:
            assert client.connected is True

    asyncio.run(exercise())
    assert writer.written == [b"q:\r\n"]
    assert writer.closed is True


def test_the_default_connector_uses_asyncio_streams() -> None:
    reader, writer = FakeReader(), FakeWriter()

    async def fake_open(host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        assert (host, port) == ("127.0.0.1", 62910)
        return cast(asyncio.StreamReader, reader), cast(asyncio.StreamWriter, writer)

    with patch("asyncio.open_connection", fake_open):
        client = AsyncCubeClient("127.0.0.1")
        asyncio.run(client.connect())
    assert client.connected is True
