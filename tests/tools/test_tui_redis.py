import json
import asyncio

from rich.console import Console

from tools.tui.tab_redis import (
    _format_backend_error,
    _format_full_redis_messages,
    _format_redis_error,
    _format_redis_messages,
    _format_redis_timestamp,
    _sort_redis_sessions,
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


def test_format_redis_timestamp_displays_as_shanghai_time() -> None:
    assert _format_redis_timestamp("2026-05-25T03:54:29Z") == "2026-05-25 11:54:29"


def test_format_full_redis_messages_keeps_complete_content() -> None:
    content = "完整回答" * 200

    text = _format_full_redis_messages(
        [
            json.dumps(
                {
                    "role": "assistant",
                    "timestamp": "2026-05-22T02:54:29Z",
                    "content": content,
                }
            )
        ]
    )

    assert content in text
    assert "assistant" in text
    assert "2026-05-22 10:54:29" in text


def test_sort_redis_sessions_supports_updated_title_and_message_count() -> None:
    sessions = [
        ("b", {"title": "Beta", "updatedAt": "2026-05-20", "createdAt": "2026-05-18"}, 2),
        ("a", {"title": "Alpha", "updatedAt": "2026-05-21", "createdAt": "2026-05-19"}, 5),
    ]

    assert [cid for cid, _, _ in _sort_redis_sessions(sessions, "updated_desc")] == ["a", "b"]
    assert [cid for cid, _, _ in _sort_redis_sessions(sessions, "updated_asc")] == ["b", "a"]
    assert [cid for cid, _, _ in _sort_redis_sessions(sessions, "title_asc")] == ["a", "b"]
    assert [cid for cid, _, _ in _sort_redis_sessions(sessions, "messages_desc")] == ["a", "b"]


def test_redis_load_messages_error_notification_disables_markup() -> None:
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
    asyncio.run(RedisPane._load_messages(pane, "cid[/]"))

    assert pane.notifications[0][1]["markup"] is False
    assert r"\[/]" in pane.detail.content


def test_redis_row_double_click_opens_full_session_text_with_messages() -> None:
    class Redis:
        async def lrange(self, key, *_args):
            assert key == "context:full-conversation-id"
            return [
                json.dumps(
                    {
                        "role": "user",
                        "timestamp": "2026-05-22T02:00:00Z",
                        "content": "full user question",
                    }
                ),
                json.dumps(
                    {
                        "role": "assistant",
                        "timestamp": "2026-05-22T02:01:00Z",
                        "content": "full assistant answer",
                    }
                ),
            ]

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
            self._redis = Redis()
            self._session_rows = {
                "full-conversation-id": {
                    "conversation_id": "full-conversation-id",
                    "title": "A very long Redis history title",
                    "message_count": 2,
                }
            }
            self.app = App()

    from tools.tui.tab_redis import RedisPane

    pane = Pane()
    event = Event()
    asyncio.run(RedisPane.on_full_row_data_table_row_double_clicked(pane, event))

    assert event.stopped is True
    content = pane.app.screens[0]._content
    assert "full-conversation-id" in content
    assert "full user question" in content
    assert "full assistant answer" in content
