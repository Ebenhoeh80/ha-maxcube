"""Backoff for a Cube whose TCP port is blocked (pure logic, no Home Assistant).

A pairing or metadata session in the MAX! app can leave port 62910 refusing
connections while ping and UDP discovery still work.  The cause is not proven,
so this module only observes the failure and slows down retries: it does not
claim a fix.  A successful connection clears the state immediately.
"""

from __future__ import annotations

_INITIAL_DELAY = 5.0
_MULTIPLIER = 2.0
_DEFAULT_MAX_DELAY = 60.0


class ConnectBackoff:
    """Exponential backoff with a cap, driven by an injected clock."""

    def __init__(self, max_delay: float = _DEFAULT_MAX_DELAY) -> None:
        """Start without any recorded failure."""
        self.max_delay = max_delay
        self.failures = 0
        self.blocked_until: float | None = None

    def should_try(self, now: float) -> bool:
        """Return True when a new connection attempt is allowed now."""
        return self.blocked_until is None or now >= self.blocked_until

    def record_failure(self, now: float) -> None:
        """Slow down the next attempt after a refused connection."""
        self.failures += 1
        delay = min(
            _INITIAL_DELAY * _MULTIPLIER ** (self.failures - 1),
            self.max_delay,
        )
        self.blocked_until = now + delay

    def record_success(self) -> None:
        """Clear the backoff after a successful connection."""
        self.failures = 0
        self.blocked_until = None

    def as_dict(self) -> dict[str, int | float | None]:
        """Return a diagnostics-friendly copy."""
        return {
            "failures": self.failures,
            "blocked_until": self.blocked_until,
        }
