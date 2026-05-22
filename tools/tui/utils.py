"""Shared helpers for the database TUI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import Any, TypeVar

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label, TextArea

from server.config import ServerConfig

T = TypeVar("T")


@dataclass(slots=True)
class BackendError:
    title: str
    detail: str


class FullTextScreen(ModalScreen[None]):
    """Modal screen for inspecting full untruncated row data."""

    def __init__(self, title: str, content: str) -> None:
        super().__init__()
        self._title = title
        self._content = content

    def compose(self) -> ComposeResult:
        with Container(id="full-text-dialog"):
            with Vertical():
                yield Label(self._title, id="full-text-title")
                yield TextArea(self._content, read_only=True, id="full-text-content")
                yield Button("Close", id="full-text-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "full-text-close":
            self.dismiss()


class FullRowDataTable(DataTable):
    """DataTable that posts a row-double-click message."""

    class RowDoubleClicked(Message):
        """Posted when a table row is double-clicked."""

        def __init__(
            self,
            data_table: "FullRowDataTable",
            cursor_row: int,
            row_key: DataTable.RowKey,
        ) -> None:
            self.data_table = data_table
            self.cursor_row = cursor_row
            self.row_key = row_key
            super().__init__()

        @property
        def control(self) -> "FullRowDataTable":
            return self.data_table

    async def _on_click(self, event: events.Click) -> None:
        await super()._on_click(event)
        if event.chain < 2:
            return
        meta = event.style.meta
        if "row" not in meta or "column" not in meta:
            return
        row_index = meta["row"]
        column_index = meta["column"]
        if row_index < 0 or column_index < 0:
            return
        if row_index >= len(self.ordered_rows):
            return
        row = self.ordered_rows[row_index]
        self.post_message(self.RowDoubleClicked(self, row_index, row.key))


async def run_sync(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def load_config() -> ServerConfig:
    return ServerConfig()


def format_error(exc: Exception) -> BackendError:
    return BackendError(title=exc.__class__.__name__, detail=str(exc))


def trunc_id(val: str, head: int = 20, tail: int = 6) -> str:
    """Shorten a long identifier for table display.

    Values short enough to fit are returned as-is.  Longer values are shown
    as ``<first head chars>…<last tail chars>`` so the displayed string is at
    most ``head + 1 + tail`` characters wide.
    """
    if len(val) <= head + 1 + tail:
        return val
    return f"{val[:head]}…{val[-tail:]}"


def format_full_row(title: str, values: dict[str, object]) -> str:
    """Format row fields for plain-text inspection."""
    lines = [title, ""]
    for key, value in values.items():
        lines.append(f"{key}:")
        lines.append(str(value) if value is not None else "")
        lines.append("")
    return "\n".join(lines).rstrip()
