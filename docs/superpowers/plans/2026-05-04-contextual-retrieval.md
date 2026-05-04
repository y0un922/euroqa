# Contextual Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task is dispatched to a fresh `trellis-implement` sub-agent; `trellis-check` runs between tasks.

**Goal:** Implement Anthropic-style contextual retrieval as a Stage 3.5 enrichment: per-chunk LLM-generated context blurb + special-chunk semantic description, written into `embedding_text` (Milvus + ES both benefit from same field).

**Architecture:** Single `Contextualizer` class using `AsyncOpenAI` client (OpenAI-compatible protocol; switch provider by changing `LLM_BASE_URL` env). Stage 3.5 expanded from "summarize special chunks only" to "contextualize all chunks". Doc-level summary computed once per document; per-chunk contextualize runs concurrently bounded by `asyncio.Semaphore`. `content` field unchanged — frontend zero impact.

**Tech Stack:** Python 3.12+, `openai` SDK (AsyncOpenAI), `pydantic-settings` (config), `asyncio` (concurrency), `pytest` + `pytest-asyncio` (testing), `structlog.testing.capture_logs` (logger assertions).

---

## File Structure

- New: `pipeline/contextualizer.py` — Contextualizer class + dataclasses + outline builder
- New: `tests/pipeline/test_contextualizer.py` — Contextualizer unit tests (mock AsyncOpenAI)
- New: `tests/pipeline/test_outline_builder.py` — build_outline_from_tree unit tests
- New: `tests/pipeline/test_contextualize_stage.py` — enrich_chunks integration unit tests
- Modify: `pipeline/config.py` — add 2 fields (concurrency, retry_attempts)
- Rename: `pipeline/summarize.py` → `pipeline/contextualize.py` — replace enrich_chunk_summaries with enrich_chunks
- Modify: `pipeline/run.py` — wire stage 3.5 to enrich_chunks
- New: `tests/pipeline/test_config.py` — PipelineConfig contextualize field tests
- New: `tests/pipeline/test_run.py` — Stage 3.5 runner wiring test
- Modify: `server/services/pipeline_runner.py` — rename single-document Stage 3.5 import/call site
- Modify: `tests/server/test_pipeline_runner.py` — update monkeypatch target to `enrich_chunks`
- Delete: `tests/pipeline/test_summarize.py` — remove superseded summary-stage tests after migration

## Grounding Notes

- `pipeline/config.py` already uses `SettingsConfigDict(env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore")`, so `contextualize_concurrency` and `contextualize_retry_attempts` automatically map to uppercase env vars.
- `pipeline/summarize.py` already uses `AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)` and `client.chat.completions.create(...)`; mirror this pattern.
- `pipeline/run.py` Stage 3.5 currently counts `special_chunks`, calls `enrich_chunk_summaries`, and records `stage35_chunks.json`.
- `pipeline/chunk.py` imports schema enum as `ChunkElementType`; `pipeline.structure.py` has separate `ElementType` with `SECTION`.
- `server/models/schemas.py` defines `Chunk`, `ChunkMetadata`, and `ElementType` values `text`, `table`, `formula`, `image`.
- Existing tests use `pytest.mark.asyncio`, `AsyncMock`, parametrization, monkeypatching, and `structlog.testing.capture_logs`.

### Task 1: Add contextualize_concurrency and contextualize_retry_attempts to PipelineConfig

Files:
- Modify `pipeline/config.py`
- Create `tests/pipeline/test_config.py`

- [ ] **Step 1: Add the failing config test file**

Create `tests/pipeline/test_config.py` with:

```python
"""Tests for contextualize-related pipeline settings."""
from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig


def test_contextualize_fields_default_values(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONTEXTUALIZE_CONCURRENCY", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_RETRY_ATTEMPTS", raising=False)

    cfg = PipelineConfig()

    assert cfg.contextualize_concurrency == 8
    assert cfg.contextualize_retry_attempts == 2


def test_contextualize_fields_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONTEXTUALIZE_CONCURRENCY", "16")
    monkeypatch.setenv("CONTEXTUALIZE_RETRY_ATTEMPTS", "3")

    cfg = PipelineConfig()

    assert cfg.contextualize_concurrency == 16
    assert cfg.contextualize_retry_attempts == 3
```

- [ ] **Step 2: Run the new test and expect failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_config.py -q
```

Expected output:

```text
FF
E   AttributeError: 'PipelineConfig' object has no attribute 'contextualize_concurrency'
```

- [ ] **Step 3: Add the two config fields in PipelineConfig**

Insert these lines in `pipeline/config.py` next to the existing LLM settings:

```python
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_concurrency: int = 10
    contextualize_concurrency: int = 8
    contextualize_retry_attempts: int = 2
```

- [ ] **Step 4: Re-run config tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/test_config.py tests/pipeline/test_config.py -q
```

Expected output:

