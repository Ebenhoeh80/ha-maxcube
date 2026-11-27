"""Release consistency gates: one version, complete translations, matching docs (P1-4)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "maxcube_local"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _version_from_changelog(path: Path) -> str | None:
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", _read(path), re.MULTILINE)
    return match.group(1) if match else None


def test_manifest_and_both_changelogs_name_the_same_version() -> None:
    manifest = json.loads(_read(INTEGRATION / "manifest.json"))
    # CHANGELOG.md is the German original, CHANGELOG.en.md its English translation.
    assert _version_from_changelog(ROOT / "CHANGELOG.md") == manifest["version"]
    assert _version_from_changelog(ROOT / "CHANGELOG.en.md") == manifest["version"]


def test_both_changelogs_have_an_unreleased_section() -> None:
    for name in ("CHANGELOG.md", "CHANGELOG.en.md"):
        assert "## [Unreleased]" in _read(ROOT / name), name


def test_readme_translations_link_each_other() -> None:
    english = _read(ROOT / "README.md")
    german = _read(ROOT / "README.de.md")
    assert "[Deutsch](README.de.md)" in english
    assert "[English](README.md)" in german


def test_engineering_and_runbook_docs_exist_in_both_languages() -> None:
    for path in ("docs/ENGINEERING.md", "docs/de/ENGINEERING.md",
                 "docs/IDENTITY.md", "docs/de/IDENTITY.md",
                 "docs/RUNBOOK.md", "docs/de/RUNBOOK.md"):
        assert (ROOT / path).is_file(), path


def test_each_readme_links_its_language_runbook() -> None:
    assert "docs/RUNBOOK.md" in _read(ROOT / "README.md")
    assert "docs/de/RUNBOOK.md" in _read(ROOT / "README.de.md")


def test_the_admin_action_has_an_icon() -> None:
    icons = json.loads(_read(INTEGRATION / "icons.json"))
    assert icons["services"]["reboot"] == "mdi:restart"


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/de.json"])
def test_translation_files_are_valid_json(name: str) -> None:
    json.loads(_read(INTEGRATION / name))


def test_all_language_files_have_the_same_sensor_keys() -> None:
    def sensors(name: str) -> set[str]:
        data = json.loads(_read(INTEGRATION / name))
        return set(data["entity"]["sensor"])

    english = sensors("translations/en.json")
    german = sensors("translations/de.json")
    assert english == german
    assert english == sensors("strings.json")


def test_the_queued_telegram_sensor_is_translated_everywhere() -> None:
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads(_read(INTEGRATION / name))
        assert "queued_telegrams" in data["entity"]["sensor"], name
