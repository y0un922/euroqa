"""Redis tab: list sessions, view message history, delete sessions."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.widget import Widget
from textual import work

from tools.tui.utils import format_error, BackendError
from server.config import ServerConfig


class RedisPane(Widget):
    DEFAULT_CSS = """
    RedisPane { height: 1fr; }
    """

    def __init__(self, config: ServerConfig) -> None:
        super().__init__()
        self._config = config
        self._redis = None
        self._error: BackendError | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Connecting to Redis...", classes="stats-bar", id="redis-stats")
            with Horizontal(classes="toolbar"):
                yield Button("Refresh", id="redis-refresh", variant="primary")
                yield Button("Delete Session", id="redis-delete", variant="error")
            yield DataTable(id="redis-table")
            yield Static("Select a session to view messages", classes="detail-panel-tall", id="redis-messages")

    async def on_mount(self) -> None:
        table = self.query_one("#redis-table", DataTable)
        table.add_columns("conversation_id", "title", "created", "updated")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._connect_and_load()

    @work
    async def _connect_and_load(self) -> None:
        try:
            if not self._config.redis_url:
                self._error = BackendError("Not Configured", "REDIS_URL is not set in .env")
                self._show_error()
                return
            from redis import asyncio as aioredis
            self._redis = aioredis.from_url(self._config.redis_url, decode_responses=True)
            await self._redis.ping()
            await self._load_sessions()
        except Exception as exc:
            self._error = format_error(exc)
            self._show_error()

    def _show_error(self) -> None:
        stats = self.query_one("#redis-stats", Static)
        stats.update(f"[bold red]✗[/] {self._error.title}: {self._error.detail}")

    async def _load_sessions(self) -> None:
        sessions: list[tuple[str, dict]] = []
        async for key in self._redis.scan_iter(match="user:*:sessions"):
            all_entries = await self._redis.hgetall(key)
            for cid, raw_meta in all_entries.items():
                try:
                    meta = json.loads(raw_meta) if isinstance(raw_meta, str) else {}
                except json.JSONDecodeError:
                    meta = {}
                sessions.append((cid, meta))

        table = self.query_one("#redis-table", DataTable)
        table.clear()
        for cid, meta in sessions:
            table.add_row(
                cid,
                meta.get("title", "—"),
                meta.get("createdAt", "—")[:19],
                meta.get("updatedAt", "—")[:19],
                key=cid,
            )
        stats = self.query_one("#redis-stats", Static)
        stats.update(
            f"[bold green]✓[/] Redis: connected  "
            f"│  Sessions: [bold]{len(sessions):,}[/]"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        cid = str(event.row_key.value)
        self._load_messages(cid)

    @work
    async def _load_messages(self, cid: str) -> None:
        if not self._redis:
            return
        try:
            raw_items = await self._redis.lrange(f"context:{cid}", 0, -1)
            lines: list[str] = []
            for msg in raw_items:
                try:
                    payload = json.loads(msg) if isinstance(msg, str) else msg
                except json.JSONDecodeError:
                    continue
                role = payload.get("role", "?")
                content = payload.get("content", "")[:300]
                ts = payload.get("timestamp", "")[:19]
                role_color = "cyan" if role == "user" else "green"
                lines.append(f"[bold {role_color}]{role}[/] [dim]{ts}[/]\n{content}\n")
            text = "\n".join(lines) if lines else "[dim]No messages in this session[/]"
            detail = self.query_one("#redis-messages", Static)
            detail.update(text)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "redis-refresh":
            self._connect_and_load()
        elif btn_id == "redis-delete":
            await self._delete_session()

    async def _delete_session(self) -> None:
        table = self.query_one("#redis-table", DataTable)
        if table.cursor_row is None:
            return
        row_data = table.get_row_at(table.cursor_row)
        cid = row_data[0] if row_data else None
        if not cid:
            return

        from tools.tui.tab_milvus import ConfirmScreen
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Delete session '{cid}' and all its messages?")
        )
        if not confirmed:
            return

        try:
            await self._redis.delete(f"context:{cid}")
            user_id, sep, _ = cid.partition("_")
            if sep and user_id:
                await self._redis.hdel(f"user:{user_id}:sessions", cid)
            await self._load_sessions()
            self.notify(f"Deleted session {cid}", severity="information")
        except Exception as exc:
            self.notify(f"Error: {exc}", severity="error")
