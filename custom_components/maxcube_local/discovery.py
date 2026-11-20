"""UDP broadcast discovery for the eQ-3 MAX! Cube LAN gateway.

The Cube answers a small broadcast datagram on UDP port 23272 with a packet
that starts with ``eQ3MaxAp`` followed by its 10-character serial number. The
source address of that reply is the Cube's IP. This lets the config flow
pre-fill the host instead of making the user look the IP up.

The sockets are blocking, so :func:`discover_cubes` must be run in the executor.
"""

from __future__ import annotations

import contextlib
import socket

DISCOVERY_PORT = 23272
# "eQ3Max" + "*" + NUL + 10 wildcard serial chars + "I" (identify).
_REQUEST = b"eQ3Max*\x00**********I"
_RESPONSE_PREFIX = b"eQ3MaxAp"
_SERIAL_SLICE = slice(8, 18)


def find_host(cubes: list[dict[str, str]], serial: str) -> str | None:
    """Return the IP address of the discovered Cube with this serial number, if any."""
    for cube in cubes:
        if cube.get("serial") == serial:
            return cube.get("host")
    return None


def discover_cubes(timeout: float = 2.0) -> list[dict[str, str]]:
    """Broadcast a MAX! discovery request and return the cubes that answer.

    Returns a list of ``{"host": <ip>, "serial": <serial>}`` dicts (one per
    distinct responding Cube). Never raises on a network error — an empty list
    simply means nothing was found.
    """
    cubes: dict[str, str] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Binding to the discovery port catches replies that some Cubes broadcast back; if it is
        # busy, fall back to an ephemeral port (the Cube still answers the unicast source port).
        with contextlib.suppress(OSError):
            sock.bind(("", DISCOVERY_PORT))
        sock.settimeout(timeout)
        sock.sendto(_REQUEST, ("255.255.255.255", DISCOVERY_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except OSError:
                # Timeout (socket.timeout is an OSError) or any other socket
                # error ends the discovery window.
                break
            if not data.startswith(_RESPONSE_PREFIX):
                continue
            serial = data[_SERIAL_SLICE].decode("ascii", "replace")
            cubes[addr[0]] = serial
    finally:
        sock.close()
    return [{"host": host, "serial": serial} for host, serial in cubes.items()]
