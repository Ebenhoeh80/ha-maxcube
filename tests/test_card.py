"""The Lovelace card ships inside the integration and its texts stay complete (no Node needed)."""

from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "maxcube_local"
CARD = BASE / "frontend" / "maxcube-schedule-card.js"
SOURCE = CARD.read_text(encoding="utf-8")


def _language_keys(language: str) -> list[str]:
    """The keys of one language block, in file order (duplicates kept)."""
    start = SOURCE.index(f"\n  {language}: {{")
    end = SOURCE.index("\n  },", start)
    return re.findall(r"^    (\w+):", SOURCE[start:end], re.M)


def _used_keys() -> set[str]:
    return set(re.findall(r"\bT\.(\w+)", SOURCE))


def test_the_card_lives_inside_the_integration() -> None:
    assert CARD.is_file()


def test_every_text_key_is_defined_once_per_language() -> None:
    for language in ("de", "en"):
        keys = _language_keys(language)
        assert keys, language
        assert len(keys) == len(set(keys)), f"duplicate keys in {language}"


def test_both_languages_have_the_same_keys() -> None:
    assert set(_language_keys("de")) == set(_language_keys("en"))


def test_every_used_text_key_exists_in_both_languages() -> None:
    used = _used_keys()
    assert used, "no T.<key> found: the parser is out of date"
    for language in ("de", "en"):
        missing = used - set(_language_keys(language))
        assert not missing, f"{language} lacks {sorted(missing)}"


def test_the_card_registers_itself() -> None:
    assert 'customElements.define("maxcube-schedule-card"' in SOURCE
    assert "window.customCards" in SOURCE
    assert 'type: "maxcube-schedule-card"' in SOURCE


def test_user_facing_text_is_not_hard_coded() -> None:
    """German words in templates would show up in the English interface."""
    outside_translations = SOURCE[SOURCE.index("const LANG") :]
    assert not re.search(r"[äöüÄÖÜß]", outside_translations)
