"""Structlog production configuration."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog

_LOG_TIMEZONE = ZoneInfo("Asia/Shanghai")


def add_shanghai_timestamp(
    _logger: object,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Add an ISO timestamp in China Standard Time."""
    event_dict["timestamp"] = datetime.now(_LOG_TIMEZONE).isoformat()
    return event_dict


def configure_logging(*, json_mode: bool = False) -> None:
    """Set up structlog with shared processors and an appropriate renderer.

    Args:
        json_mode: When ``True`` use :class:`structlog.processors.JSONRenderer`
            (for production / machine-readable logs).  When ``False`` use
            :class:`structlog.dev.ConsoleRenderer` (for local development).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        add_shanghai_timestamp,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_mode:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(
            ensure_ascii=False,
        )
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
