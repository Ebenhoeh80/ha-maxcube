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


def test_dynamic_values_are_escaped_before_they_reach_innerhtml() -> None:
    assert "const esc = " in SOURCE
    for risky in ("${p.until}", "${errs.join", "${s.text}"):
        assert risky not in SOURCE, f"{risky} is written to HTML without esc()"
    # names are free text from Home Assistant: every template use goes through esc()
    assert SOURCE.count("esc(this._name(") >= 3


def test_no_text_key_is_unused() -> None:
    unused = set(_language_keys("en")) - _used_keys() - {"dayShort", "dayLong"}
    assert not unused, f"unused keys {sorted(unused)}"


def test_sending_is_limited_to_changed_days_and_asks_for_many_telegrams() -> None:
    assert "DAYS;" not in SOURCE.replace("const DAYS", ""), "must not fall back to all days"
    assert "this._changedDays.size > 0\n      ? [...this._changedDays]" not in SOURCE
    assert "T.nothingToSend" in SOURCE
    assert "T.confirmSend(" in SOURCE
    assert "RADIO_PERCENT_PER_TELEGRAM" in SOURCE
    assert "sent_not_confirmed" in SOURCE
    assert '"failed"' in SOURCE


def test_the_card_reads_the_entity_keyed_service_response() -> None:
    """An entity service answers {entity_id: {"result": {day: state}}} (return_response)."""
    assert "return_response: true" in SOURCE
    assert "res?.response?.[entity]" in SOURCE
    assert "body.result?.[day]" in SOURCE


def test_wall_thermostats_are_hidden_because_the_service_refuses_them() -> None:
    assert "schedule_radiator_only" in (BASE / "climate.py").read_text(encoding="utf-8")
    assert '"Wall Thermostat"' in (BASE / "const.py").read_text(encoding="utf-8")
    assert "_isRadiator(" in SOURCE
    assert "/wall/i" in SOURCE
