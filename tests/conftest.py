"""Make the integration's pure modules importable without Home Assistant.

``custom_components/maxcube_local/__init__.py`` imports Home Assistant, which the tests do not
install. A package named ``maxcube_local`` pointing at the same folder is registered instead, so
``cube``, ``schedule`` and ``discovery`` import normally (relative imports included) while the real
``__init__`` is never run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

_FOLDER = Path(__file__).parents[1] / "custom_components" / "maxcube_local"

if "maxcube_local" not in sys.modules:
    _package = ModuleType("maxcube_local")
    _package.__path__ = [str(_FOLDER)]
    sys.modules["maxcube_local"] = _package
