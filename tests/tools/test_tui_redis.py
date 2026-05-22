import json

import pytest
from rich.console import Console

from tools.tui.tab_redis import (
    _format_backend_error,
    _format_redis_error,
    _format_redis_messages,
)
from tools.tui.utils import BackendError, format_full_row


def _render_markup(markup: str) -> None:
    console = Console(record=True, width=100)
    console.print(markup)


def test_redis_messages_escape_markup_like_answer_content() -> None:
    markup = _format_redis_messages(
        "context:1001_[session]",
        [
            json.dumps(
                {
                    "role": "assistant",
                    "content": "### 直接结论\nThis contains [/], [bold red], and [link=x]tags[/link].",
                    "timestamp": "2026-05-22T02:54:29.878647Z",
                }
            )
        ],
    )

    _render_markup(markup)
    assert r"\[/]" in markup
    assert r"\[bold red]" in markup
    assert r"\[session]" in markup


def test_redis_error_escapes_markup_like_exception_text() -> None:
    markup = _format_redis_error(ValueError("auto closing tag ('[/]') has nothing to close"))

    _render_markup(markup)
    assert r"\[/]" in markup


def test_backend_error_escapes_markup_like_detail_text() -> None:
    markup = _format_backend_error(BackendError("Redis[/]", "connection failed [bold]"))

    _render_markup(markup)
    assert r"Redis\[/]" in markup
    assert r"\[bold]" in markup


def test_format_full_row_keeps_complete_values() -> None:
    full_id = "1001_7eb55bdc8782461caca6eadd03d75aea"

    text = format_full_row("Redis session", {"conversation_id": full_id})

    assert full_id in text
    assert "…" not in text


@pytest.mark.asyncio
async def test_redis_load_messages_error_notification_disables_markup() -> None:
    class FailingRedis:
        async def lrange(self, *_args):
            raise ValueError("auto closing tag ('[/]') has nothing to close")

    class Detail:
        def __init__(self) -> None:
            self.content = ""

        def update(self, content: str) -> None:
            self.content = content

    class Pane:
        _redis = FailingRedis()

        def __init__(self) -> None:
            self.detail = Detail()
            self.notifications = []

        def query_one(self, *_args):
            return self.detail

        def notify(self, *args, **kwargs) -> None:
            self.notifications.append((args, kwargs))

    from tools.tui.tab_redis import RedisPane

    pane = Pane()
    await RedisPane._load_messages(pane, "cid[/]")

    assert pane.notifications[0][1]["markup"] is False
    assert r"\[/]" in pane.detail.content


def test_redis_row_double_click_opens_full_session_text() -> None:
    class App:
        def __init__(self) -> None:
            self.screens = []

        def push_screen(self, screen) -> None:
            self.screens.append(screen)

    class Event:
        data_table = type("Table", (), {"id": "redis-table"})()
        row_key = type("RowKey", (), {"value": "full-conversation-id"})()

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    class Pane:
        def __init__(self) -> None:
            self._session_rows = {
                "full-conversation-id": {
                    "conversation_id": "full-conversation-id",
                    "title": "A very long Redis history title",
                }
            }
            self.app = App()

    from tools.tui.tab_redis import RedisPane

    pane = Pane()
    event = Event()
    RedisPane.on_full_row_data_table_row_double_clicked(pane, event)

    assert event.stopped is True
    assert "full-conversation-id" in pane.app.screens[0]._content
