"""MinIO tab: list objects, view metadata, delete with optional cascade to ES/Milvus."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static
from textual.widget import Widget
from textual import work

from tools.tui.utils import format_error, trunc_id, BackendError
from server.config import ServerConfig


class MinioPane(Widget):
    DEFAULT_CSS = """
    MinioPane { height: 1fr; }
    """

    def __init__(self, config: ServerConfig) -> None:
        super().__init__()
        self._config = config
        self._client = None
        self._error: BackendError | None = None
        self._bucket = "eurocode"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Connecting to MinIO...", classes="stats-bar", id="minio-stats")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Bucket name...", value=self._bucket, id="minio-bucket")
                yield Button("List", id="minio-list", variant="primary")
                yield Button("Delete", id="minio-del", variant="error")
                yield Button("Cascade Delete", id="minio-cascade", variant="warning")
            yield DataTable(id="minio-table")
            yield Static("Select an object to view metadata", classes="detail-panel", id="minio-meta")

    async def on_mount(self) -> None:
        table = self.query_one("#minio-table", DataTable)
        table.add_column("object_name", width=50)
        table.add_column("size", width=12)
        table.add_column("last_modified", width=20)
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._connect_and_list()

    @work(thread=True)
    def _connect_and_list(self) -> None:
        try:
            from minio import Minio
            self._client = Minio(
                self._config.minio_endpoint,
                access_key=self._config.minio_access_key,
                secret_key=self._config.minio_secret_key,
                secure=self._config.minio_secure,
            )
            self.app.call_from_thread(self._refresh_list)
        except Exception as exc:
            self._error = format_error(exc)
            self.app.call_from_thread(self._show_error)

    def _show_error(self) -> None:
        stats = self.query_one("#minio-stats", Static)
        stats.update(f"[bold red]✗[/] {self._error.title}: {self._error.detail}")

    def _refresh_list(self) -> None:
        if not self._client:
            return
        table = self.query_one("#minio-table", DataTable)
        table.clear()
        try:
            bucket = self.query_one("#minio-bucket", Input).value.strip() or self._bucket
            if not self._client.bucket_exists(bucket):
                stats = self.query_one("#minio-stats", Static)
                stats.update(f"[bold yellow]![/] Bucket [bold]'{bucket}'[/] does not exist")
                return
            objects = list(self._client.list_objects(bucket, recursive=True))
            for obj in objects:
                size_str = _fmt_size(obj.size) if obj.size else "—"
                modified = str(obj.last_modified)[:19] if obj.last_modified else "—"
                table.add_row(
                    trunc_id(obj.object_name, head=44, tail=4),
                    size_str,
                    modified,
                    key=obj.object_name,
                )
            stats = self.query_one("#minio-stats", Static)
            stats.update(
                f"[bold green]✓[/] Bucket: [bold]{bucket}[/]  "
                f"│  Objects: [bold]{len(objects):,}[/]"
            )
        except Exception as exc:
            self._error = format_error(exc)
            self._show_error()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_metadata(str(event.row_key.value))

    @work(thread=True)
    def _show_metadata(self, object_name: str) -> None:
        if not self._client:
            return
        try:
            bucket = self._bucket
            stat = self._client.stat_object(bucket, object_name)
            lines = [
                f"[bold]Object:[/]       {stat.object_name}",
                f"[bold]Size:[/]         {_fmt_size(stat.size)}",
                f"[bold]Content-Type:[/] {stat.content_type}",
                f"[bold]ETag:[/]         {stat.etag}",
                f"[bold]Modified:[/]     {stat.last_modified}",
            ]
            if stat.metadata:
                lines.append("[bold]Metadata:[/]")
                for k, v in stat.metadata.items():
                    lines.append(f"  {k}: {v}")
            text = "\n".join(lines)

            def update():
                meta = self.query_one("#minio-meta", Static)
                meta.update(text)

            self.app.call_from_thread(update)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "minio-list":
            self._bucket = self.query_one("#minio-bucket", Input).value.strip() or "eurocode"
            self._connect_and_list()
        elif btn_id == "minio-del":
            await self._delete_object(cascade=False)
        elif btn_id == "minio-cascade":
            await self._delete_object(cascade=True)

    async def _delete_object(self, cascade: bool) -> None:
        table = self.query_one("#minio-table", DataTable)
        if table.cursor_row is None:
            return
        row_data = table.get_row_at(table.cursor_row)
        object_name = row_data[0] if row_data else None
        if not object_name:
            return

        action = "CASCADE delete (MinIO + ES + Milvus)" if cascade else "Delete from MinIO only"
        from tools.tui.tab_milvus import ConfirmScreen
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"{action}:\n'{object_name}'")
        )
        if not confirmed:
            return

        try:
            self._client.remove_object(self._bucket, object_name)
            if cascade:
                await self._cascade_delete_chunks(object_name)
            self._refresh_list()
            msg = f"Deleted {object_name}" + (" + associated chunks" if cascade else "")
            self.notify(msg, severity="information", markup=False)
        except Exception as exc:
            self.notify(f"Error: {exc}", severity="error", markup=False)

    async def _cascade_delete_chunks(self, object_name: str) -> None:
        source = object_name.replace("uploads/", "").replace(".pdf", "")

        from shared.elasticsearch_client import build_async_elasticsearch
        es = build_async_elasticsearch(self._config.es_url)
        try:
            await es.delete_by_query(
                index=self._config.es_index,
                body={"query": {"term": {"source": source}}},
            )
        finally:
            await es.close()

        import asyncio
        from pymilvus import connections, Collection

        def milvus_delete():
            connections.connect(host=self._config.milvus_host, port=self._config.milvus_port)
            collection = Collection(self._config.milvus_collection)
            collection.delete(expr=f'source == "{source}"')

        await asyncio.to_thread(milvus_delete)


def _fmt_size(size: int | None) -> str:
    if not size:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
