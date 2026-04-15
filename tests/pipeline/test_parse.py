"""Tests for MinerU parsing providers."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from pipeline.config import PipelineConfig
from pipeline.parse import parse_pdf


class _FakeResponse:
    def __init__(self, json_data=None, *, content: bytes = b"", status_code: int = 200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, responses: dict[tuple[str, str], list[_FakeResponse]], calls: list[tuple[str, str, object]]):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, **kwargs):
        self._calls.append(("POST", url, kwargs))
        return self._responses[("POST", url)].pop(0)

    async def get(self, url: str, **kwargs):
        self._calls.append(("GET", url, kwargs))
        return self._responses[("GET", url)].pop(0)

    async def put(self, url: str, **kwargs):
        self._calls.append(("PUT", url, kwargs))
        return self._responses[("PUT", url)].pop(0)


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_parse_pdf_local_provider_writes_markdown_and_meta(tmp_path, monkeypatch):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 demo")
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="local",
        mineru_api_url="http://localhost:8000",
        mineru_poll_interval_seconds=0,
    )

    calls: list[tuple[str, str, object]] = []
    responses = {
        ("POST", "http://localhost:8000/api/v1/extract"): [
            _FakeResponse({"task_id": "task-1"}),
        ],
        ("GET", "http://localhost:8000/api/v1/extract/task-1"): [
            _FakeResponse({"state": "running"}),
            _FakeResponse({"state": "done"}),
        ],
        ("GET", "http://localhost:8000/api/v1/extract/task-1/result"): [
            _FakeResponse(
                {
                    "markdown": "# Demo\n\ncontent",
                    "metadata": {"title": "Demo Title"},
                }
            ),
        ],
    }

    monkeypatch.setattr(
        "pipeline.parse.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    md_path = await parse_pdf(pdf_path, output_dir, config)

    assert md_path == output_dir / "demo.md"
    assert md_path.read_text(encoding="utf-8") == "# Demo\n\ncontent"
    meta = json.loads((output_dir / "demo_meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Demo Title"
    assert [call[:2] for call in calls] == [
        ("POST", "http://localhost:8000/api/v1/extract"),
        ("GET", "http://localhost:8000/api/v1/extract/task-1"),
        ("GET", "http://localhost:8000/api/v1/extract/task-1"),
        ("GET", "http://localhost:8000/api/v1/extract/task-1/result"),
    ]


@pytest.mark.asyncio
async def test_parse_pdf_official_provider_downloads_full_md_zip(tmp_path, monkeypatch):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 demo")
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="official",
        mineru_api_token="token-123",
        mineru_official_base_url="https://mineru.net",
        mineru_official_model_version="vlm",
        mineru_poll_interval_seconds=0,
    )

    zip_bytes = _make_zip_bytes(
        {
            "result/full.md": "# Official Demo\n\nparsed",
            "result/demo_content_list.json": json.dumps({"items": []}),
        }
    )
    calls: list[tuple[str, str, object]] = []
    responses = {
        ("POST", "https://mineru.net/api/v4/file-urls/batch"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": ["https://upload.example/demo.pdf"],
                    },
                }
            ),
        ],
        ("PUT", "https://upload.example/demo.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-1"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {"file_name": "demo.pdf", "state": "waiting-file"},
                        ],
                    },
                }
            ),
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": "demo.pdf",
                                "state": "done",
                                "full_zip_url": "https://cdn.example/demo.zip",
                                "data_id": "demo",
                            }
                        ],
                    },
                }
            ),
        ],
        ("GET", "https://cdn.example/demo.zip"): [
            _FakeResponse(content=zip_bytes),
        ],
    }

    monkeypatch.setattr(
        "pipeline.parse.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    md_path = await parse_pdf(pdf_path, output_dir, config)

    assert md_path == output_dir / "demo.md"
    assert md_path.read_text(encoding="utf-8") == "# Official Demo\n\nparsed"
    meta = json.loads((output_dir / "demo_meta.json").read_text(encoding="utf-8"))
    assert meta["provider"] == "official"
    assert meta["batch_id"] == "batch-1"
    assert meta["result"]["data_id"] == "demo"
    assert meta["content_list_output"] == "demo_content_list.json"
    content_list = json.loads(
        (output_dir / "demo_content_list.json").read_text(encoding="utf-8")
    )
    assert content_list == {"items": []}
    post_call = calls[0]
    assert post_call[0] == "POST"
    assert post_call[1] == "https://mineru.net/api/v4/file-urls/batch"
    assert post_call[2]["headers"]["Authorization"] == "Bearer token-123"
    put_call = calls[1]
    assert put_call[0] == "PUT"
    assert put_call[1] == "https://upload.example/demo.pdf"
    assert put_call[2]["content"] == b"%PDF-1.4 demo"
    assert "data" not in put_call[2]


@pytest.mark.asyncio
async def test_parse_pdf_official_provider_requires_token(tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 demo")
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="official",
        mineru_api_token="",
    )

    with pytest.raises(RuntimeError, match="MINERU_API_TOKEN"):
        await parse_pdf(pdf_path, output_dir, config)
