"""Make the integration's pure modules importable without Home Assistant.

``custom_components/maxcube_local/__init__.py`` imports Home Assistant, which the tests do not
install. A package named ``maxcube_local`` pointing at the same folder is registered instead, so
``cube``, ``schedule`` and ``discovery`` import normally (relative imports included) while the real
``__init__`` is never run.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

try:
    import pytest_socket
except ImportError:  # the plain job has no socket guard; the Home Assistant job has one
    pytest_socket = None

_FOLDER = Path(__file__).parents[1] / "custom_components" / "maxcube_local"

if "maxcube_local" not in sys.modules:
    _package = ModuleType("maxcube_local")
    _package.__path__ = [str(_FOLDER)]
    sys.modules["maxcube_local"] = _package


@pytest.fixture(autouse=True)
def _allow_loopback_only() -> Iterator[None]:
    """Open loopback for the fake Cube where pytest-socket blocks sockets, then block again.

    The Home Assistant plugin (pytest-homeassistant-custom-component) blocks every socket per test.
    Only 127.0.0.1 is allowed here, and the block is restored afterwards. Without the plugin there
    is no guard and nothing to do.
    """
    if pytest_socket is None:
        yield
        return
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1"])
    yield
    pytest_socket.disable_socket(allow_unix_socket=True)
