"""Tests for MinerU parsing providers."""
from __future__ import annotations

import io
import json
import zipfile

import fitz
import pytest

from pipeline.config import PipelineConfig
from pipeline.parse import parse_pdf
from pipeline.structure import parse_markdown_to_tree


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


def _write_pdf(path, page_count: int) -> None:
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    doc.save(path)
    doc.close()


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
    _write_pdf(pdf_path, 1)
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
    assert put_call[2]["content"] == pdf_path.read_bytes()
    assert "data" not in put_call[2]


@pytest.mark.asyncio
async def test_parse_pdf_official_splits_large_pdf_and_offsets_page_metadata(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "demo.pdf"
    _write_pdf(pdf_path, 201)
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="official",
        mineru_api_token="token-123",
        mineru_official_base_url="https://mineru.net",
        mineru_official_model_version="vlm",
        mineru_poll_interval_seconds=0,
    )

    part1_name = "demo__part001_pages1-200.pdf"
    part2_name = "demo__part002_pages201-201.pdf"
    zip_part1 = _make_zip_bytes(
        {
            "result/full.md": "# Part 1\n\nfirst part",
            "result/part1_content_list.json": json.dumps(
                {
                    "items": [
                        {
                            "type": "text",
                            "text": "Part 1",
                            "text_level": 1,
                            "page_idx": 199,
                        }
                    ]
                }
            ),
        }
    )
    zip_part2 = _make_zip_bytes(
        {
            "result/full.md": "# Part 2\n\nsecond part",
            "result/part2_content_list.json": json.dumps(
                {
                    "items": [
                        {
                            "type": "text",
                            "text": "Part 2",
                            "text_level": 1,
                            "page_idx": 0,
                        },
                        {
                            "type": "text",
                            "text": "second part",
                            "text_level": 0,
                            "page_idx": 0,
                            "bbox": [10, 20, 30, 40],
                        },
                        {
                            "type": "image",
                            "img_path": "images/part2-figure.png",
                            "page_idx": 0,
                        },
                    ]
                }
            ),
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
                        "file_urls": [
                            "https://upload.example/part1.pdf",
                            "https://upload.example/part2.pdf",
                        ],
                    },
                }
            ),
        ],
        ("PUT", "https://upload.example/part1.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("PUT", "https://upload.example/part2.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-1"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": part1_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part1.zip",
                            },
                            {
                                "file_name": part2_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part2.zip",
                            },
                        ],
                    },
                }
            ),
        ],
        ("GET", "https://cdn.example/part1.zip"): [
            _FakeResponse(content=zip_part1),
        ],
        ("GET", "https://cdn.example/part2.zip"): [
            _FakeResponse(content=zip_part2),
        ],
    }

    monkeypatch.setattr(
        "pipeline.parse.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    md_path = await parse_pdf(pdf_path, output_dir, config)

    assert md_path == output_dir / "demo.md"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "demo.md",
        "demo_content_list.json",
        "demo_meta.json",
    ]
    content_list = json.loads(
        (output_dir / "demo_content_list.json").read_text(encoding="utf-8")
    )
    assert [item["page_idx"] for item in content_list["items"]] == [
        199,
        200,
        200,
        200,
    ]
    assert content_list["items"][3]["type"] == "image"
    meta = json.loads((output_dir / "demo_meta.json").read_text(encoding="utf-8"))
    assert meta["split_pdf"] is True
    assert meta["original_page_count"] == 201
    assert meta["parts"][1]["page_offset"] == 200
    assert meta["parts"][1]["validation"]["min_original_page_idx"] == 200

    tree = parse_markdown_to_tree(
        md_path.read_text(encoding="utf-8"),
        source="demo",
        content_list=content_list,
    )
    part2 = tree.children[1]
    assert part2.page_file_index == [200]
    assert part2.page_numbers == [201]
    assert part2.bbox_page_idx == 200
    assert part2.bbox == [10.0, 20.0, 30.0, 40.0]


