"""Release consistency gates: one version, complete translations, matching docs (P1-4)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
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


def test_releasing_docs_exist_in_both_languages() -> None:
    english = _read(ROOT / "RELEASING.md")
    german = _read(ROOT / "RELEASING.de.md")
    assert "[Deutsch](RELEASING.de.md)" in english
    assert "[English](RELEASING.md)" in german
    # Both languages must state that both changelogs are part of a release.
    assert "CHANGELOG.en.md" in english
    assert "CHANGELOG.en.md" in german


def test_release_notes_script_emits_both_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    version = json.loads(_read(INTEGRATION / "manifest.json"))["version"]
    monkeypatch.setenv("GITHUB_REF_NAME", f"v{version}")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "release_notes.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "## Deutsch" in result.stdout
    assert "## English" in result.stdout
    assert f"## [{version}]" in result.stdout


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


def test_no_sensor_claims_a_cube_queue_length() -> None:
    """The S message has no queue field; a translated entity must not claim one."""
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads(_read(INTEGRATION / name))
        assert "queued_telegrams" not in data["entity"]["sensor"], name
