"""Shared AsyncOpenAI client cache for request-path LLM calls."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI


@dataclass(frozen=True)
class _TimeoutKey:
    timeout: float | None
    connect: float | None
    read: float | None
    write: float | None
    pool: float | None


_CLIENTS: dict[tuple[str, str, _TimeoutKey, int], AsyncOpenAI] = {}
_CLIENT_LOCK = asyncio.Lock()


def _timeout_key(timeout: httpx.Timeout | float | None) -> _TimeoutKey:
    if isinstance(timeout, httpx.Timeout):
        return _TimeoutKey(
            timeout=None,
            connect=timeout.connect,
            read=timeout.read,
            write=timeout.write,
            pool=timeout.pool,
        )
    return _TimeoutKey(
        timeout=float(timeout) if timeout is not None else None,
        connect=None,
        read=None,
        write=None,
        pool=None,
    )


async def get_async_openai_client(
    *,
    api_key: str,
    base_url: str,
    timeout: httpx.Timeout | float | None = None,
    client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client for one endpoint/timeout tuple."""
    key = (api_key, base_url, _timeout_key(timeout), id(client_factory))
    client = _CLIENTS.get(key)
    if client is not None:
        return client

    async with _CLIENT_LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
            if timeout is not None:
                kwargs["timeout"] = timeout
            client = client_factory(**kwargs)
            _CLIENTS[key] = client
        return client


async def close_async_openai_clients() -> None:
    """Close and clear all cached AsyncOpenAI clients."""
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    for client in clients:
        close = getattr(client, "close", None)
        if close is None:
            close = getattr(client, "aclose", None)
        if close is None:
            continue
        result = close()
        if result is not None:
            await result