```text
.....                                                                    [100%]
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py tests/pipeline/test_config.py
git commit -m "feat(config): add contextualize_concurrency and retry_attempts fields"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 2: ContextualizeRequest / ContextualizeResult dataclasses

Files:
- Create `pipeline/contextualizer.py`
- Create `tests/pipeline/test_contextualizer.py`

- [ ] **Step 1: Add failing dataclass tests**

Create `tests/pipeline/test_contextualizer.py` with:

```python
"""Tests for contextual retrieval helper primitives."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import get_args

import pytest

from pipeline.contextualizer import ContextualizeRequest, ContextualizeResult


def test_contextualize_request_is_frozen_and_defaults_chunk_alt():
    request = ContextualizeRequest(
        doc_summary="doc summary",
        parent_section_text="parent text",
        chunk_content="chunk text",
        chunk_kind="text",
        section_path=["Section 3", "3.2 Concrete"],
    )

    assert request.chunk_alt == ""

    with pytest.raises(FrozenInstanceError):
        request.chunk_content = "changed"


def test_contextualize_request_chunk_kind_literal_values():
    field_info = next(field for field in fields(ContextualizeRequest) if field.name == "chunk_kind")

    assert set(get_args(field_info.type)) == {"text", "table", "formula", "image"}


def test_contextualize_result_is_frozen_and_defaults_description_empty():
    result = ContextualizeResult(context_blurb="context")

    assert result.semantic_description == ""

    with pytest.raises(FrozenInstanceError):
        result.context_blurb = "changed"
```

- [ ] **Step 2: Run tests and expect ImportError**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
ERROR tests/pipeline/test_contextualizer.py
E   ModuleNotFoundError: No module named 'pipeline.contextualizer'
```

- [ ] **Step 3: Create the dataclass module**

Create `pipeline/contextualizer.py` with:

```python
"""Contextual retrieval helper objects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ContextualizeRequest:
    """Inputs required to contextualize one chunk."""

    doc_summary: str
    parent_section_text: str
    chunk_content: str
    chunk_kind: Literal["text", "table", "formula", "image"]
    section_path: list[str]
    chunk_alt: str = ""


@dataclass(frozen=True)
class ContextualizeResult:
    """LLM output for one contextualized chunk."""

    context_blurb: str
    semantic_description: str = ""
```

- [ ] **Step 4: Re-run tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
...                                                                      [100%]
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/contextualizer.py tests/pipeline/test_contextualizer.py
git commit -m "feat(contextualizer): add ContextualizeRequest/Result dataclasses"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 3: build_outline_from_tree pure function

Files:
- Modify `pipeline/contextualizer.py`
- Create `tests/pipeline/test_outline_builder.py`

- [ ] **Step 1: Add failing outline-builder tests**

Create `tests/pipeline/test_outline_builder.py` with:

```python
"""Tests for document outline construction used by contextual retrieval."""
from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from pipeline.contextualizer import build_outline_from_tree
from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType


def _section(title: str, content: str = "", children: list[DocumentNode] | None = None) -> DocumentNode:
    return DocumentNode(
        title=title,
        content=content,
        element_type=StructElementType.SECTION,
        children=children or [],
        source="EN 1992-1-1:2004",
    )


def test_single_root_plus_two_sections():
    tree = _section(
        "root",
        children=[
            _section("1 General", "Scope paragraph.\n\nSecond paragraph."),
            _section("2 Basis of design", "Design paragraph."),
        ],
    )

    outline = build_outline_from_tree(tree)

    assert outline == (
        "1 General\n"
        "  Scope paragraph.\n"
        "2 Basis of design\n"
        "  Design paragraph."
    )


