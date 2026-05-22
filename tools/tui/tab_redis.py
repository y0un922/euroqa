"""Redis tab: list sessions, view message history, delete sessions."""

from __future__ import annotations

import json

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.widget import Widget
from textual import work

from tools.tui.utils import (
    BackendError,
    FullRowDataTable,
    FullTextScreen,
    format_error,
    format_full_row,
    trunc_id,
)
from server.config import ServerConfig


def _format_redis_messages(redis_key: str, raw_items: list[object]) -> str:
    """Build Rich markup for Redis message previews with dynamic text escaped."""
    lines: list[str] = [
        f"[dim]Key: {escape(redis_key)}  │  Messages found: {len(raw_items)}[/]\n"
    ]
    for msg in raw_items:
        try:
            payload = json.loads(msg) if isinstance(msg, str) else msg
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        role = str(payload.get("role") or "?")
        content = str(payload.get("content") or "")[:300]
        ts = str(payload.get("timestamp") or "")[:19]
        role_color = "cyan" if role == "user" else "green"
        lines.append(
            f"[bold {role_color}]{escape(role)}[/] [dim]{escape(ts)}[/]\n"
            f"{escape(content)}\n"
        )
    if len(raw_items) == 0:
        lines.append("[dim]No messages found under this key.[/]")
    return "\n".join(lines)


def _format_redis_error(exc: Exception) -> str:
    """Build Rich markup for Redis load errors with exception text escaped."""
    return f"[bold red]Error:[/] {escape(str(exc))}"


def _format_backend_error(error: BackendError) -> str:
    """Build Rich markup for Redis connection errors with detail text escaped."""
    return f"[bold red]✗[/] {escape(error.title)}: {escape(error.detail)}"


class RedisPane(Widget):
    DEFAULT_CSS = """
    RedisPane { height: 1fr; }
    """

    def __init__(self, config: ServerConfig) -> None:
        super().__init__()
        self._config = config
        self._redis = None
        self._error: BackendError | None = None
        self._session_rows: dict[str, dict[str, object]] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Connecting to Redis...", classes="stats-bar", id="redis-stats")
            with Horizontal(classes="toolbar"):
                yield Button("Refresh", id="redis-refresh", variant="primary")
                yield Button("Delete Session", id="redis-delete", variant="error")
            yield FullRowDataTable(id="redis-table")
            yield Static("Select a session to view messages", classes="detail-panel-tall", id="redis-messages")

    async def on_mount(self) -> None:
        table = self.query_one("#redis-table", DataTable)
        table.add_column("conversation_id", width=30)
        table.add_column("title", width=40)
        table.add_column("created", width=20)
        table.add_column("updated", width=20)
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
        stats.update(_format_backend_error(self._error))

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
        self._session_rows.clear()
        for cid, meta in sessions:
            title = meta.get("title", "—")
            self._session_rows[cid] = {
                "conversation_id": cid,
                "title": title,
                "createdAt": meta.get("createdAt", "—"),
                "updatedAt": meta.get("updatedAt", "—"),
                "raw_meta": json.dumps(meta, indent=2, ensure_ascii=False),
            }
            table.add_row(
                trunc_id(cid),
                trunc_id(title, head=36, tail=0) if len(title) > 37 else title,
                meta.get("createdAt", "—")[:19],
                meta.get("updatedAt", "—")[:19],
                key=cid,
            )
        stats = self.query_one("#redis-stats", Static)
        stats.update(
            f"[bold green]✓[/] Redis: connected  "
            f"│  Sessions: [bold]{len(sessions):,}[/]"
        )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        cid = str(event.row_key.value)
        await self._load_messages(cid)

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        cid = str(event.row_key.value)
        await self._load_messages(cid)

    def on_full_row_data_table_row_double_clicked(
        self,
        event: FullRowDataTable.RowDoubleClicked,
    ) -> None:
        if event.data_table.id != "redis-table":
            return
        cid = str(event.row_key.value)
        row = self._session_rows.get(cid)
        if not row:
            return
        event.stop()
        self.app.push_screen(
            FullTextScreen(
                "Redis session",
                format_full_row("Redis session", row),
            )
        )

    async def _load_messages(self, cid: str) -> None:
        if not self._redis:
            return
        redis_key = f"context:{cid}"
        try:
            raw_items = await self._redis.lrange(redis_key, 0, -1)
            detail = self.query_one("#redis-messages", Static)
            detail.update(_format_redis_messages(redis_key, raw_items))
        except Exception as exc:
            self.notify(
                f"Error loading messages: {exc}",
                severity="error",
                markup=False,
            )
            detail = self.query_one("#redis-messages", Static)
            detail.update(_format_redis_error(exc))

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
        # Retrieve the full cid from the row key at the current cursor position.
        row_keys = list(table.rows.keys())
        if table.cursor_row >= len(row_keys):
            return
        cid = str(row_keys[table.cursor_row].value)
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
            self.notify(f"Deleted session {cid}", severity="information", markup=False)
        except Exception as exc:
            self.notify(f"Error: {exc}", severity="error", markup=False)
