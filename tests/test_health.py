"""Tests for the 'which device needs attention' logic."""

from __future__ import annotations

from types import SimpleNamespace as NS

from maxcube_local import health


def device(addr: str, name: str | None = "Bad", battery: int = 0) -> NS:
    return NS(rf_address=addr, name=name, battery=battery)


def test_a_healthy_device_has_no_findings() -> None:
    assert health.find_problems([device("a")], lambda _: NS(error=False)) == []


def test_unknown_error_state_is_not_a_problem() -> None:
    assert health.find_problems([device("a")], lambda _: NS(error=None)) == []


def test_low_battery_and_error_are_reported_separately() -> None:
    findings = health.find_problems([device("a", battery=1)], lambda _: NS(error=True))
    assert {f.kind for f in findings} == {health.ISSUE_BATTERY, health.ISSUE_ERROR}


def test_the_address_names_a_device_without_a_name() -> None:
    (finding,) = health.find_problems([device("abc", name=None, battery=1)], lambda _: NS(error=False))
    assert finding.name == "abc"