def test_multilevel_tree_four_levels_deep():
    tree = _section(
        "root",
        children=[
            _section(
                "1 General",
                "Top paragraph.",
                children=[
                    _section(
                        "1.1 Scope",
                        "Scope paragraph.",
                        children=[
                            _section(
                                "1.1.1 Eurocode 2 scope",
                                "Detail paragraph.",
                                children=[
                                    _section("1.1.1.1 Design assumptions", "Assumption paragraph."),
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )

    outline = build_outline_from_tree(tree)

    assert "1 General" in outline
    assert "  1.1 Scope" in outline
    assert "    1.1.1 Eurocode 2 scope" in outline
    assert "      1.1.1.1 Design assumptions" in outline


def test_empty_tree_returns_empty_string():
    tree = _section("root")

    assert build_outline_from_tree(tree) == ""


def test_large_outline_falls_back_to_titles_only():
    huge = "x " * 120000
    tree = _section(
        "root",
        children=[
            _section("1 General", huge),
            _section("2 Materials", huge),
        ],
    )

    with capture_logs() as logs:
        outline = build_outline_from_tree(tree)

    assert outline == "1 General\n2 Materials"
    assert any(log["event"] == "outline_fallback_titles_only" for log in logs)


@pytest.mark.parametrize(
    ("paragraph", "expected"),
    [
        ("x" * 199, "1 General\n  " + ("x" * 199)),
        ("x" * 200, "1 General\n  " + ("x" * 200) + "…"),
    ],
)
def test_first_para_max_chars_boundary(paragraph: str, expected: str):
    tree = _section("root", children=[_section("1 General", paragraph)])

    assert build_outline_from_tree(tree, first_para_max_chars=200) == expected
```

- [ ] **Step 2: Run tests and expect import failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_outline_builder.py -q
```

Expected output:

```text
ERROR tests/pipeline/test_outline_builder.py
E   ImportError: cannot import name 'build_outline_from_tree'
```

- [ ] **Step 3: Implement build_outline_from_tree and helpers**

Merge these imports and functions into `pipeline/contextualizer.py`:

```python
import re
from collections.abc import Iterator

import structlog

from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType


logger = structlog.get_logger()


def build_outline_from_tree(tree: DocumentNode, *, first_para_max_chars: int = 200) -> str:
    """Build a deterministic outline from the document tree."""
    lines: list[str] = []

    for node, depth in _walk_with_depth(tree):
        if node.element_type != StructElementType.SECTION:
            continue
        if node.title == "root":
            continue

        indent = "  " * depth
        lines.append(f"{indent}{node.title}")

        first_para = _first_nonempty_paragraph(node.content)
        if first_para:
            truncated = first_para[:first_para_max_chars]
            suffix = "…" if len(first_para) >= first_para_max_chars else ""
            lines.append(f"{indent}  {truncated}{suffix}")

    text = "\n".join(lines)
    if _estimate_tokens(text) > 50000:
        logger.warning("outline_fallback_titles_only", source=tree.source)
        return _build_titles_only_outline(tree)
    return text


def _walk_with_depth(tree: DocumentNode) -> Iterator[tuple[DocumentNode, int]]:
    stack: list[tuple[DocumentNode, int]] = [(tree, -1)]
    while stack:
        node, depth = stack.pop()
        if node.title != "root":
            yield node, max(depth, 0)
        for child in reversed(node.children):
            stack.append((child, depth + 1))


def _first_nonempty_paragraph(text: str) -> str:
    for paragraph in re.split(r"\n\s*\n", text):
        collapsed = " ".join(paragraph.split())
        if collapsed:
            return collapsed
    return ""


def _build_titles_only_outline(tree: DocumentNode) -> str:
    lines: list[str] = []
    for node, depth in _walk_with_depth(tree):
        if node.element_type != StructElementType.SECTION:
            continue
        if node.title == "root":
            continue
        lines.append(f"{'  ' * depth}{node.title}")
    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 if text else 0
```

- [ ] **Step 4: Re-run outline tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_outline_builder.py -q
```

Expected output:

```text
......                                                                   [100%]
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/contextualizer.py tests/pipeline/test_outline_builder.py
git commit -m "feat(contextualizer): add build_outline_from_tree"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 4: Contextualizer class skeleton + generate_doc_summary

Files:
- Modify `pipeline/contextualizer.py`
- Modify `tests/pipeline/test_contextualizer.py`

- [ ] **Step 1: Add failing doc-summary tests**

Append to `tests/pipeline/test_contextualizer.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from pipeline.config import PipelineConfig
from pipeline.contextualizer import Contextualizer


def _chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.asyncio
async def test_generate_doc_summary_prompt_contains_title_and_outline():
    create = AsyncMock(return_value=_chat_response("Summary text."))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(
            PipelineConfig(
                llm_api_key="key",
                llm_base_url="https://llm.test/v1",
                llm_model="demo-model",
                contextualize_retry_attempts=2,
            )
        )
        result = await contextualizer.generate_doc_summary(
            source_title="Design of concrete structures",
            doc_outline_text="1 General\n  Scope paragraph.",
        )

    assert result == "Summary text."
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "demo-model"
    assert kwargs["temperature"] == 0.1
    assert kwargs["max_tokens"] == 800
    prompt = kwargs["messages"][0]["content"]
    assert "Design of concrete structures" in prompt
    assert "1 General" in prompt


@pytest.mark.asyncio
async def test_generate_doc_summary_retries_timeout_then_succeeds():
    create = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout-1"),
            _chat_response("Recovered summary."),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig(contextualize_retry_attempts=2))
        result = await contextualizer.generate_doc_summary("Title", "Outline")

    assert result == "Recovered summary."
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_generate_doc_summary_retry_exhaustion_raises():
    create = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout-1"),
            httpx.ReadTimeout("timeout-2"),
            httpx.ReadTimeout("timeout-3"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig(contextualize_retry_attempts=3))
        with pytest.raises(httpx.ReadTimeout, match="timeout-3"):
            await contextualizer.generate_doc_summary("Title", "Outline")

    assert create.await_count == 3
```

- [ ] **Step 2: Run tests and expect failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
E   ImportError: cannot import name 'Contextualizer'
```

- [ ] **Step 3: Implement Contextualizer.__init__ and generate_doc_summary**

Merge these imports and methods into `pipeline/contextualizer.py`:

```python
from openai import AsyncOpenAI

from pipeline.config import PipelineConfig


class Contextualizer:
    """Single OpenAI-compatible LLM contextualizer."""

    def __init__(self, config: PipelineConfig) -> None:
        self._client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
        )
        self._model = config.llm_model
        self._retry_attempts = max(1, config.contextualize_retry_attempts)

    async def generate_doc_summary(self, source_title: str, doc_outline_text: str) -> str:
        prompt = (
            f"Below is the outline and excerpts of a regulatory/standards document titled '{source_title}'.\n"
            "In 200-400 words, summarize its scope, structure, and key technical topics.\n"
            "This summary will be used as context to improve search retrieval of individual chunks.\n\n"
            f"Outline:\n{doc_outline_text}"
        )
        return await self._call_llm(prompt, max_tokens=800)

    async def _call_llm(self, prompt: str, *, max_tokens: int) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                return content.strip() if content else ""
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "contextualize_llm_attempt_failed",
                    attempt=attempt,
                    max_attempts=self._retry_attempts,
                    error=str(exc),
                )
        assert last_error is not None
        raise last_error
```

- [ ] **Step 4: Re-run tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
......                                                                   [100%]
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/contextualizer.py tests/pipeline/test_contextualizer.py
git commit -m "feat(contextualizer): add Contextualizer.generate_doc_summary"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 5: Contextualizer.contextualize_chunk text path

Files:
- Modify `pipeline/contextualizer.py`
- Modify `tests/pipeline/test_contextualizer.py`

- [ ] **Step 1: Add the failing text-path test**

Append to `tests/pipeline/test_contextualizer.py`:

```python
@pytest.mark.asyncio
async def test_contextualize_chunk_text_path():
    llm_text = "Section 3.2 of EN1992 introduces concrete material properties."
    create = AsyncMock(return_value=_chat_response(llm_text))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    request = ContextualizeRequest(
        doc_summary="This document covers concrete structure design.",
        parent_section_text="3.2 Concrete material properties are defined here.",
        chunk_content="Concrete strength classes are based on cylinder strength.",
        chunk_kind="text",
        section_path=["EN 1992-1-1", "Section 3", "3.2 Concrete"],
    )

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig())
        result = await contextualizer.contextualize_chunk(request)

    assert result == ContextualizeResult(context_blurb=llm_text, semantic_description="")
    prompt = create.await_args.kwargs["messages"][0]["content"]
    assert prompt.index("Document summary:") < prompt.index("Section path:")
    assert prompt.index("Section path:") < prompt.index("Section containing the chunk:")
    assert prompt.index("Section containing the chunk:") < prompt.index("Chunk to situate:")
    assert "EN 1992-1-1 > Section 3 > 3.2 Concrete" in prompt
```

- [ ] **Step 2: Run the focused test and expect failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py::test_contextualize_chunk_text_path -q
```

Expected output:

```text
E   AttributeError: 'Contextualizer' object has no attribute 'contextualize_chunk'
```

- [ ] **Step 3: Implement the text contextualization path**

Add these methods to `Contextualizer` in `pipeline/contextualizer.py`:

```python
    async def contextualize_chunk(self, request: ContextualizeRequest) -> ContextualizeResult:
        if request.chunk_kind == "text":
            return await self._contextualize_text_chunk(request)
        raise ValueError(f"Unsupported chunk kind: {request.chunk_kind}")

    async def _contextualize_text_chunk(self, request: ContextualizeRequest) -> ContextualizeResult:
        prompt = (
            f"Document summary: {request.doc_summary}\n\n"
            f"Section path: {' > '.join(request.section_path)}\n\n"
            f"Section containing the chunk:\n{request.parent_section_text}\n\n"
            f"Chunk to situate:\n{request.chunk_content}\n\n"
            "In 1-3 sentences, give a short context that situates this chunk within the document "
            "for retrieval purposes. Output only the context, no preamble."
        )
        context = await self._call_llm(prompt, max_tokens=300)
        return ContextualizeResult(context_blurb=context.strip(), semantic_description="")
```

- [ ] **Step 4: Re-run the contextualizer test file and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
.......                                                                  [100%]
7 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/contextualizer.py tests/pipeline/test_contextualizer.py
git commit -m "feat(contextualizer): add contextualize_chunk text path"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 6: Contextualizer.contextualize_chunk special path with JSON fallback

Files:
- Modify `pipeline/contextualizer.py`
- Modify `tests/pipeline/test_contextualizer.py`

- [ ] **Step 1: Add failing special-path tests**

Append to `tests/pipeline/test_contextualizer.py` and add the `capture_logs` import:

```python
from structlog.testing import capture_logs


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_kind", ["table", "formula"])
async def test_contextualize_chunk_special_json(chunk_kind: str):
    raw_json = (
        '{"context": "This element supports material property lookup.", '
        '"description": "It expresses design values used in concrete calculations."}'
    )
    create = AsyncMock(return_value=_chat_response(raw_json))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    request = ContextualizeRequest(
        doc_summary="Document summary.",
        parent_section_text="Parent section text.",
        chunk_content="Element content.",
        chunk_kind=chunk_kind,
        section_path=["Section 3", "3.2 Concrete"],
    )

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig())
        result = await contextualizer.contextualize_chunk(request)

    assert result == ContextualizeResult(
        context_blurb="This element supports material property lookup.",
        semantic_description="It expresses design values used in concrete calculations.",
    )


@pytest.mark.asyncio
async def test_contextualize_chunk_image_prompt_includes_alt_text():
    raw_json = (
        '{"context": "This figure appears in the concrete stress-strain section.", '
        '"description": "A figure showing the parabola-rectangle diagram for concrete."}'
    )
    create = AsyncMock(return_value=_chat_response(raw_json))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    request = ContextualizeRequest(
        doc_summary="Document summary.",
        parent_section_text="Parent section text.",
        chunk_content="![Figure 3.3](images/figure-3-3.png)",
        chunk_kind="image",
        section_path=["Section 3", "3.1.7 Stress-strain relations"],
        chunk_alt="Figure 3.3: Parabola-rectangle diagram for concrete under compression.",
    )

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig())
        result = await contextualizer.contextualize_chunk(request)

    assert result.semantic_description.startswith("A figure showing")
    prompt = create.await_args.kwargs["messages"][0]["content"]
    assert "Image alt text: Figure 3.3: Parabola-rectangle diagram" in prompt


@pytest.mark.asyncio
async def test_contextualize_chunk_json_parse_fallback():
    raw = "This table gives concrete strength classes in context."
    create = AsyncMock(return_value=_chat_response(raw))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    request = ContextualizeRequest(
        doc_summary="Document summary.",
        parent_section_text="Parent section text.",
        chunk_content="Table content.",
        chunk_kind="table",
        section_path=["Section 3"],
    )

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig())
        with capture_logs() as logs:
            result = await contextualizer.contextualize_chunk(request)

    assert result == ContextualizeResult(context_blurb=raw, semantic_description="")
    assert any(
        log["event"] == "contextualize_json_parse_failed"
        and log["chunk_id"] == "unknown"
        and log["raw"] == raw
        for log in logs
    )
```

- [ ] **Step 2: Run tests and expect failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py -q
```

Expected output:

```text
FFF
E   ValueError: Unsupported chunk kind: table
```

- [ ] **Step 3: Implement table/formula/image handling with JSON fallback**

Merge this import and code into `pipeline/contextualizer.py`:

```python
import json


    async def contextualize_chunk(self, request: ContextualizeRequest) -> ContextualizeResult:
        if request.chunk_kind == "text":
            return await self._contextualize_text_chunk(request)
        if request.chunk_kind in {"table", "formula", "image"}:
            return await self._contextualize_special_chunk(request)
        raise ValueError(f"Unsupported chunk kind: {request.chunk_kind}")

    async def _contextualize_special_chunk(self, request: ContextualizeRequest) -> ContextualizeResult:
        image_alt = ""
        if request.chunk_kind == "image" and request.chunk_alt:
            image_alt = f"\nImage alt text: {request.chunk_alt}"

        prompt = (
            f"Document summary: {request.doc_summary}\n"
            f"Section path: {' > '.join(request.section_path)}\n"
            f"Section containing the element:\n{request.parent_section_text}\n\n"
            f"The element ({request.chunk_kind}) to situate:\n{request.chunk_content}"
            f"{image_alt}\n\n"
            "Respond with a JSON object exactly matching this schema:\n"
            "{\n"
            '  "context": "1-2 sentence context situating this element within the document",\n'
            f'  "description": "natural-language description of what this {request.chunk_kind} expresses '
            '(factors, formula meaning, figure subject, etc.)"\n'
            "}\n"
            "Output only the JSON, no preamble."
        )
        raw = await self._call_llm(prompt, max_tokens=500)
        try:
            payload = json.loads(raw)
            return ContextualizeResult(
                context_blurb=str(payload.get("context", "")).strip(),
                semantic_description=str(payload.get("description", "")).strip(),
            )
        except json.JSONDecodeError:
            logger.warning(
                "contextualize_json_parse_failed",
                chunk_id="unknown",
                raw=raw[:200],
            )
            return ContextualizeResult(context_blurb=raw.strip(), semantic_description="")
```

- [ ] **Step 4: Re-run contextualizer and outline tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualizer.py tests/pipeline/test_outline_builder.py -q
```

Expected output:

```text
.................                                                        [100%]
17 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/contextualizer.py tests/pipeline/test_contextualizer.py
git commit -m "feat(contextualizer): add contextualize_chunk special path with JSON fallback"
```

Expected output:

```text
[feature/contextual-retrieval
```

### Task 7: Refactor summarize.py → contextualize.py + enrich_chunks main flow

Files:
- Rename `pipeline/summarize.py` → `pipeline/contextualize.py`
- Create `tests/pipeline/test_contextualize_stage.py`
- Delete `tests/pipeline/test_summarize.py`

- [ ] **Step 1: Add failing stage tests**

Create `tests/pipeline/test_contextualize_stage.py` with:

```python
"""Tests for Stage 3.5 contextual chunk enrichment."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from structlog.testing import capture_logs

from pipeline.config import PipelineConfig
from pipeline.contextualize import build_embedding_text, enrich_chunks
from pipeline.contextualizer import ContextualizeResult
from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _chunk(
    chunk_id: str,
    content: str,
    element_type: ElementType,
    *,
    parent_chunk_id: str | None = None,
    parent_text_chunk_id: str | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source="EN 1992-1-1:2004",
            source_title="Design of concrete structures",
            section_path=["Section 3", "3.2 Concrete"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=[],
            element_type=element_type,
            parent_chunk_id=parent_chunk_id,
            parent_text_chunk_id=parent_text_chunk_id,
            object_label="Figure 3.3" if element_type == ElementType.IMAGE else "",
        ),
    )


@pytest.fixture
def stage_chunks() -> list[Chunk]:
    parent = _chunk("parent-1", "Parent section text.", ElementType.TEXT)
    text_1 = _chunk("text-1", "First text chunk.", ElementType.TEXT, parent_chunk_id="parent-1")
    text_2 = _chunk("text-2", "Second text chunk.", ElementType.TEXT, parent_chunk_id="parent-1")
    table = _chunk("table-1", "<table><tr><td>fck</td></tr></table>", ElementType.TABLE, parent_text_chunk_id="parent-1")
    formula = _chunk("formula-1", "$$f_cd = alpha_cc f_ck / gamma_c$$", ElementType.FORMULA, parent_text_chunk_id="parent-1")
    image = _chunk("image-1", "![Figure 3.3](images/figure-3-3.png)", ElementType.IMAGE, parent_text_chunk_id="parent-1")
    return [parent, text_1, text_2, table, formula, image]


@pytest.fixture
def document_tree() -> DocumentNode:
    return DocumentNode(
        title="root",
        source="EN 1992-1-1:2004",
        children=[
            DocumentNode(
                title="Section 3 Materials",
                content="Concrete material properties.",
                element_type=StructElementType.SECTION,
                source="EN 1992-1-1:2004",
            )
        ],
    )


def _result_for_kind(kind: str) -> ContextualizeResult:
    if kind == "text":
        return ContextualizeResult(context_blurb="text context", semantic_description="")
    return ContextualizeResult(context_blurb=f"{kind} context", semantic_description=f"{kind} description")


@pytest.mark.asyncio
async def test_enrich_chunks_contextualizes_all_chunks_and_preserves_content(stage_chunks, document_tree):
    original_content = {chunk.chunk_id: chunk.content for chunk in stage_chunks}
    progress_events: list[dict] = []

    async def fake_contextualize_chunk(request):
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        enriched = await enrich_chunks(
            stage_chunks,
            PipelineConfig(contextualize_concurrency=2),
            tree=document_tree,
            progress_callback=progress_events.append,
        )

    assert enriched is stage_chunks
    assert instance.generate_doc_summary.await_count == 1
    assert instance.contextualize_chunk.await_count == len(stage_chunks)
    assert len(progress_events) == len(stage_chunks)
    for chunk in enriched:
        assert chunk.content == original_content[chunk.chunk_id]
        if chunk.metadata.element_type == ElementType.TEXT:
            assert chunk.embedding_text.startswith("[CTX] text context\n\n")
            assert chunk.embedding_text.endswith(chunk.content)
        else:
            kind = chunk.metadata.element_type.value
            assert chunk.embedding_text == f"[CTX] {kind} context\n\n[DESC] {kind} description"


@pytest.mark.asyncio
async def test_enrich_chunks_single_chunk_failure_keeps_raw_embedding(stage_chunks, document_tree):
    async def fake_contextualize_chunk(request):
        if request.chunk_content == "First text chunk.":
            raise RuntimeError("llm failed")
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        with capture_logs() as logs:
            enriched = await enrich_chunks(stage_chunks, PipelineConfig(), tree=document_tree)

    failed = next(chunk for chunk in enriched if chunk.chunk_id == "text-1")
    assert failed.embedding_text == "First text chunk."
    assert any(log["event"] == "contextualize_failed" and log["chunk_id"] == "text-1" for log in logs)


@pytest.mark.asyncio
async def test_enrich_chunks_doc_summary_failure_propagates(stage_chunks, document_tree):
    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(side_effect=RuntimeError("summary failed"))
        with pytest.raises(RuntimeError, match="summary failed"):
            await enrich_chunks(stage_chunks, PipelineConfig(), tree=document_tree)


def test_build_embedding_text_text_chunk():
    chunk = _chunk("text-1", "Raw text chunk.", ElementType.TEXT)
    result = ContextualizeResult(context_blurb="context", semantic_description="")

    assert build_embedding_text(chunk, result) == "[CTX] context\n\nRaw text chunk."


def test_build_embedding_text_special_chunk():
    chunk = _chunk("table-1", "<table></table>", ElementType.TABLE)
    result = ContextualizeResult(context_blurb="context", semantic_description="description")

    assert build_embedding_text(chunk, result) == "[CTX] context\n\n[DESC] description"
```

- [ ] **Step 2: Run tests and expect missing-module failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_contextualize_stage.py -q
```

Expected output:

```text
ERROR tests/pipeline/test_contextualize_stage.py
E   ModuleNotFoundError: No module named 'pipeline.contextualize'
```

- [ ] **Step 3: Rename summarize.py and implement enrich_chunks**

Run the rename:

```bash
cd /Users/youngz/webdav/Euro_QA && git mv pipeline/summarize.py pipeline/contextualize.py
```

Expected output:

```text
```

Replace `pipeline/contextualize.py` with:

```python
"""Stage 3.5 contextual retrieval enrichment."""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog

from pipeline.config import PipelineConfig
from pipeline.contextualizer import (
    ContextualizeRequest,
    ContextualizeResult,
    Contextualizer,
    build_outline_from_tree,
)
from pipeline.structure import DocumentNode
from server.models.schemas import Chunk, ElementType

logger = structlog.get_logger()


async def enrich_chunks(
    chunks: list[Chunk],
    config: PipelineConfig | None = None,
    *,
    tree: DocumentNode | None = None,
    progress_callback: Callable[[dict], Awaitable[None] | None] | None = None,
) -> list[Chunk]:
    """Contextualize all chunks and write into embedding_text."""
    if not chunks:
        return chunks

    cfg = config or PipelineConfig()
    contextualizer = Contextualizer(cfg)
    chunks_by_source: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_source[chunk.metadata.source].append(chunk)

    for source, source_chunks in chunks_by_source.items():
        source_title = source_chunks[0].metadata.source_title or source
        outline_text = build_outline_from_tree(tree) if tree is not None else _build_outline_from_chunks(source_chunks)
        doc_summary = await contextualizer.generate_doc_summary(
            source_title=source_title,
            doc_outline_text=outline_text,
        )
        await _contextualize_source_chunks(
            source_chunks,
            contextualizer,
            cfg,
            doc_summary,
            progress_callback,
        )

    return chunks


async def _contextualize_source_chunks(
    chunks: list[Chunk],
    contextualizer: Contextualizer,
    config: PipelineConfig,
    doc_summary: str,
    progress_callback: Callable[[dict], Awaitable[None] | None] | None,
) -> None:
    semaphore = asyncio.Semaphore(max(1, config.contextualize_concurrency))
    chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
    total = len(chunks)
    completed = 0

    async def _one(chunk: Chunk) -> ContextualizeResult:
        async with semaphore:
            request = _build_request(chunk, chunk_lookup, doc_summary)
            return await contextualizer.contextualize_chunk(request)

    results = await asyncio.gather(*(_one(chunk) for chunk in chunks), return_exceptions=True)

    for chunk, result in zip(chunks, results):
        completed += 1
        if isinstance(result, Exception):
            logger.warning(
                "contextualize_failed",
                chunk_id=chunk.chunk_id,
                element_type=chunk.metadata.element_type.value,
                section_path=chunk.metadata.section_path,
                exc=str(result),
            )
        else:
            chunk.embedding_text = build_embedding_text(chunk, result)

        if progress_callback is not None:
            payload = {
                "completed": completed,
                "total": total,
                "chunk_id": chunk.chunk_id,
                "element_type": chunk.metadata.element_type.value,
                "section_path": chunk.metadata.section_path,
            }
            callback_result = progress_callback(payload)
            if isinstance(callback_result, Awaitable):
                await callback_result


def build_embedding_text(chunk: Chunk, result: ContextualizeResult) -> str:
    """Build the final embedding_text string."""
    if chunk.metadata.element_type == ElementType.TEXT:
        return f"[CTX] {result.context_blurb}\n\n{chunk.content}"
    return f"[CTX] {result.context_blurb}\n\n[DESC] {result.semantic_description}"


def _build_request(
    chunk: Chunk,
    chunk_lookup: dict[str, Chunk],
    doc_summary: str,
) -> ContextualizeRequest:
    return ContextualizeRequest(
        doc_summary=doc_summary,
        parent_section_text=_resolve_parent_section_text(chunk, chunk_lookup),
        chunk_content=chunk.content,
        chunk_kind=chunk.metadata.element_type.value,
        section_path=chunk.metadata.section_path,
        chunk_alt=_extract_alt_if_image(chunk),
    )


def _resolve_parent_section_text(chunk: Chunk, chunk_lookup: dict[str, Chunk]) -> str:
    if chunk.metadata.element_type == ElementType.TEXT:
        parent_id = chunk.metadata.parent_chunk_id
        if parent_id and parent_id in chunk_lookup:
            return chunk_lookup[parent_id].content
        return chunk.content

    parent_text_chunk_id = chunk.metadata.parent_text_chunk_id
    if parent_text_chunk_id and parent_text_chunk_id in chunk_lookup:
        return chunk_lookup[parent_text_chunk_id].content
    return chunk.content


def _extract_alt_if_image(chunk: Chunk) -> str:
    if chunk.metadata.element_type != ElementType.IMAGE:
        return ""
    match = re.search(r"!\[([^\]]*)\]\([^)]+\)", chunk.content)
    if match:
        return match.group(1).strip()
    return chunk.metadata.object_label


def _build_outline_from_chunks(chunks: list[Chunk]) -> str:
    seen: set[tuple[str, ...]] = set()
    lines: list[str] = []
    for chunk in chunks:
        path = tuple(chunk.metadata.section_path)
        if not path or path in seen:
            continue
        seen.add(path)
        depth = max(0, len(path) - 1)
        lines.append(f"{'  ' * depth}{path[-1]}")
    return "\n".join(lines)
```

Delete the superseded test file:

```bash
cd /Users/youngz/webdav/Euro_QA && git rm tests/pipeline/test_summarize.py
```

Expected output:

```text
rm 'tests/pipeline/test_summarize.py'
```

- [ ] **Step 4: Re-run pipeline tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_config.py tests/pipeline/test_contextualizer.py tests/pipeline/test_outline_builder.py tests/pipeline/test_contextualize_stage.py -q
```

Expected output:

```text
........................                                                 [100%]
24 passed
```

Also run the broader pipeline suite:

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/ -q
```

Expected output:

```text
passed
```

- [ ] **Step 5: Commit in two commits**

```bash
git add pipeline/contextualize.py pipeline/summarize.py
git commit -m "chore: rename summarize.py to contextualize.py"
git add pipeline/contextualize.py tests/pipeline/test_contextualize_stage.py tests/pipeline/test_summarize.py
git commit -m "feat(contextualize): replace enrich_chunk_summaries with enrich_chunks"
```

Expected output:

```text
[feature/contextual-retrieval
[feature/contextual-retrieval
```

### Task 8: Wire stage 3.5 in pipeline/run.py

Files:
- Modify `pipeline/run.py`
- Create `tests/pipeline/test_run.py`
- Modify `server/services/pipeline_runner.py`
- Modify `tests/server/test_pipeline_runner.py`

- [ ] **Step 1: Add failing runner wiring tests**

Create `tests/pipeline/test_run.py` with:

```python
"""Tests for Stage 3.5 wiring in pipeline.run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import run as pipeline_run
from pipeline.config import PipelineConfig
from server.models.schemas import Chunk


@pytest.mark.asyncio
async def test_stage_3_5_calls_enrich_chunks_with_tree_and_all_chunk_progress(tmp_path: Path, monkeypatch):
    parsed_dir = tmp_path / "parsed"
    debug_dir = tmp_path / "debug"
    doc_dir = parsed_dir / "EN1992"
    doc_dir.mkdir(parents=True)
    md_path = doc_dir / "EN1992.md"
    md_path.write_text(
        "# Section 3 Materials\n\n"
        "## 3.2 Concrete\n\n"
        "Concrete text.\n\n"
        "| Class | fck |\n"
        "|---|---|\n"
        "| C30/37 | 30 |\n",
        encoding="utf-8",
    )
    (doc_dir / "EN1992_meta.json").write_text("{}", encoding="utf-8")

    config = PipelineConfig(
        parsed_dir=str(parsed_dir),
        debug_pipeline_dir=str(debug_dir),
        tree_pruning_enabled=False,
    )
    calls: list[dict] = []

    async def fake_enrich_chunks(chunks: list[Chunk], cfg: PipelineConfig, *, tree=None, progress_callback=None):
        assert cfg is config
        assert tree is not None
        if progress_callback is not None:
            progress_callback(
                {
                    "completed": len(chunks),
                    "total": len(chunks),
                    "chunk_id": chunks[-1].chunk_id,
                    "element_type": chunks[-1].metadata.element_type.value,
                    "section_path": chunks[-1].metadata.section_path,
                }
            )
        calls.append({"chunks": chunks, "tree": tree})
        return chunks

    async def fake_index_to_milvus(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    monkeypatch.setattr(pipeline_run, "enrich_chunks", fake_enrich_chunks)
    monkeypatch.setattr(pipeline_run, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(pipeline_run, "index_to_elasticsearch", fake_index_to_elasticsearch)

    await pipeline_run._run_pipeline(config, start_stage=2)

    assert len(calls) == 1
    chunks = calls[0]["chunks"]
    run_dirs = sorted(debug_dir.iterdir())
    stage_file = next(run_dirs[-1].glob("artifacts/*/stage_3_5/stage.json"))
    payload = json.loads(stage_file.read_text(encoding="utf-8"))
    assert payload["summary"]["total_all_chunks"] == len(chunks)
```

Append to `tests/server/test_pipeline_runner.py`:

```python
    monkeypatch.setattr(pipeline_runner, "enrich_chunks", fake_enrich)
```

and remove the old monkeypatch line targeting `enrich_chunk_summaries`.

- [ ] **Step 2: Run tests and expect failure**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_run.py tests/server/test_pipeline_runner.py -q
```

Expected output:

```text
E   AttributeError: module 'pipeline.run' has no attribute 'enrich_chunks'
```

- [ ] **Step 3: Update run.py and single-document runner imports/call sites**

In `pipeline/run.py`, replace the stale import and Stage 3.5 block with:

```python
from pipeline.contextualize import enrich_chunks
```

```python
                # Stage 3.5: contextual retrieval enrichment
                if start_stage <= 3.5:
                    if start_stage > 3 and all_chunks:
                        chunks = [c for c in all_chunks if c.metadata.source == source_name]

                    all_chunk_count = len(chunks)
                    logger.info("stage_3_5_start", source=source_name, all_chunks=all_chunk_count)
                    recorder.start_stage(
                        "stage_3_5",
                        document_id=doc_id,
                        summary={"total_all_chunks": all_chunk_count, "completed": 0},
                    )

                    def _on_contextualize_progress(payload: dict) -> None:
                        logger.info(
                            "stage_3_5_progress",
                            source=source_name,
                            completed=payload["completed"],
                            total=payload["total"],
                            element_type=payload["element_type"],
                        )
                        recorder.update_stage("stage_3_5", document_id=doc_id, summary=payload)

                    chunks = await enrich_chunks(
                        chunks,
                        config,
                        tree=tree,
                        progress_callback=_on_contextualize_progress,
                    )
                    recorder.record_json_artifact(
                        document_id=doc_id,
                        stage="stage_3_5",
                        filename="stage35_chunks.json",
                        label="Enriched Chunks",
                        payload=PipelineDebugRecorder.serialize_chunks(chunks),
                    )
                    recorder.complete_stage(
                        "stage_3_5",
                        document_id=doc_id,
                        summary={"completed": all_chunk_count, "total_all_chunks": all_chunk_count},
                    )
                    logger.info("stage_3_5_done", source=source_name, all_chunks=all_chunk_count)

                    all_chunks.extend(chunks)
```

In `server/services/pipeline_runner.py`, replace the Stage 3.5 import/call with:

```python
from pipeline.contextualize import enrich_chunks
```

```python
    chunks = await enrich_chunks(chunks, config)
```

- [ ] **Step 4: Re-run runner and regression tests and expect pass**

```bash
cd /Users/youngz/webdav/Euro_QA && ./.venv/bin/python -m pytest tests/pipeline/test_run.py tests/server/test_pipeline_runner.py tests/pipeline/ -q
```

Expected output:

```text
passed
```

Then verify there are no stale references:

```bash
cd /Users/youngz/webdav/Euro_QA && rg -n "enrich_chunk_summaries|pipeline\\.summarize|special_chunks|total_special_chunks" pipeline tests server
```

Expected output:

```text
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/run.py server/services/pipeline_runner.py tests/pipeline/test_run.py tests/server/test_pipeline_runner.py
git commit -m "feat(run): wire stage 3.5 to enrich_chunks"
```

Expected output:

```text
[feature/contextual-retrieval
```

## Self-Review

### Spec coverage

- AC1 `embedding_text` shape for text chunks is covered by Task 7 `test_build_embedding_text_text_chunk` and `test_enrich_chunks_contextualizes_all_chunks_and_preserves_content`.
- AC1 special chunks using `[CTX] {context}\n\n[DESC] {description}` is covered by Task 7 `test_build_embedding_text_special_chunk`.
- AC2 `content` remains unchanged is covered by Task 7 with `original_content` assertions across all chunks.
- AC3 new-module coverage is supported by Tasks 2-7: dataclasses, outline builder, retries, text path, special path, JSON fallback, and Stage 3.5 integration all get direct tests.
- AC4 `tests/pipeline/` and runner regression are covered by Task 7 Step 4 and Task 8 Step 4.
- AC5 subjective retrieval validation remains a manual post-implementation gate; this plan intentionally stops at implementation and automated verification.
- Doc summary once per document is asserted in Task 7 via `instance.generate_doc_summary.await_count == 1`.
- Per-chunk semaphore concurrency is implemented in Task 7 by `asyncio.Semaphore(max(1, config.contextualize_concurrency))`.
- Provider switching through `LLM_BASE_URL`/`LLM_MODEL` stays within the single `AsyncOpenAI` path introduced in Task 4.

### Type consistency

- `ContextualizeRequest.doc_summary` is defined in Task 2, filled in Task 7, and consumed in Tasks 4-6.
- `ContextualizeRequest.parent_section_text` is defined in Task 2, resolved in Task 7, and used by both text and special prompts.
- `ContextualizeRequest.chunk_content` always comes from `chunk.content`.
- `ContextualizeRequest.chunk_kind` always comes from `chunk.metadata.element_type.value`, matching the literal values tested in Task 2.
- `ContextualizeRequest.section_path` always comes from `chunk.metadata.section_path`.
- `ContextualizeRequest.chunk_alt` defaults to `""` in Task 2 and is only populated for image chunks in Task 7.
- `ContextualizeResult.context_blurb` is written to `[CTX]` for all chunk kinds.
- `ContextualizeResult.semantic_description` stays `""` for text and is only written to `[DESC]` for special chunks.

### Frequent commits

- Task 1: `feat(config): add contextualize_concurrency and retry_attempts fields`
- Task 2: `feat(contextualizer): add ContextualizeRequest/Result dataclasses`
- Task 3: `feat(contextualizer): add build_outline_from_tree`
- Task 4: `feat(contextualizer): add Contextualizer.generate_doc_summary`
- Task 5: `feat(contextualizer): add contextualize_chunk text path`
- Task 6: `feat(contextualizer): add contextualize_chunk special path with JSON fallback`
- Task 7 commit 1: `chore: rename summarize.py to contextualize.py`
- Task 7 commit 2: `feat(contextualize): replace enrich_chunk_summaries with enrich_chunks`
- Task 8: `feat(run): wire stage 3.5 to enrich_chunks`

Total expected commits: 9.
