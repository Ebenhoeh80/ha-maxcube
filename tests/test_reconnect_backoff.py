"""Regression tests for observing and backing off a blocked Cube port (P2-3)."""

from __future__ import annotations

from maxcube_local import reconnect


def test_the_first_failure_allows_a_short_retry() -> None:
    backoff = reconnect.ConnectBackoff()
    assert backoff.should_try(100.0) is True
    backoff.record_failure(100.0)
    assert backoff.should_try(100.0) is False
    assert backoff.should_try(104.9) is False
    assert backoff.should_try(105.0) is True


def test_repeated_failures_grow_only_up_to_a_cap() -> None:
    backoff = reconnect.ConnectBackoff()
    now = 0.0
    expected = []
    for _ in range(8):
        backoff.record_failure(now)
        expected.append(backoff.blocked_until - now)
        now += backoff.blocked_until - now + 1
    assert expected == [5, 10, 20, 40, 60, 60, 60, 60]


def test_a_success_clears_the_backoff() -> None:
    backoff = reconnect.ConnectBackoff()
    backoff.record_failure(100.0)
    assert backoff.should_try(100.0) is False
    backoff.record_success()
    assert backoff.should_try(100.0) is True
    assert backoff.blocked_until is None
    assert backoff.failures == 0


def test_the_backoff_never_blocks_longer_than_one_poll_interval() -> None:
    """A 60 s poll must not be delayed by more than one interval (P2 observation)."""
    backoff = reconnect.ConnectBackoff(max_delay=60.0)
    for _ in range(20):
        backoff.record_failure(0.0)
    assert backoff.blocked_until == 60.0
