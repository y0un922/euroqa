"""Bounded async retry with exponential backoff."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 2,
    retryable: tuple[type[Exception], ...] = (),
    backoff_seconds: float = 1.0,
) -> T:
    """Run *coro_factory()* up to *max_attempts* times.

    Only exceptions whose type is in *retryable* trigger a retry.
    Backoff doubles after each failed attempt (1s -> 2s -> ...).
    After exhausting attempts the last exception is re-raised.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except retryable as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "retrying",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    error=str(exc),
                    backoff_seconds=delay,
                )
                await asyncio.sleep(delay)
    # max_attempts exhausted — re-raise the last exception
    raise last_exc  # type: ignore[misc]
