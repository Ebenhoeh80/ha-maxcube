"""A small, typed asyncio client for the MAX! Cube's line protocol (P2-2 building block).

This is deliberately *not* a drop-in replacement for ``maxcube-api`` yet: the
sync library still owns parsing and the coordinator still uses the executor.
What lives here are the primitives a real async client needs — a connection,
line framing with CRLF leftovers, one serialised request at a time, timeouts and
a ``q:`` teardown — with types that survive ``mypy --strict``.

The lock is only held for the actual exchange.  Cancelling a request therefore
cannot leave a cancelled task holding the lock while a connection stays open:
the failure that the executor bridge previously had to work around is avoided
by construction rather than by a compensating release.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Final

DEFAULT_PORT: Final = 62910
DEFAULT_TIMEOUT: Final = 5.0
_LINE_END: Final = b"\r\n"
_TEARDOWN: Final = "q:"

Connector = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


class AsyncCubeError(Exception):
    """The Cube did not answer in time or the connection is gone."""


class AsyncCubeClient:
    """One serialised request/response exchange with a Cube over asyncio streams."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        connector: Connector | None = None,
    ) -> None:
        """Create a client; the connection is opened by :meth:`connect`."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._connect = connector or self._open_connection
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def _open_connection(self, host: str, port: int) -> tuple[
        asyncio.StreamReader, asyncio.StreamWriter
    ]:
        """Open the TCP connection with a deadline (no blocking socket calls)."""
        return await asyncio.wait_for(asyncio.open_connection(host, port), self.timeout)

    async def connect(self) -> None:
        """Open the connection; a failed attempt leaves no half-connected state."""
        self._reader, self._writer = await self._connect(self.host, self.port)

    @property
    def connected(self) -> bool:
        """Whether a connection is currently held."""
        return self._writer is not None

    async def request(self, command: str) -> tuple[str, ...]:
        """Send one command and read the reply lines, holding the serialisation lock."""
        async with self._lock:
            writer = self._writer
            reader = self._reader
            if writer is None or reader is None:
                raise AsyncCubeError("The Cube is not connected")
            writer.write(command.encode("ascii") + _LINE_END)
            await asyncio.wait_for(writer.drain(), self.timeout)
            return await self._read_reply(reader)

    async def _read_reply(self, reader: asyncio.StreamReader) -> tuple[str, ...]:
        """Read one CRLF-terminated reply line.

        ``readuntil`` handles a CRLF split across TCP packets itself, so no
        manual buffer scanning (and no unsigned slice magic) is needed here.
        """
        try:
            data = await asyncio.wait_for(reader.readuntil(_LINE_END), self.timeout)
        except (asyncio.LimitOverrunError, asyncio.IncompleteReadError) as err:
            raise AsyncCubeError("The Cube sent an incomplete line") from err
        except TimeoutError as err:
            raise AsyncCubeError("The Cube did not answer in time") from err
        return (data[: -len(_LINE_END)].decode("utf-8", errors="replace"),)

    async def close(self) -> None:
        """Send the Cube's ``q:`` teardown and close the stream, idempotently."""
        async with self._lock:
            writer = self._writer
            self._writer = None
            self._reader = None
            if writer is None:
                return
            try:
                writer.write(_TEARDOWN.encode("ascii") + _LINE_END)
                await asyncio.wait_for(writer.drain(), self.timeout)
            except (OSError, TimeoutError):
                pass  # the Cube may already have closed; teardown is best effort
            writer.close()
            with contextlib.suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), self.timeout)

    async def __aenter__(self) -> AsyncCubeClient:
        """Connect on entry."""
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Always tear the connection down on exit."""
        await self.close()
