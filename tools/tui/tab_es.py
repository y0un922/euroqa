"""Elasticsearch tab: browse documents, full-text search, filter by source, delete."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static
from textual.widget import Widget
from textual import work

from tools.tui.utils import (
    BackendError,
    FullRowDataTable,
    FullTextScreen,
    format_error,
    trunc_id,
)
from server.config import ServerConfig


class ElasticsearchPane(Widget):
    DEFAULT_CSS = """
    ElasticsearchPane { height: 1fr; }
    """

    def __init__(self, config: ServerConfig) -> None:
        super().__init__()
        self._config = config
        self._es = None
        self._error: BackendError | None = None
        self._page = 0
        self._page_size = 50
        self._current_query = ""
        self._source_filter = ""
        self._hit_rows: dict[str, dict[str, object]] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Connecting to Elasticsearch...", classes="stats-bar", id="es-stats")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Full-text search...", id="es-search")
                yield Input(placeholder="Filter by source...", id="es-source-filter")
                yield Button("Search", id="es-go", variant="primary")
                yield Button("Refresh", id="es-refresh", variant="default")
                yield Button("Delete", id="es-delete", variant="error")
            yield FullRowDataTable(id="es-table")
            with Horizontal(classes="page-bar"):
                yield Button("← Prev", id="es-prev")
                yield Static("", id="es-page-info")
                yield Button("Next →", id="es-next")
            yield Static("Select a row to view details", classes="detail-panel", id="es-detail")

    async def on_mount(self) -> None:
        table = self.query_one("#es-table", DataTable)
        table.add_column("chunk_id", width=30)
        table.add_column("source", width=40)
        table.add_column("element_type", width=16)
        table.add_column("section_path", width=30)
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._connect_and_load()

    @work
    async def _connect_and_load(self) -> None:
        try:
            from shared.elasticsearch_client import build_async_elasticsearch
            self._es = build_async_elasticsearch(self._config.es_url)
            count_resp = await self._es.count(index=self._config.es_index)
            count = count_resp["count"]
            stats = self.query_one("#es-stats", Static)
            stats.update(
                f"[bold green]✓[/] Index: [bold]{self._config.es_index}[/]  "
                f"│  Documents: [bold]{count:,}[/]"
            )
            await self._load_page()
        except Exception as exc:
            self._error = format_error(exc)
            self._show_error()

    def _show_error(self) -> None:
        stats = self.query_one("#es-stats", Static)
        stats.update(f"[bold red]✗[/] {self._error.title}: {self._error.detail}")

    async def _load_page(self) -> None:
        if not self._es:
            return
        try:
            results = await self._search_es()
            table = self.query_one("#es-table", DataTable)
            table.clear()
            self._hit_rows.clear()
            hits = results["hits"]["hits"]
            for hit in hits:
                src = hit["_source"]
                chunk_id = src.get("chunk_id", hit["_id"])
                self._hit_rows[hit["_id"]] = {
                    "_id": hit["_id"],
                    "_index": hit.get("_index", ""),
                    "_score": hit.get("_score", ""),
                    "_source": src,
                }
                table.add_row(
                    trunc_id(chunk_id),
                    trunc_id(src.get("source", ""), head=26, tail=4),
                    src.get("element_type", ""),
                    trunc_id(src.get("section_path", ""), head=26, tail=4),
                    key=hit["_id"],
                )
            total = results["hits"]["total"]["value"]
            page_info = self.query_one("#es-page-info", Static)
            start = self._page * self._page_size + 1
            end = start + len(hits) - 1
            page_info.update(f"{start}–{end} of {total:,}")
        except Exception as exc:
            self._error = format_error(exc)
            self._show_error()

    async def _search_es(self):
        body: dict = {"from": self._page * self._page_size, "size": self._page_size}
        if self._current_query or self._source_filter:
            must = []
            if self._current_query:
                must.append({"multi_match": {
                    "query": self._current_query,
                    "fields": ["content^2", "clause_ids.text^4", "section_path.text^2", "source_title.text^3"],
                }})
            if self._source_filter:
                must.append({"term": {"source": self._source_filter}})
            body["query"] = {"bool": {"must": must}}
        else:
            body["query"] = {"match_all": {}}
        return await self._es.search(index=self._config.es_index, body=body)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "es-go":
            self._current_query = self.query_one("#es-search", Input).value.strip()
            self._source_filter = self.query_one("#es-source-filter", Input).value.strip()
            self._page = 0
            self._do_search()
        elif btn_id == "es-refresh":
            self._current_query = ""
            self._source_filter = ""
            self._page = 0
            self._connect_and_load()
        elif btn_id == "es-next":
            self._page += 1
            self._do_search()
        elif btn_id == "es-prev":
            self._page = max(0, self._page - 1)
            self._do_search()
        elif btn_id == "es-delete":
            await self._delete_selected()

    @work
    async def _do_search(self) -> None:
        await self._load_page()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_detail(str(event.row_key.value))

    def on_full_row_data_table_row_double_clicked(
        self,
        event: FullRowDataTable.RowDoubleClicked,
    ) -> None:
        if event.data_table.id != "es-table":
            return
        doc_id = str(event.row_key.value)
        row = self._hit_rows.get(doc_id)
        if not row:
            return
        event.stop()
        self.app.push_screen(
            FullTextScreen(
                "Elasticsearch chunk",
                json.dumps(row, indent=2, ensure_ascii=False),
            )
        )

    @work
    async def _show_detail(self, doc_id: str) -> None:
        if not self._es:
            return
        try:
            result = await self._es.get(index=self._config.es_index, id=doc_id)
            source = result["_source"]
            text = json.dumps(source, indent=2, ensure_ascii=False)[:3000]
            detail = self.query_one("#es-detail", Static)
            detail.update(text)
        except Exception:
            pass

    async def _delete_selected(self) -> None:
        if not self._es:
            return
        table = self.query_one("#es-table", DataTable)
        if table.cursor_row is None:
            return
        row_data = table.get_row_at(table.cursor_row)
        chunk_id = row_data[0] if row_data else None
        if not chunk_id:
            return

        from tools.tui.tab_milvus import ConfirmScreen
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Delete document '{chunk_id}' from ES index?")
        )
        if confirmed:
            try:
                await self._es.delete_by_query(
                    index=self._config.es_index,
                    body={"query": {"term": {"chunk_id": chunk_id}}},
                )
                await self._load_page()
                self.notify(f"Deleted {chunk_id}", severity="information", markup=False)
            except Exception as exc:
                self.notify(f"Error: {exc}", severity="error", markup=False)
