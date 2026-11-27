"""Fail the build when one integration module falls below its coverage floor.

The combined ``--cov-fail-under`` only sees the average: a well-tested module can
hide an untested one. This check runs after the combined Home Assistant + logic
run in CI and applies the floor to every Python module of the integration.

Two modules are temporarily exempt with a stated reason: their missing lines are
socket error paths (discovery timeouts, a malformed library answer) that cannot
be triggered with the synthetic Cube. They stay visible in the report instead of
being silently included in the average.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MIN_COVERAGE = 95.0
EXEMPT = {
    "cube": "library socket error paths and malformed answers need hardware evidence",
    "discovery": "broadcast/connect error paths need a real network",
}

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "coverage.json"


def main() -> int:
    """Check the module percentages from ``coverage json`` and print a short verdict."""
    if not REPORT.is_file():
        print(f"missing {REPORT}: run coverage json first", file=sys.stderr)
        return 2
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    failures: list[str] = []
    # Coverage 7 writes ``files`` as a dict keyed by filename; older versions
    # wrote a list of records. Accept both so the gate is not tied to a format.
    raw_files = data["files"]
    items = (
        raw_files.items()
        if isinstance(raw_files, dict)
        else ((entry["filename"], entry) for entry in raw_files)
    )
    for filename, entry in items:
        relative = Path(filename).as_posix()
        if "/custom_components/maxcube_local/" not in relative:
            continue
        name = Path(relative).stem
        percent = float(entry["summary"]["percent_covered"])
        if name in EXEMPT:
            print(f"EXEMPT {name}: {percent:.2f}% - {EXEMPT[name]}")
            continue
        status = "ok" if percent >= MIN_COVERAGE else "FAIL"
        print(f"{status:4} {name}: {percent:.2f}%")
        if status == "FAIL":
            failures.append(f"{name} has {percent:.2f}% (need {MIN_COVERAGE:.0f}%)")
    if failures:
        print("Module coverage gate failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(f"Module coverage gate passed (>= {MIN_COVERAGE:.0f}% per module).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
