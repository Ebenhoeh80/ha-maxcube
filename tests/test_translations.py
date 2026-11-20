"""The translation files stay in step with each other."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "maxcube_local"


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def _keys(node: object, prefix: str = "") -> set[str]:
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            found |= _keys(value, f"{prefix}/{key}")
        return found
    return {prefix}


def test_english_translation_equals_strings() -> None:
    assert _load("translations/en.json") == _load("strings.json")


def test_german_translation_has_the_same_keys_as_english() -> None:
    assert _keys(_load("translations/de.json")) == _keys(_load("strings.json"))


def test_placeholders_are_the_same_in_every_language() -> None:
    import re

    def texts(node: object, prefix: str = "") -> dict[str, set[str]]:
        if isinstance(node, dict):
            out: dict[str, set[str]] = {}
            for key, value in node.items():
                out |= texts(value, f"{prefix}/{key}")
            return out
        return {prefix: set(re.findall(r"\{(\w+)\}", str(node)))}

    assert texts(_load("translations/de.json")) == texts(_load("strings.json"))
