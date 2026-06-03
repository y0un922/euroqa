"""Tests for backend logging configuration."""

from __future__ import annotations

from datetime import datetime

from server.logging_config import add_shanghai_timestamp


def test_add_shanghai_timestamp_uses_china_timezone() -> None:
    event = add_shanghai_timestamp(None, "info", {})

    timestamp = event["timestamp"]
    parsed = datetime.fromisoformat(timestamp)

    assert timestamp.endswith("+08:00")
    assert parsed.utcoffset() is not None
    assert int(parsed.utcoffset().total_seconds()) == 8 * 60 * 60
