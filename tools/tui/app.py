"""Main TUI application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from tools.tui.utils import load_config
from tools.tui.tab_milvus import MilvusPane
from tools.tui.tab_es import ElasticsearchPane
from tools.tui.tab_minio import MinioPane
from tools.tui.tab_redis import RedisPane


class EuroQATUI(App):
    TITLE = "Euro_QA Database Manager"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark"),
        ("1", "tab_1", "Milvus"),
        ("2", "tab_2", "ES"),
        ("3", "tab_3", "MinIO"),
        ("4", "tab_4", "Redis"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }

    TabbedContent {
        height: 1fr;
    }

    /* ── Stats bar ── */
    .stats-bar {
        height: 1;
        background: $primary-background;
        color: $text;
        padding: 0 2;
        text-style: bold;
    }

    /* ── Toolbar ── */
    .toolbar {
        height: auto;
        padding: 1 1 0 1;
        layout: horizontal;
    }
    .toolbar Input {
        width: 1fr;
        margin: 0 1 0 0;
    }
    .toolbar Button {
        min-width: 16;
        margin: 0 0 0 1;
    }

    /* ── DataTable ── */
    DataTable {
        height: 1fr;
        margin: 1 1;
        scrollbar-size: 1 1;
    }
    DataTable > .datatable--header {
        text-style: bold;
        color: $text;
        background: $accent 15%;
    }
    DataTable > .datatable--cursor {
        background: $accent 40%;
        color: $text;
        text-style: bold;
    }

    /* ── Pagination bar ── */
    .page-bar {
        height: 3;
        align: center middle;
        padding: 0 1;
    }
    .page-bar Button {
        min-width: 12;
        margin: 0 1;
    }
    .page-bar Static {
        width: auto;
        text-align: center;
        color: $text-muted;
    }

    /* ── Detail / metadata panels ── */
    .detail-panel {
        height: 12;
        margin: 0 1 1 1;
        padding: 1 2;
        border: round $primary 50%;
        background: $boost;
        overflow-y: auto;
    }
    .detail-panel-tall {
        height: 1fr;
        margin: 0 1 1 1;
        padding: 1 2;
        border: round $primary 50%;
        background: $boost;
        overflow-y: auto;
    }

    /* ── Error state ── */
    .error-text {
        color: $error;
        text-style: bold italic;
        padding: 0 2;
        height: 1;
    }

    /* ── Confirm dialog ── */
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 64;
        height: auto;
        border: thick $error 80%;
        background: $surface;
        padding: 2 3;
    }
    #confirm-dialog Label {
        margin-bottom: 1;
        text-align: center;
        width: 100%;
    }
    #confirm-buttons {
        align: center middle;
        height: auto;
    }
    #confirm-buttons Button {
        margin: 0 2;
    }

    /* ── Full text dialog ── */
    FullTextScreen {
        align: center middle;
    }
    #full-text-dialog {
        width: 90%;
        height: 85%;
        border: thick $primary 80%;
        background: $surface;
        padding: 1 2;
    }
    #full-text-title {
        height: 1;
        text-style: bold;
        margin-bottom: 1;
    }
    #full-text-content {
        height: 1fr;
    }
    #full-text-close {
        margin-top: 1;
        align-horizontal: center;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("  Milvus  ", id="tab-milvus"):
                yield MilvusPane(self.config)
            with TabPane(" Elasticsearch ", id="tab-es"):
                yield ElasticsearchPane(self.config)
            with TabPane("  MinIO  ", id="tab-minio"):
                yield MinioPane(self.config)
            with TabPane("  Redis  ", id="tab-redis"):
                yield RedisPane(self.config)
        yield Footer()

    def action_toggle_dark(self) -> None:
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_tab_1(self) -> None:
        self.query_one(TabbedContent).active = "tab-milvus"

    def action_tab_2(self) -> None:
        self.query_one(TabbedContent).active = "tab-es"

    def action_tab_3(self) -> None:
        self.query_one(TabbedContent).active = "tab-minio"

    def action_tab_4(self) -> None:
        self.query_one(TabbedContent).active = "tab-redis"
