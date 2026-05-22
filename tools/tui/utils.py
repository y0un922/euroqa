"""Shared helpers for the database TUI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import Any, TypeVar

from server.config import ServerConfig

T = TypeVar("T")


@dataclass(slots=True)
class BackendError:
    title: str
    detail: str


async def run_sync(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def load_config() -> ServerConfig:
    return ServerConfig()


def format_error(exc: Exception) -> BackendError:
    return BackendError(title=exc.__class__.__name__, detail=str(exc))
