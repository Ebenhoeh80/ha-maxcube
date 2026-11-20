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


def test_the_radio_hint_needs_a_sustained_high_value() -> None:
    watch = health.DutyCycleWatch(high=90, low=80, sustain=600)
    assert not watch.update(95, 0)
    assert not watch.update(96, 599)
    assert watch.update(92, 600)


def test_a_short_peak_does_not_count() -> None:
    watch = health.DutyCycleWatch(high=90, low=80, sustain=600)
    watch.update(95, 0)
    assert not watch.update(50, 300)  # dropped: the clock starts again
    assert not watch.update(95, 400)
    assert not watch.update(95, 900)  # only 500 s since the new start
    assert watch.update(95, 1000)


def test_the_hint_stays_until_the_value_is_below_the_lower_threshold() -> None:
    watch = health.DutyCycleWatch(high=90, low=80, sustain=0)
    assert watch.update(90, 0)
    assert watch.update(85, 10)  # between the thresholds: unchanged
    assert not watch.update(79, 20)
    assert not watch.update(85, 30)  # not high again yet


def test_an_unknown_value_changes_nothing() -> None:
    watch = health.DutyCycleWatch(high=90, low=80, sustain=0)
    assert not watch.update(None, 0)
    watch.update(95, 1)
    assert watch.update(None, 2)
