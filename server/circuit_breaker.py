"""Small async circuit breaker for protecting flaky downstream calls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Raised when a downstream call is skipped because the breaker is open."""


class AsyncCircuitBreaker:
    """Process-local async circuit breaker with closed/open/half-open states."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._recovery_timeout_seconds = max(0.0, recovery_timeout_seconds)
        self._clock = clock
        self._lock = asyncio.Lock()
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    @property
    def state(self) -> str:
        """Return the externally visible breaker state."""
        if self._opened_at is None:
            return "closed"
        if self._ready_for_probe():
            return "half_open"
        return "open"

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Run *func* unless the circuit is open."""
        await self._before_call()
        try:
            result = await func()
        except Exception:
            await self.record_failure()
            raise
        await self.record_success()
        return result

    async def record_success(self) -> None:
        """Close the breaker after a successful protected call."""
        async with self._lock:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_in_flight = False

    async def record_failure(self) -> None:
        """Record a failure and open the breaker after the configured threshold."""
        async with self._lock:
            self._half_open_in_flight = False
            if self._opened_at is not None:
                self._opened_at = self._clock()
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._opened_at = self._clock()

    async def _before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            if not self._ready_for_probe():
                raise CircuitBreakerOpenError()
            if self._half_open_in_flight:
                raise CircuitBreakerOpenError()
            self._half_open_in_flight = True

    def _ready_for_probe(self) -> bool:
        return (
            self._opened_at is not None
            and self._clock() - self._opened_at >= self._recovery_timeout_seconds
        )
