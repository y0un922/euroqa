"""Unit tests for the async circuit breaker."""

from __future__ import annotations

import pytest

from server.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError


class _ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failure_threshold():
    clock = _ManualClock()
    breaker = AsyncCircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=30.0,
        clock=clock,
    )

    async def fail():
        raise RuntimeError("downstream failed")

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == "closed"

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == "open"

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(fail)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_success_closes():
    clock = _ManualClock()
    breaker = AsyncCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=30.0,
        clock=clock,
    )

    async def fail():
        raise RuntimeError("downstream failed")

    async def succeed():
        return "ok"

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == "open"

    clock.advance(30.0)
    assert breaker.state == "half_open"
    assert await breaker.call(succeed) == "ok"
    assert breaker.state == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens():
    clock = _ManualClock()
    breaker = AsyncCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=30.0,
        clock=clock,
    )

    async def fail():
        raise RuntimeError("downstream failed")

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    clock.advance(30.0)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == "open"

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(fail)
