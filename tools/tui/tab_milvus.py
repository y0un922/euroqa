"""Milvus tab: browse chunks, search by chunk_id, vector similarity search, delete."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static
from textual.widget import Widget
from textual.screen import ModalScreen
from textual.containers import Container
from textual import work

from tools.tui.utils import format_error, BackendError
from server.config import ServerConfig


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Label(self._message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, Delete", id="confirm-yes", variant="error")
                yield Button("Cancel", id="confirm-no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class MilvusPane(Widget):
    DEFAULT_CSS = """
    MilvusPane { height: 1fr; }
    """

    def __init__(self, config: ServerConfig) -> None:
        super().__init__()
        self._config = config
        self._collection = None
        self._error: BackendError | None = None
        self._page_offset = 0
        self._page_size = 50

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Connecting to Milvus...", classes="stats-bar", id="milvus-stats")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="chunk_id or text for vector search...", id="milvus-search")
                yield Button("Search ID", id="milvus-search-id", variant="primary")
                yield Button("Vector Search", id="milvus-vec-search", variant="success")
                yield Button("Refresh", id="milvus-refresh", variant="default")
                yield Button("Delete", id="milvus-delete", variant="error")
            yield DataTable(id="milvus-table")
            with Horizontal(classes="page-bar"):
                yield Button("← Prev", id="milvus-prev")
                yield Static("", id="milvus-page-info")
                yield Button("Next →", id="milvus-next")

    async def on_mount(self) -> None:
        table = self.query_one("#milvus-table", DataTable)
        table.add_columns("chunk_id", "source", "element_type")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._connect_and_load()

    @work(thread=True)
    def _connect_and_load(self) -> None:
        try:
            from pymilvus import connections, Collection, utility
            connections.connect(host=self._config.milvus_host, port=self._config.milvus_port)
            if not utility.has_collection(self._config.milvus_collection):
                self._error = BackendError("No Collection", f"'{self._config.milvus_collection}' not found")
                self.app.call_from_thread(self._show_error)
                return
            self._collection = Collection(self._config.milvus_collection)
            self._collection.load()
            self.app.call_from_thread(self._update_stats)
            self.app.call_from_thread(self._load_page)
        except Exception as exc:
            self._error = format_error(exc)
            self.app.call_from_thread(self._show_error)

    def _show_error(self) -> None:
        stats = self.query_one("#milvus-stats", Static)
        stats.update(f"[bold red]✗[/] {self._error.title}: {self._error.detail}")

    def _update_stats(self) -> None:
        stats = self.query_one("#milvus-stats", Static)
        num = self._collection.num_entities
        stats.update(
            f"[bold green]✓[/] Collection: [bold]{self._config.milvus_collection}[/]  "
            f"│  Entities: [bold]{num:,}[/]"
        )

    def _load_page(self) -> None:
        if not self._collection:
            return
        table = self.query_one("#milvus-table", DataTable)
        table.clear()
        try:
            results = self._collection.query(
                expr="",
                output_fields=["chunk_id", "source", "element_type"],
                offset=self._page_offset,
                limit=self._page_size,
            )
            for row in results:
                table.add_row(
                    row.get("chunk_id", ""),
                    row.get("source", ""),
                    row.get("element_type", ""),
                    key=row.get("chunk_id", ""),
                )
            page_info = self.query_one("#milvus-page-info", Static)
            end = self._page_offset + len(results)
            page_info.update(f"Rows {self._page_offset + 1}–{end}")
        except Exception as exc:
            self._error = format_error(exc)
            self._show_error()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "milvus-refresh":
            self._page_offset = 0
            self._connect_and_load()
        elif btn_id == "milvus-next":
            self._page_offset += self._page_size
            self._load_page_worker()
        elif btn_id == "milvus-prev":
            self._page_offset = max(0, self._page_offset - self._page_size)
            self._load_page_worker()
        elif btn_id == "milvus-search-id":
            self._search_by_id()
        elif btn_id == "milvus-vec-search":
            self._vector_search()
        elif btn_id == "milvus-delete":
            await self._delete_selected()

    @work(thread=True)
    def _load_page_worker(self) -> None:
        self.app.call_from_thread(self._load_page)

    @work(thread=True)
    def _search_by_id(self) -> None:
        query = self.app.call_from_thread(lambda: self.query_one("#milvus-search", Input).value.strip())
        if not query or not self._collection:
            return
        try:
            results = self._collection.query(
                expr=f'chunk_id == "{query}"',
                output_fields=["chunk_id", "source", "element_type"],
            )

            def update():
                table = self.query_one("#milvus-table", DataTable)
                table.clear()
                for row in results:
                    table.add_row(
                        row.get("chunk_id", ""),
                        row.get("source", ""),
                        row.get("element_type", ""),
                        key=row.get("chunk_id", ""),
                    )

            self.app.call_from_thread(update)
        except Exception as exc:
            self._error = format_error(exc)
            self.app.call_from_thread(self._show_error)

    @work(thread=True)
    def _vector_search(self) -> None:
        query = self.app.call_from_thread(lambda: self.query_one("#milvus-search", Input).value.strip())
        if not query or not self._collection:
            return
        try:
            import asyncio
            from shared.model_clients import build_embedding_client

            loop = asyncio.new_event_loop()
            try:
                client = build_embedding_client(self._config)
                embeddings = loop.run_until_complete(client.embed_texts([query]))
            finally:
                loop.close()

            results = self._collection.search(
                data=embeddings,
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"ef": 128}},
                limit=20,
                output_fields=["chunk_id", "source", "element_type"],
            )

            def update():
                table = self.query_one("#milvus-table", DataTable)
                table.clear()
                if results:
                    for hit in results[0]:
                        score = hit.score
                        table.add_row(
                            hit.entity.get("chunk_id", ""),
                            hit.entity.get("source", ""),
                            f"{hit.entity.get('element_type', '')}  [dim]score={score:.4f}[/]",
                            key=hit.entity.get("chunk_id", ""),
                        )

            self.app.call_from_thread(update)
        except Exception as exc:
            self._error = format_error(exc)
            self.app.call_from_thread(self._show_error)

    async def _delete_selected(self) -> None:
        if not self._collection:
            return
        table = self.query_one("#milvus-table", DataTable)
        if table.cursor_row is None:
            return
        row_data = table.get_row_at(table.cursor_row)
        chunk_id = row_data[0] if row_data else None
        if not chunk_id:
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Delete chunk '{chunk_id}' from Milvus?")
        )
        if confirmed:
            try:
                self._collection.delete(expr=f'chunk_id == "{chunk_id}"')
                self._load_page()
                self.notify(f"Deleted {chunk_id}", severity="information")
            except Exception as exc:
                self.notify(f"Error: {exc}", severity="error")