@pytest.mark.asyncio
async def test_parse_pdf_official_split_missing_content_list_fails_closed(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "demo.pdf"
    _write_pdf(pdf_path, 201)
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="official",
        mineru_api_token="token-123",
        mineru_official_base_url="https://mineru.net",
        mineru_poll_interval_seconds=0,
    )

    part1_name = "demo__part001_pages1-200.pdf"
    part2_name = "demo__part002_pages201-201.pdf"
    calls: list[tuple[str, str, object]] = []
    responses = {
        ("POST", "https://mineru.net/api/v4/file-urls/batch"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": [
                            "https://upload.example/part1.pdf",
                            "https://upload.example/part2.pdf",
                        ],
                    },
                }
            ),
        ],
        ("PUT", "https://upload.example/part1.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("PUT", "https://upload.example/part2.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-1"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": part1_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part1.zip",
                            },
                            {
                                "file_name": part2_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part2.zip",
                            },
                        ],
                    },
                }
            ),
        ],
        ("GET", "https://cdn.example/part1.zip"): [
            _FakeResponse(
                content=_make_zip_bytes(
                    {
                        "result/full.md": "# Part 1",
                        "result/part1_content_list.json": json.dumps(
                            {
                                "items": [
                                    {
                                        "type": "text",
                                        "text": "Part 1",
                                        "text_level": 1,
                                        "page_idx": 0,
                                    }
                                ]
                            }
                        ),
                    }
                )
            ),
        ],
        ("GET", "https://cdn.example/part2.zip"): [
            _FakeResponse(content=_make_zip_bytes({"result/full.md": "# Part 2"})),
        ],
    }

    monkeypatch.setattr(
        "pipeline.parse.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    with pytest.raises(RuntimeError, match="missing content_list"):
        await parse_pdf(pdf_path, output_dir, config)

    assert not (output_dir / "demo.md").exists()
    assert not (output_dir / "demo_content_list.json").exists()
    assert not (output_dir / "demo_meta.json").exists()


@pytest.mark.asyncio
async def test_parse_pdf_official_split_invalid_page_idx_fails_closed(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "demo.pdf"
    _write_pdf(pdf_path, 201)
    output_dir = tmp_path / "parsed" / "demo"
    config = PipelineConfig(
        mineru_provider="official",
        mineru_api_token="token-123",
        mineru_official_base_url="https://mineru.net",
        mineru_poll_interval_seconds=0,
    )

    part1_name = "demo__part001_pages1-200.pdf"
    part2_name = "demo__part002_pages201-201.pdf"
    calls: list[tuple[str, str, object]] = []
    responses = {
        ("POST", "https://mineru.net/api/v4/file-urls/batch"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": [
                            "https://upload.example/part1.pdf",
                            "https://upload.example/part2.pdf",
                        ],
                    },
                }
            ),
        ],
        ("PUT", "https://upload.example/part1.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("PUT", "https://upload.example/part2.pdf"): [
            _FakeResponse(status_code=200),
        ],
        ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-1"): [
            _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": part1_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part1.zip",
                            },
                            {
                                "file_name": part2_name,
                                "state": "done",
                                "full_zip_url": "https://cdn.example/part2.zip",
                            },
                        ],
                    },
                }
            ),
        ],
        ("GET", "https://cdn.example/part1.zip"): [
            _FakeResponse(
                content=_make_zip_bytes(
                    {
                        "result/full.md": "# Part 1",
                        "result/part1_content_list.json": json.dumps(
                            {
                                "items": [
                                    {
                                        "type": "text",
                                        "text": "Part 1",
                                        "text_level": 1,
                                        "page_idx": 0,
                                    }
                                ]
                            }
                        ),
                    }
                )
            ),
        ],
        ("GET", "https://cdn.example/part2.zip"): [
            _FakeResponse(
                content=_make_zip_bytes(
                    {
                        "result/full.md": "# Part 2",
                        "result/part2_content_list.json": json.dumps(
                            {
                                "items": [
                                    {
                                        "type": "text",
                                        "text": "Part 2",
                                        "text_level": 1,
                                        "page_idx": 1,
                                    }
                                ]
                            }
                        ),
                    }
                )
            ),
        ],
    }

    monkeypatch.setattr(
        "pipeline.parse.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    with pytest.raises(RuntimeError, match="out-of-range page_idx"):
        await parse_pdf(pdf_path, output_dir, config)

    assert not (output_dir / "demo.md").exists()
    assert not (output_dir / "demo_content_list.json").exists()
    assert not (output_dir / "demo_meta.json").exists()


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
