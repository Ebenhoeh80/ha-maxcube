"""Print bilingual release notes for the tag being released.

The shared release workflow uses the German changelog section as the GitHub
release body. Public release notes must be available in German *and* English,
so the release workflow calls this script to replace the body with both
language sections before publishing is finished.

The version comes from the tag (``vX.Y.Z``); the two changelog sections must
exist. A missing section is a hard error rather than a silently incomplete
translation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def section(path: Path, version: str) -> str:
    """Return the ``[version]`` section of a Keep-a-Changelog file."""
    text = path.read_text(encoding="utf-8")
    heading = f"## [{version}]"
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"{path.name} has no {heading} section")
    end = text.find("\n## [", start + len(heading))
    return text[start : end if end > 0 else len(text)].strip()


def main() -> int:
    """Write the combined notes to stdout."""
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if not tag.startswith("v"):
        print(f"expected a version tag in GITHUB_REF_NAME, got {tag!r}", file=sys.stderr)
        return 2
    version = tag[1:]
    try:
        german = section(ROOT / "CHANGELOG.md", version)
        english = section(ROOT / "CHANGELOG.en.md", version)
    except ValueError as err:
        print(err, file=sys.stderr)
        return 2
    print(f"## Deutsch\n\n{german}\n\n---\n\n## English\n\n{english}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
