# Eurocode QA System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a RAG-based Q&A backend that lets Chinese engineers query ~40 Eurocode PDF standards in Chinese and get answers with precise source citations.

**Architecture:** Offline pipeline (MinerU PDF parse → structure → mixed chunk → embed → index into Milvus+ES) feeds an online FastAPI server (query understanding → hybrid retrieval → LLM generation). Frontend-backend separation via versioned REST API.

**Tech Stack:** Python 3.12, FastAPI, MinerU (hybrid), bge-m3, bge-reranker-v2-m3, Milvus/Qdrant, Elasticsearch, domestic LLM API (DeepSeek/Qwen), Docker Compose, uv package manager.

**Spec:** `docs/superpowers/specs/2026-03-26-eurocode-qa-system-design.md`

---

## File Structure

```
euro-qa/
├── pyproject.toml                       # uv project, all dependencies
├── docker-compose.yml                   # Milvus + ES + app
├── .env.example                         # environment variable template
├── data/
│   ├── pdfs/                            # raw Eurocode PDFs
│   ├── parsed/                          # MinerU output (per-PDF subdirs)
│   └── glossary.json                    # CN-EN terminology mapping
├── pipeline/
│   ├── __init__.py
│   ├── config.py                        # pipeline configuration (paths, MinerU URL, LLM config)
│   ├── parse.py                         # Stage 1: MinerU API client
│   ├── structure.py                     # Stage 2: Markdown → structured document tree
│   ├── chunk.py                         # Stage 3: mixed chunking (parent-child + independent)
│   ├── summarize.py                     # Stage 3.5: LLM summaries for tables/formulas
│   ├── index.py                         # Stage 4: bge-m3 embedding + Milvus + ES indexing
│   └── run.py                           # CLI entrypoint for full pipeline
├── server/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app factory + lifespan
│   ├── config.py                        # server configuration (LLM keys, DB URLs)
│   ├── deps.py                          # FastAPI dependency injection
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py                # v1 router aggregator
│   │       ├── query.py                 # POST /query, /query/stream
│   │       ├── documents.py             # GET /documents, /documents/{id}/page/{n}
│   │       └── glossary.py              # GET /glossary, /suggest
│   ├── core/
│   │   ├── __init__.py
│   │   ├── query_understanding.py       # intent classification + query rewrite
│   │   ├── retrieval.py                 # hybrid search + rerank + parent retrieval
│   │   ├── generation.py                # prompt assembly + LLM call + structured output
│   │   └── conversation.py              # conversation state (TTL cache)
│   └── models/
│       ├── __init__.py
│       └── schemas.py                   # Pydantic models: QueryRequest, QueryResponse, Source, Chunk
├── tests/
│   ├── conftest.py                      # shared fixtures
│   ├── pipeline/
│   │   ├── test_structure.py
│   │   ├── test_chunk.py
│   │   └── test_summarize.py
│   └── server/
│       ├── test_query_understanding.py
│       ├── test_retrieval.py
│       ├── test_generation.py
│       └── test_api.py
└── docs/
    └── superpowers/
        ├── specs/                       # design spec (already exists)
        └── plans/                       # this plan
```

---

## Task 1: Project Scaffolding + Dependencies

**Files:**
- Create: `pyproject.toml` (overwrite existing skeleton)
- Create: `.env.example`
- Create: `server/models/schemas.py`
- Create: `pipeline/config.py`
- Create: `server/config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Update pyproject.toml with all dependencies**

```toml
[project]
name = "euro-qa"
version = "0.1.0"
description = "Eurocode standards Q&A system for Chinese engineers"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # 后端框架
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-multipart>=0.0.9",
    "sse-starlette>=2.0",
    # LLM 客户端
    "openai>=1.50",
    "httpx>=0.27",
    # Embedding + Reranker
    "FlagEmbedding>=1.2",
    # 向量库
    "pymilvus>=2.4",
    # Elasticsearch
    "elasticsearch[async]>=8.0",
    # PDF 处理
    "pymupdf>=1.24",
    # 工具
    "tiktoken>=0.7",
    "cachetools>=5.3",
    "python-dotenv>=1.0",
    "structlog>=24.0",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "httpx>=0.27",
    "ruff>=0.6",
]

[project.scripts]
euro-pipeline = "pipeline.run:main"
```

- [ ] **Step 2: Create .env.example**

```env
# LLM
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# MinerU
MINERU_API_URL=http://localhost:8000

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Elasticsearch
ES_URL=http://localhost:9200

# Paths
PDF_DIR=data/pdfs
PARSED_DIR=data/parsed
GLOSSARY_PATH=data/glossary.json
```

- [ ] **Step 3: Create Pydantic data models (schemas.py)**

```python
"""Pydantic 数据模型：请求/响应/内部数据结构"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ElementType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    IMAGE = "image"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class QueryType(str, Enum):
    CONCEPT = "concept"
    CLAUSE = "clause"
    PARAMETER = "parameter"
    COMPARISON = "comparison"


class IntentType(str, Enum):
    EXACT = "exact"
    CONCEPT = "concept"
    REASONING = "reasoning"


# --- Chunk 数据模型 ---

class ChunkMetadata(BaseModel):
    """存储在向量库/ES 中的 chunk 元数据"""
    source: str                              # "EN 1990:2002"
    source_title: str                        # "Eurocode - Basis of structural design"
    section_path: list[str]                  # ["Section 2", "2.3 Design working life"]
    page_numbers: list[int]                  # 视觉页码(1-based)
    page_file_index: list[int]               # PDF 文件内页码(0-based)
    clause_ids: list[str]                    # ["2.3(1)"]
    element_type: ElementType
    cross_refs: list[str] = []               # ["Annex A", "EN 1992"]
    parent_chunk_id: Optional[str] = None    # 章节级 parent
    parent_text_chunk_id: Optional[str] = None  # 所在文本 chunk


class Chunk(BaseModel):
    """完整的 chunk 数据（含内容和元数据）"""
    chunk_id: str
    content: str                             # 原始内容（文本/HTML表格/LaTeX公式）
    embedding_text: str                      # 用于 embedding 的文本（可能是摘要）
    metadata: ChunkMetadata


# --- API 请求/响应 ---

class QueryRequest(BaseModel):
    question: str = Field(..., max_length=500)
    domain: Optional[str] = None
    query_type: Optional[QueryType] = None
    conversation_id: Optional[str] = None
    stream: bool = False


class Source(BaseModel):
    file: str
    title: str
    section: str
    page: int
    clause: str
    original_text: str = Field(..., max_length=1000)
    translation: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list, max_length=5)
    related_refs: list[str] = []
    confidence: Confidence
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    degraded: bool = False


class DocumentInfo(BaseModel):
    id: str
    name: str                                # "EN 1990:2002"
    title: str
    total_pages: int
    chunk_count: int


class GlossaryEntry(BaseModel):
    zh: list[str]                            # ["设计使用年限", "设计寿命"]
    en: str                                  # "design working life"
    verified: bool = True
```

- [ ] **Step 4: Create pipeline/config.py and server/config.py**

`pipeline/config.py`:
```python
"""离线管线配置"""
from pydantic_settings import BaseSettings


class PipelineConfig(BaseSettings):
    model_config = {"env_prefix": ""}

    # MinerU
    mineru_api_url: str = "http://localhost:8000"
    mineru_backend: str = "hybrid-http-client"

    # LLM（用于生成表格/公式摘要）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    # Elasticsearch
    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    # 路径
    pdf_dir: str = "data/pdfs"
    parsed_dir: str = "data/parsed"
    glossary_path: str = "data/glossary.json"

    # 分块参数
    child_chunk_max_tokens: int = 800
    child_chunk_min_tokens: int = 100
    parent_chunk_max_tokens: int = 4000
    long_subsection_threshold: int = 1500
    formula_group_threshold: int = 5
```

`server/config.py`:
```python
"""后端服务配置"""
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_prefix": ""}

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    # Elasticsearch
    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    # 检索参数
    vector_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_n: int = 5
    max_context_tokens: int = 3000

    # 会话
    conversation_ttl_hours: int = 24
    max_conversation_rounds: int = 3

    # 路径
    glossary_path: str = "data/glossary.json"
    pdf_dir: str = "data/pdfs"
```

- [ ] **Step 5: Create tests/conftest.py**

```python
"""共享测试 fixtures"""
import pytest

from server.models.schemas import Chunk, ChunkMetadata, ElementType


@pytest.fixture
def sample_text_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk_023",
        content=(
            "2.3 Design working life\n"
            "(1) The design working life should be specified.\n"
            "NOTE Indicative categories are given in Table 2.1.\n"
            "[-> Table 2.1 - Indicative design working life]"
        ),
        embedding_text=(
            "2.3 Design working life. The design working life should be specified. "
            "Indicative categories are given in Table 2.1."
        ),
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Eurocode - Basis of structural design",
            section_path=["Section 2 Requirements", "2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["2.3(1)"],
            element_type=ElementType.TEXT,
            cross_refs=["Annex A"],
            parent_chunk_id="chunk_section_2",
        ),
    )


@pytest.fixture
def sample_table_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk_t_2_1",
        content=(
            "Table 2.1 - Indicative design working life\n"
            "| Category | Years | Examples |\n"
            "|1|10|Temporary structures|\n"
            "|2|10-25|Replaceable structural parts|\n"
            "|3|15-30|Agricultural and similar structures|\n"
            "|4|50|Building structures and other common structures|\n"
            "|5|100|Monumental building structures, bridges, "
            "and other civil engineering structures|"
        ),
        embedding_text=(
            "Table 2.1 设计使用年限分为5类: "
            "临时结构10年, 可更换构件10-25年, 农业建筑15-30年, "
            "普通建筑50年, 重大基础设施(桥梁等)100年。"
            "Section: 2.3 Design working life"
        ),
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Eurocode - Basis of structural design",
            section_path=["Section 2 Requirements", "2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["Table 2.1"],
            element_type=ElementType.TABLE,
            cross_refs=[],
            parent_text_chunk_id="chunk_023",
        ),
    )
```

- [ ] **Step 6: Install dependencies and verify**

Run: `uv sync && uv sync --group dev`
Expected: all dependencies installed successfully

- [ ] **Step 7: Create directory structure + __init__.py files**

```bash
mkdir -p data/pdfs data/parsed
mkdir -p pipeline server/api/v1 server/core server/models tests/pipeline tests/server
touch pipeline/__init__.py server/__init__.py server/api/__init__.py
touch server/api/v1/__init__.py server/core/__init__.py server/models/__init__.py
touch tests/__init__.py tests/pipeline/__init__.py tests/server/__init__.py
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with dependencies, data models, and config"
```

---

## Task 2: Pipeline Stage 2 — Structure Parser

> Stage 1 (MinerU parsing) depends on external MinerU API. We build Stage 2 first because it's pure logic and testable with static Markdown input. Stage 1 will be a thin API client wrapper added in Task 4.

**Files:**
- Create: `pipeline/structure.py`
- Create: `tests/pipeline/test_structure.py`

- [ ] **Step 1: Write failing tests for structure parser**

```python
"""测试 Markdown → 结构化文档树"""
import pytest

from pipeline.structure import (
    DocumentNode,
    ElementType,
    parse_markdown_to_tree,
    extract_cross_refs,
)


class TestParseMarkdownToTree:
    def test_basic_section_hierarchy(self):
        md = (
            "# Section 1 General\n\n"
            "## 1.1 Scope\n\n"
            "(1) EN 1990 establishes Principles and requirements.\n\n"
            "(2) EN 1990 is intended to be used in conjunction.\n\n"
            "## 1.2 Normative references\n\n"
            "This European Standard incorporates...\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        # 顶层应该有一个 Section
        assert len(tree.children) == 1
        section = tree.children[0]
        assert "Section 1" in section.title
        # 下面有两个 Subsection
        assert len(section.children) == 2
        assert "1.1" in section.children[0].title
        assert "1.2" in section.children[1].title

    def test_table_detection(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "| Category | Years | Examples |\n"
            "|---|---|---|\n"
            "|1|10|Temporary|\n"
            "|5|100|Bridges|\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        subsection = tree.children[0]
        # 应该检测到一个表格子节点
        tables = [c for c in subsection.children if c.element_type == ElementType.TABLE]
        assert len(tables) == 1

    def test_formula_detection(self):
        md = (
            "## 6.3.5 Design resistance\n\n"
            "(1) The design resistance Rd:\n\n"
            "$$R_d = \\frac{1}{\\gamma_{Rd}} R\\{X_{d,i}; a_d\\}$$\n\n"
            "where:\n\n"
            "- $\\gamma_{Rd}$ is a partial factor\n"
            "- $X_{d,i}$ is the design value\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        subsection = tree.children[0]
        formulas = [c for c in subsection.children if c.element_type == ElementType.FORMULA]
        assert len(formulas) == 1
        # 公式节点应该包含 where 定义块
        assert "gamma_{Rd}" in formulas[0].content

    def test_image_detection(self):
        md = (
            "## 3.1 Overview\n\n"
            "![Figure 3.1](images/figure_3_1.png)\n\n"
            "Some text after image.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        images = [c for c in tree.children[0].children if c.element_type == ElementType.IMAGE]
        assert len(images) == 1


class TestExtractCrossRefs:
    def test_extract_en_references(self):
        text = "See also EN 1991-1-2 and EN 1992 for details."
        refs = extract_cross_refs(text)
        assert "EN 1991-1-2" in refs
        assert "EN 1992" in refs

    def test_extract_annex_references(self):
        text = "See Annex A and Annex B3 for more."
        refs = extract_cross_refs(text)
        assert "Annex A" in refs
        assert "Annex B3" in refs

    def test_no_refs(self):
        text = "A simple paragraph with no references."
        refs = extract_cross_refs(text)
        assert refs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline/test_structure.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement structure.py**

```python
"""Stage 2: Markdown → 结构化文档树

将 MinerU 输出的 Markdown 解析为层级文档树，
识别章节/小节/条款，标记表格/公式/图片元素。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ElementType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    IMAGE = "image"
    SECTION = "section"


@dataclass
class DocumentNode:
    """文档树节点"""
    title: str
    content: str = ""
    element_type: ElementType = ElementType.SECTION
    level: int = 0                           # heading level (1=Section, 2=Subsection, ...)
    page_numbers: list[int] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    children: list[DocumentNode] = field(default_factory=list)
    source: str = ""


# --- 正则模式 ---
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_TABLE_RE = re.compile(r"(\|.+\|[\s\S]*?\n)(?=\n[^|]|\Z)")
_FORMULA_BLOCK_RE = re.compile(r"\$\$[\s\S]+?\$\$")
_FORMULA_WHERE_RE = re.compile(
    r"(\$\$[\s\S]+?\$\$[\s\S]*?)((?:where|Where)[\s\S]*?)(?=\n\n\(|\n\n#{1,4}|\Z)"
)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_CLAUSE_ID_RE = re.compile(r"\((\d+)\)")
_EN_REF_RE = re.compile(r"EN\s+\d{4}(?:-\d+-\d+|-\d+)?")
_ANNEX_REF_RE = re.compile(r"Annex\s+[A-Z]\d*")


def extract_cross_refs(text: str) -> list[str]:
    """从文本中提取交叉引用（EN 标准 + Annex）"""
    refs: list[str] = []
    for m in _EN_REF_RE.finditer(text):
        ref = m.group().replace("  ", " ")
        if ref not in refs:
            refs.append(ref)
    for m in _ANNEX_REF_RE.finditer(text):
        ref = m.group()
        if ref not in refs:
            refs.append(ref)
    return refs


def _split_special_elements(text: str) -> list[DocumentNode]:
    """从小节文本中分离出表格/公式/图片为独立节点"""
    nodes: list[DocumentNode] = []

    # 检测图片
    for m in _IMAGE_RE.finditer(text):
        nodes.append(DocumentNode(
            title=m.group(1) or "Image",
            content=m.group(0),
            element_type=ElementType.IMAGE,
        ))

    # 检测公式（含 where 块）
    for m in _FORMULA_WHERE_RE.finditer(text):
        nodes.append(DocumentNode(
            title="Formula",
            content=m.group(0).strip(),
            element_type=ElementType.FORMULA,
            cross_refs=extract_cross_refs(m.group(0)),
        ))

    # 如果没有 where 块的独立公式
    if not any(n.element_type == ElementType.FORMULA for n in nodes):
        for m in _FORMULA_BLOCK_RE.finditer(text):
            nodes.append(DocumentNode(
                title="Formula",
                content=m.group(0).strip(),
                element_type=ElementType.FORMULA,
            ))

    # 检测表格
    for m in _TABLE_RE.finditer(text):
        table_text = m.group(0).strip()
        if "|" in table_text and table_text.count("\n") >= 2:
            nodes.append(DocumentNode(
                title="Table",
                content=table_text,
                element_type=ElementType.TABLE,
            ))

    return nodes


def parse_markdown_to_tree(markdown: str, source: str = "") -> DocumentNode:
    """将 Markdown 解析为结构化文档树

    Args:
        markdown: MinerU 输出的 Markdown 文本
        source: 文档标识，如 "EN 1990:2002"

    Returns:
        根节点，children 为顶层章节
    """
    root = DocumentNode(title="root", source=source, level=0)
    stack: list[DocumentNode] = [root]

    # 按 heading 分割
    parts = _HEADING_RE.split(markdown)

    # parts 结构: [前文, '#', 'Title1', 内容1, '##', 'Title2', 内容2, ...]
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith("#") and not part.startswith("#!"):
            level = len(part)
            title = parts[i + 1].strip() if i + 1 < len(parts) else ""
            body = parts[i + 2].strip() if i + 2 < len(parts) else ""
            i += 3

            node = DocumentNode(
                title=title,
                content=body,
                element_type=ElementType.SECTION,
                level=level,
                source=source,
                cross_refs=extract_cross_refs(body),
                clause_ids=[
                    m.group(1) for m in _CLAUSE_ID_RE.finditer(body)
                ],
            )

            # 提取特殊元素为子节点
            node.children = _split_special_elements(body)

            # 找到合适的父节点（level 比当前小的最近节点）
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)
        else:
            i += 1

    return root
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/pipeline/test_structure.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/structure.py tests/pipeline/test_structure.py
git commit -m "feat(pipeline): add structure parser - Markdown to document tree"
```

---

## Task 3: Pipeline Stage 3 — Mixed Chunker

**Files:**
- Create: `pipeline/chunk.py`
- Create: `tests/pipeline/test_chunk.py`

- [ ] **Step 1: Write failing tests for chunker**

```python
"""测试混合分块策略"""
import pytest

from pipeline.chunk import create_chunks
from pipeline.structure import DocumentNode, ElementType, parse_markdown_to_tree
from server.models.schemas import Chunk, ElementType as ChunkElementType


class TestCreateChunks:
    def _make_tree(self, md: str) -> DocumentNode:
        return parse_markdown_to_tree(md, source="EN 1990:2002")

    def test_text_parent_child_chunks(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.1 Basic requirements\n\n"
            "(1)P A structure shall be designed and executed.\n\n"
            "(2)P A structure shall have adequate resistance.\n\n"
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        # 应该有 child chunks (小节级) + parent chunk (章节级)
        children = [c for c in chunks if c.metadata.parent_chunk_id is not None]
        parents = [c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
                   and c.metadata.parent_chunk_id is None
                   and "Section" in c.metadata.section_path[0]]
        assert len(children) >= 2  # 2.1 和 2.3
        assert len(parents) >= 1   # Section 2

    def test_table_independent_chunk(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "| Category | Years | Examples |\n"
            "|---|---|---|\n"
            "|1|10|Temporary|\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        table_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TABLE]
        assert len(table_chunks) == 1
        # 表格 chunk 应该关联回文本 chunk
        assert table_chunks[0].metadata.parent_text_chunk_id is not None

    def test_text_chunk_has_placeholder_for_table(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "| Category | Years | Examples |\n"
            "|---|---|---|\n"
            "|1|10|Temporary|\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        text_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT]
        # 文本 chunk 里表格内容应该被替换为占位符
        for tc in text_chunks:
            assert "|" not in tc.content or "[-> Table" in tc.content or "Category" not in tc.content

    def test_formula_independent_chunk(self):
        md = (
            "## 6.3 Design values\n\n"
            "(1) The design resistance:\n\n"
            "$$R_d = \\frac{1}{\\gamma_{Rd}} R\\{X_{d,i}\\}$$\n\n"
            "where:\n\n"
            "- $\\gamma_{Rd}$ is a partial factor\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        formula_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.FORMULA]
        assert len(formula_chunks) == 1
        assert "gamma_{Rd}" in formula_chunks[0].content

    def test_metadata_completeness(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.1 Basic requirements\n\n"
            "(1) A structure shall be designed. See also EN 1991-1-2.\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        child = [c for c in chunks if "2.1" in str(c.metadata.section_path)]
        assert len(child) >= 1
        meta = child[0].metadata
        assert meta.source == "EN 1990:2002"
        assert meta.source_title == "Basis of structural design"
        assert len(meta.section_path) >= 2
        assert "EN 1991-1-2" in meta.cross_refs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline/test_chunk.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chunk.py**

```python
"""Stage 3: 混合分块

纯文本 → 父子分块（小节 child + 章节 parent）
表格/公式/图片 → 独立分块 + 占位符
"""
from __future__ import annotations

import hashlib
import re

from pipeline.structure import DocumentNode, ElementType as StructElementType
from server.models.schemas import (
    Chunk,
    ChunkMetadata,
    ElementType,
)

# 默认阈值（可被 PipelineConfig 覆盖）
_CHILD_MAX_TOKENS = 800
_CHILD_MIN_TOKENS = 100
_PARENT_MAX_TOKENS = 4000
_LONG_SUBSECTION = 1500


def _estimate_tokens(text: str) -> int:
    """粗略估计 token 数（中英混合，1 token ≈ 1.5 字符）"""
    return max(1, len(text) // 2)


def _make_chunk_id(source: str, section: str, suffix: str = "") -> str:
    raw = f"{source}::{section}::{suffix}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _strip_special_elements(text: str) -> tuple[str, list[str]]:
    """从文本中移除表格/公式/图片，返回清洁文本和占位符列表"""
    placeholders: list[str] = []

    # 移除公式块（含 where）
    def _replace_formula(m: re.Match) -> str:
        placeholders.append("[-> Formula]")
        return "[-> Formula]\n"

    text = re.sub(
        r"\$\$[\s\S]+?\$\$(?:[\s\S]*?(?:where|Where)[\s\S]*?)?(?=\n\n|\Z)",
        _replace_formula,
        text,
    )

    # 移除独立公式
    text = re.sub(r"\$\$[\s\S]+?\$\$", lambda m: "[-> Formula]\n", text)

    # 移除表格
    def _replace_table(m: re.Match) -> str:
        placeholders.append("[-> Table]")
        return "[-> Table]\n"

    text = re.sub(r"\|.+\|[\s\S]*?\n(?=\n[^|]|\Z)", _replace_table, text)

    # 移除图片
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", lambda m: "[-> Image]\n", text)

    return text.strip(), placeholders


def _split_by_clauses(text: str) -> list[str]:
    """按条款编号 (1) (2) 切分长文本"""
    parts = re.split(r"(?=\(\d+\)(?:P\s|\s))", text)
    return [p.strip() for p in parts if p.strip()]


def create_chunks(
    tree: DocumentNode,
    source_title: str = "",
) -> list[Chunk]:
    """从文档树创建混合分块

    Args:
        tree: parse_markdown_to_tree 的输出
        source_title: 文档标题

    Returns:
        所有 chunk 列表（含 text/table/formula/image 类型）
    """
    chunks: list[Chunk] = []
    source = tree.source

    def _process_section(node: DocumentNode, path: list[str]) -> list[Chunk]:
        """递归处理一个章节节点"""
        section_chunks: list[Chunk] = []
        current_path = path + [node.title]

        # 收集所有子小节（level > node.level 的直接 children）
        subsections = [c for c in node.children if c.element_type == StructElementType.SECTION]
        special_elements = [c for c in node.children if c.element_type != StructElementType.SECTION]

        # 如果当前节点是叶子小节（无子 section），创建 child chunk
        if not subsections:
            clean_text, _ = _strip_special_elements(node.content)
            if _estimate_tokens(clean_text) > _CHILD_MIN_TOKENS:
                child_id = _make_chunk_id(source, node.title, "text")
                child_chunk = Chunk(
                    chunk_id=child_id,
                    content=clean_text,
                    embedding_text=clean_text,
                    metadata=ChunkMetadata(
                        source=source,
                        source_title=source_title,
                        section_path=current_path,
                        page_numbers=node.page_numbers,
                        page_file_index=[],
                        clause_ids=node.clause_ids,
                        element_type=ElementType.TEXT,
                        cross_refs=node.cross_refs,
                        parent_chunk_id=None,  # 后面回填
                    ),
                )
                section_chunks.append(child_chunk)

                # 为特殊元素创建独立 chunk
                for elem in special_elements:
                    elem_type = ElementType(elem.element_type.value)
                    elem_id = _make_chunk_id(source, node.title, elem.element_type.value)
                    elem_chunk = Chunk(
                        chunk_id=elem_id,
                        content=elem.content,
                        embedding_text=elem.content,  # 后续被 summarize 替换
                        metadata=ChunkMetadata(
                            source=source,
                            source_title=source_title,
                            section_path=current_path,
                            page_numbers=node.page_numbers,
                            page_file_index=[],
                            clause_ids=[],
                            element_type=elem_type,
                            cross_refs=elem.cross_refs,
                            parent_text_chunk_id=child_id,
                        ),
                    )
                    section_chunks.append(elem_chunk)
        else:
            # 递归处理子小节
            for sub in subsections:
                section_chunks.extend(_process_section(sub, current_path))

        return section_chunks

    # 遍历顶层章节
    for section_node in tree.children:
        section_path = [section_node.title]
        child_chunks = _process_section(section_node, [])

        # 创建 parent chunk（章节级）
        full_text, _ = _strip_special_elements(section_node.content)
        # 收集所有子节点文本
        for child in section_node.children:
            if child.element_type == StructElementType.SECTION:
                clean, _ = _strip_special_elements(child.content)
                full_text += f"\n\n{child.title}\n{clean}"

        if _estimate_tokens(full_text) > 0:
            parent_id = _make_chunk_id(source, section_node.title, "parent")

            # 如果 parent 超限，截断
            if _estimate_tokens(full_text) > _PARENT_MAX_TOKENS:
                full_text = full_text[: _PARENT_MAX_TOKENS * 2]

            parent_chunk = Chunk(
                chunk_id=parent_id,
                content=full_text,
                embedding_text="",  # parent 不做 embedding，仅在生成时使用
                metadata=ChunkMetadata(
                    source=source,
                    source_title=source_title,
                    section_path=section_path,
                    page_numbers=section_node.page_numbers,
                    page_file_index=[],
                    clause_ids=[],
                    element_type=ElementType.TEXT,
                    cross_refs=section_node.cross_refs,
                ),
            )
            chunks.append(parent_chunk)

            # 回填 child 的 parent_chunk_id
            for c in child_chunks:
                if c.metadata.element_type == ElementType.TEXT and c.metadata.parent_chunk_id is None:
                    c.metadata.parent_chunk_id = parent_id

        chunks.extend(child_chunks)

    return chunks
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pipeline/test_chunk.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(pipeline): add mixed chunker - parent-child text + independent special elements"
```

---

## Task 4: Pipeline Stage 1 — MinerU API Client

**Files:**
- Create: `pipeline/parse.py`

- [ ] **Step 1: Implement MinerU API client**

```python
"""Stage 1: MinerU API 客户端

调用 MinerU API 将 PDF 解析为 Markdown + 元数据。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import structlog

from pipeline.config import PipelineConfig

logger = structlog.get_logger()


async def parse_pdf(
    pdf_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    """调用 MinerU API 解析单个 PDF

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录（Markdown + 图片）
        config: 管线配置

    Returns:
        输出 Markdown 文件路径
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=600.0) as client:
        # 提交解析任务
        with open(pdf_path, "rb") as f:
            resp = await client.post(
                f"{config.mineru_api_url}/api/v1/extract",
                files={"file": (pdf_path.name, f, "application/pdf")},
                data={
                    "parse_method": config.mineru_backend,
                    "is_table_recognition": "true",
                    "is_formula_recognition": "true",
                },
            )
        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        logger.info("mineru_task_submitted", pdf=pdf_path.name, task_id=task_id)

        # 轮询任务状态
        while True:
            status_resp = await client.get(
                f"{config.mineru_api_url}/api/v1/extract/{task_id}"
            )
            status_resp.raise_for_status()
            status = status_resp.json()

            if status.get("state") == "done":
                break
            if status.get("state") == "failed":
                raise RuntimeError(f"MinerU parsing failed: {status.get('error')}")

            logger.debug("mineru_polling", state=status.get("state"))
            time.sleep(5)

        # 下载结果
        result_resp = await client.get(
            f"{config.mineru_api_url}/api/v1/extract/{task_id}/result"
        )
        result_resp.raise_for_status()
        result = result_resp.json()

        # 保存 Markdown
        md_path = output_dir / f"{pdf_path.stem}.md"
        md_path.write_text(result.get("markdown", ""), encoding="utf-8")

        # 保存元数据（页码映射等）
        meta_path = output_dir / f"{pdf_path.stem}_meta.json"
        meta_path.write_text(
            json.dumps(result.get("metadata", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("mineru_parse_done", pdf=pdf_path.name, output=str(md_path))
        return md_path


async def parse_all_pdfs(config: PipelineConfig) -> list[Path]:
    """批量解析所有 PDF"""
    pdf_dir = Path(config.pdf_dir)
    parsed_dir = Path(config.parsed_dir)
    results: list[Path] = []

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        output_dir = parsed_dir / pdf_path.stem
        try:
            md_path = await parse_pdf(pdf_path, output_dir, config)
            results.append(md_path)
        except Exception:
            logger.exception("parse_failed", pdf=pdf_path.name)

    return results
```

> 注意：此模块依赖外部 MinerU API，不编写单元测试。在 Task 12 做集成测试时验证。

- [ ] **Step 2: Commit**

```bash
git add pipeline/parse.py
git commit -m "feat(pipeline): add MinerU API client for PDF parsing"
```

---

## Task 5: Pipeline Stage 3.5 — LLM Summaries for Special Elements

**Files:**
- Create: `pipeline/summarize.py`
- Create: `tests/pipeline/test_summarize.py`

- [ ] **Step 1: Write failing tests**

```python
"""测试 LLM 摘要生成（mock LLM 调用）"""
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.contextualize import generate_table_summary, generate_formula_description
from server.models.schemas import Chunk, ChunkMetadata, ElementType


@pytest.fixture
def table_chunk():
    return Chunk(
        chunk_id="t1",
        content="| Cat | Years |\n|---|---|\n|1|10|",
        embedding_text="",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=[],
            element_type=ElementType.TABLE,
        ),
    )


@pytest.mark.asyncio
async def test_generate_table_summary(table_chunk):
    mock_response = "设计使用年限分类表，临时结构10年。"
    with patch("pipeline.contextualize._call_llm", new_callable=AsyncMock, return_value=mock_response):
        result = await generate_table_summary(table_chunk)
        assert result == mock_response


@pytest.mark.asyncio
async def test_generate_formula_description():
    chunk = Chunk(
        chunk_id="f1",
        content="$$R_d = \\frac{1}{\\gamma_{Rd}} R$$\nwhere gamma is partial factor",
        embedding_text="",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["6.3.5 Design resistance"],
            page_numbers=[44],
            page_file_index=[43],
            clause_ids=[],
            element_type=ElementType.FORMULA,
        ),
    )
    mock_response = "设计抗力Rd的计算公式，考虑分项系数。"
    with patch("pipeline.contextualize._call_llm", new_callable=AsyncMock, return_value=mock_response):
        result = await generate_formula_description(chunk)
        assert result == mock_response
```

- [ ] **Step 2: Run tests to verify fail**

Run: `uv run pytest tests/pipeline/test_summarize.py -v`
Expected: FAIL

- [ ] **Step 3: Implement summarize.py**

```python
"""Stage 3.5: 为表格/公式生成自然语言摘要

用 LLM 为独立分块的特殊元素生成 embedding 文本。
"""
from __future__ import annotations

from openai import AsyncOpenAI

from pipeline.config import PipelineConfig
from server.models.schemas import Chunk, ElementType

_client: AsyncOpenAI | None = None


def _get_client(config: PipelineConfig | None = None) -> AsyncOpenAI:
    global _client
    if _client is None:
        cfg = config or PipelineConfig()
        _client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    return _client


async def _call_llm(prompt: str, config: PipelineConfig | None = None) -> str:
    client = _get_client(config)
    cfg = config or PipelineConfig()
    resp = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


async def generate_table_summary(chunk: Chunk, config: PipelineConfig | None = None) -> str:
    """为表格 chunk 生成中文自然语言摘要"""
    section_context = " > ".join(chunk.metadata.section_path)
    prompt = (
        f"以下是欧洲建筑规范 {chunk.metadata.source} 中 {section_context} 的一个表格。\n"
        f"请用简洁的中文描述表格的内容和关键数据点（100字以内）。\n\n"
        f"表格内容：\n{chunk.content}"
    )
    return await _call_llm(prompt, config)


async def generate_formula_description(chunk: Chunk, config: PipelineConfig | None = None) -> str:
    """为公式 chunk 生成中文语义描述"""
    section_context = " > ".join(chunk.metadata.section_path)
    prompt = (
        f"以下是欧洲建筑规范 {chunk.metadata.source} 中 {section_context} 的一个公式。\n"
        f"请用简洁的中文描述公式的含义和用途（100字以内）。\n\n"
        f"公式内容：\n{chunk.content}"
    )
    return await _call_llm(prompt, config)


async def enrich_chunk_summaries(
    chunks: list[Chunk],
    config: PipelineConfig | None = None,
) -> list[Chunk]:
    """为所有特殊元素 chunk 填充 embedding_text"""
    for chunk in chunks:
        if chunk.metadata.element_type == ElementType.TABLE:
            summary = await generate_table_summary(chunk, config)
            chunk.embedding_text = f"{summary} Section: {' > '.join(chunk.metadata.section_path)}"
        elif chunk.metadata.element_type == ElementType.FORMULA:
            desc = await generate_formula_description(chunk, config)
            chunk.embedding_text = f"{desc} Section: {' > '.join(chunk.metadata.section_path)}"
        elif chunk.metadata.element_type == ElementType.IMAGE:
            # 图片描述已在 MinerU 阶段生成，这里补充 section 上下文
            chunk.embedding_text = f"{chunk.content} Section: {' > '.join(chunk.metadata.section_path)}"
    return chunks
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pipeline/test_summarize.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/summarize.py tests/pipeline/test_summarize.py
git commit -m "feat(pipeline): add LLM summary generator for tables and formulas"
```

---

## Task 6: Pipeline Stage 4 — Embedding + Indexing

**Files:**
- Create: `pipeline/index.py`

- [ ] **Step 1: Implement index.py**

```python
"""Stage 4: Embedding 生成 + Milvus/ES 入库

bge-m3 生成 dense 向量 → Milvus
chunk 文本 + 元数据 → Elasticsearch BM25
"""
from __future__ import annotations

from pathlib import Path

import structlog
from FlagEmbedding import BGEM3FlagModel
from elasticsearch import AsyncElasticsearch
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from pipeline.config import PipelineConfig
from server.models.schemas import Chunk

logger = structlog.get_logger()

_embed_model: BGEM3FlagModel | None = None


def _get_embed_model() -> BGEM3FlagModel:
    global _embed_model
    if _embed_model is None:
        _embed_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    return _embed_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """批量生成 dense embedding"""
    model = _get_embed_model()
    result = model.encode(texts, return_dense=True, return_sparse=False, return_colbert_vecs=False)
    return result["dense_vecs"].tolist()


# --- Milvus ---

def _init_milvus_collection(config: PipelineConfig) -> Collection:
    """创建或获取 Milvus collection"""
    connections.connect(host=config.milvus_host, port=config.milvus_port)

    if utility.has_collection(config.milvus_collection):
        return Collection(config.milvus_collection)

    fields = [
        FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=1024),  # bge-m3 dim
        FieldSchema("source", DataType.VARCHAR, max_length=128),
        FieldSchema("element_type", DataType.VARCHAR, max_length=16),
    ]
    schema = CollectionSchema(fields, description="Eurocode chunks")
    collection = Collection(config.milvus_collection, schema)
    collection.create_index("embedding", {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 256}})
    return collection


async def index_to_milvus(chunks: list[Chunk], config: PipelineConfig) -> int:
    """将 chunks 的 dense 向量写入 Milvus"""
    collection = _init_milvus_collection(config)

    # 只为有 embedding_text 的 chunk 生成向量
    to_embed = [c for c in chunks if c.embedding_text]
    if not to_embed:
        return 0

    texts = [c.embedding_text for c in to_embed]
    embeddings = _embed_texts(texts)

    data = [
        [c.chunk_id for c in to_embed],
        embeddings,
        [c.metadata.source for c in to_embed],
        [c.metadata.element_type.value for c in to_embed],
    ]
    collection.insert(data)
    collection.flush()
    logger.info("milvus_indexed", count=len(to_embed))
    return len(to_embed)


# --- Elasticsearch ---

_ES_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "standard"},
            "embedding_text": {"type": "text", "analyzer": "standard"},
            "source": {"type": "keyword"},
            "source_title": {"type": "keyword"},
            "section_path": {"type": "keyword"},
            "page_numbers": {"type": "integer"},
            "clause_ids": {"type": "keyword"},
            "element_type": {"type": "keyword"},
            "cross_refs": {"type": "keyword"},
            "parent_chunk_id": {"type": "keyword"},
            "parent_text_chunk_id": {"type": "keyword"},
        }
    }
}


async def index_to_elasticsearch(chunks: list[Chunk], config: PipelineConfig) -> int:
    """将 chunks 写入 Elasticsearch（BM25 + 元数据）"""
    es = AsyncElasticsearch(config.es_url)

    try:
        if not await es.indices.exists(index=config.es_index):
            await es.indices.create(index=config.es_index, body=_ES_MAPPING)

        for chunk in chunks:
            doc = {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "embedding_text": chunk.embedding_text,
                **chunk.metadata.model_dump(),
            }
            await es.index(index=config.es_index, id=chunk.chunk_id, document=doc)

        await es.indices.refresh(index=config.es_index)
        logger.info("es_indexed", count=len(chunks))
        return len(chunks)
    finally:
        await es.close()
```

> 依赖外部服务（Milvus + ES），在 Task 12 集成测试中验证。

- [ ] **Step 2: Commit**

```bash
git add pipeline/index.py
git commit -m "feat(pipeline): add embedding generation + Milvus/ES indexing"
```

---

## Task 7: Pipeline CLI Runner

**Files:**
- Create: `pipeline/run.py`

- [ ] **Step 1: Implement pipeline CLI**

```python
"""管线 CLI 入口：串联 Stage 1-4"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
import structlog

from pipeline.config import PipelineConfig
from pipeline.parse import parse_all_pdfs
from pipeline.structure import parse_markdown_to_tree
from pipeline.chunk import create_chunks
from pipeline.contextualize import enrich_chunk_summaries
from pipeline.index import index_to_milvus, index_to_elasticsearch

logger = structlog.get_logger()


async def _run_pipeline(config: PipelineConfig) -> None:
    """执行完整管线"""

    # Stage 1: MinerU 解析
    logger.info("stage_1_start", msg="PDF → Markdown")
    md_paths = await parse_all_pdfs(config)
    logger.info("stage_1_done", count=len(md_paths))

    all_chunks = []

    for md_path in md_paths:
        source_name = md_path.stem.replace("_", " ")
        markdown = md_path.read_text(encoding="utf-8")

        # 加载元数据（如有）
        meta_path = md_path.parent / f"{md_path.stem}_meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        source_title = meta.get("title", source_name)

        # Stage 2: 结构化解析
        tree = parse_markdown_to_tree(markdown, source=source_name)

        # Stage 3: 分块
        chunks = create_chunks(tree, source_title=source_title)
        logger.info("stage_3_done", source=source_name, chunks=len(chunks))

        # Stage 3.5: LLM 摘要
        chunks = await enrich_chunk_summaries(chunks, config)

        all_chunks.extend(chunks)

    logger.info("total_chunks", count=len(all_chunks))

    # Stage 4: Embedding + 入库
    milvus_count = await index_to_milvus(all_chunks, config)
    es_count = await index_to_elasticsearch(all_chunks, config)
    logger.info("stage_4_done", milvus=milvus_count, es=es_count)


@click.command()
@click.option("--pdf-dir", default=None, help="PDF 目录（覆盖 .env）")
def main(pdf_dir: str | None) -> None:
    """Eurocode 文档处理管线"""
    config = PipelineConfig()
    if pdf_dir:
        config.pdf_dir = pdf_dir
    asyncio.run(_run_pipeline(config))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/run.py
git commit -m "feat(pipeline): add CLI runner - full pipeline orchestration"
```

---

## Task 8: Server — Query Understanding

**Files:**
- Create: `server/core/query_understanding.py`
- Create: `tests/server/test_query_understanding.py`

- [ ] **Step 1: Write failing tests**

```python
"""测试查询理解层"""
from unittest.mock import AsyncMock, patch

import pytest

from server.core.query_understanding import (
    classify_intent,
    rewrite_query,
    extract_filters,
    QueryAnalysis,
)
from server.models.schemas import IntentType


class TestClassifyIntent:
    def test_exact_query_formula(self):
        result = classify_intent("公式6.10怎么用")
        assert result == IntentType.EXACT

    def test_exact_query_table(self):
        result = classify_intent("Table A1.2 的内容")
        assert result == IntentType.EXACT

    def test_concept_query(self):
        result = classify_intent("什么是极限状态")
        assert result == IntentType.CONCEPT

    def test_reasoning_query(self):
        result = classify_intent("巴黎地铁的使用期限有多久")
        assert result == IntentType.REASONING


class TestExtractFilters:
    def test_extract_source_filter(self):
        filters = extract_filters("EN 1992 第6章的抗弯计算")
        assert filters.get("source") == "EN 1992"

    def test_extract_element_type(self):
        filters = extract_filters("表格A1.2的内容")
        assert filters.get("element_type") == "table"

    def test_no_filters(self):
        filters = extract_filters("混凝土梁如何设计")
        assert filters == {}


class TestRewriteQuery:
    @pytest.mark.asyncio
    async def test_rewrite_with_glossary(self):
        glossary = {"设计使用年限": "design working life"}
        mock_llm = AsyncMock(return_value="design working life infrastructure")
        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await rewrite_query("地铁的设计使用年限是多久", glossary)
            assert "design working life" in result
```

- [ ] **Step 2: Run tests → FAIL**

- [ ] **Step 3: Implement query_understanding.py**

```python
"""查询理解层：意图分类 + 查询改写 + 过滤条件提取"""
from __future__ import annotations

import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from server.config import ServerConfig
from server.models.schemas import IntentType

# 精确查询的正则模式
_EXACT_PATTERNS = [
    re.compile(r"(?:公式|formula|eq\.?)\s*[\d.]+", re.IGNORECASE),
    re.compile(r"(?:表格?|table)\s*[A-Z]?\d+[\d.]*", re.IGNORECASE),
    re.compile(r"§\s*\d+", re.IGNORECASE),
    re.compile(r"\d+\.\d+\.\d+"),  # 条款编号如 6.3.5
]

_SOURCE_RE = re.compile(r"EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_TABLE_RE = re.compile(r"表格?|table", re.IGNORECASE)
_FORMULA_RE = re.compile(r"公式|formula|eq", re.IGNORECASE)


@dataclass
class QueryAnalysis:
    intent: IntentType
    original_question: str
    rewritten_query: str
    filters: dict[str, str]
    matched_terms: dict[str, str]  # 命中的术语表条目


def classify_intent(question: str) -> IntentType:
    """根据问题文本分类意图"""
    for pattern in _EXACT_PATTERNS:
        if pattern.search(question):
            return IntentType.EXACT

    # 概念类关键词
    concept_keywords = ["什么是", "定义", "含义", "概念", "区别", "what is", "definition"]
    if any(kw in question.lower() for kw in concept_keywords):
        return IntentType.CONCEPT

    return IntentType.REASONING


def extract_filters(question: str) -> dict[str, str]:
    """从问题中提取元数据过滤条件"""
    filters: dict[str, str] = {}

    m = _SOURCE_RE.search(question)
    if m:
        filters["source"] = f"EN {m.group(1)}"

    if _TABLE_RE.search(question):
        filters["element_type"] = "table"
    elif _FORMULA_RE.search(question):
        filters["element_type"] = "formula"

    return filters


async def _call_llm(prompt: str, config: ServerConfig | None = None) -> str:
    cfg = config or ServerConfig()
    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    resp = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
    )
    return resp.choices[0].message.content.strip()


async def rewrite_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> str:
    """将中文问题改写为英文检索 query

    1. 先在术语表中查找匹配
    2. 术语表命中的用精确翻译
    3. 未命中的由 LLM 翻译改写
    """
    matched_terms: dict[str, str] = {}
    for zh, en in glossary.items():
        if zh in question:
            matched_terms[zh] = en

    # 构建 prompt
    term_hint = ""
    if matched_terms:
        term_hint = "已知术语对照：" + ", ".join(f"{zh}={en}" for zh, en in matched_terms.items()) + "\n"

    prompt = (
        f"将以下中文工程问题改写为英文检索关键词（用于在 Eurocode 规范文档中搜索）。\n"
        f"只输出英文关键词，用空格分隔，不要输出句子。\n"
        f"{term_hint}"
        f"问题：{question}"
    )
    return await _call_llm(prompt, config)


async def analyze_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> QueryAnalysis:
    """完整的查询分析流程"""
    intent = classify_intent(question)
    filters = extract_filters(question)
    rewritten = await rewrite_query(question, glossary, config)

    matched_terms = {zh: en for zh, en in glossary.items() if zh in question}

    return QueryAnalysis(
        intent=intent,
        original_question=question,
        rewritten_query=rewritten,
        filters=filters,
        matched_terms=matched_terms,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/server/test_query_understanding.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add server/core/query_understanding.py tests/server/test_query_understanding.py
git commit -m "feat(server): add query understanding - intent, rewrite, filters"
```

---

## Task 9: Server — Hybrid Retrieval + Reranker

**Files:**
- Create: `server/core/retrieval.py`
- Create: `tests/server/test_retrieval.py`

- [ ] **Step 1: Write failing tests**

```python
"""测试混合检索层（mock 外部服务）"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.retrieval import HybridRetriever, RetrievalResult
from server.models.schemas import IntentType


@pytest.fixture
def retriever():
    return HybridRetriever.__new__(HybridRetriever)


class TestMergeAndDedup:
    def test_dedup_by_chunk_id(self, retriever):
        vec_results = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
        ]
        bm25_results = [
            {"chunk_id": "b", "score": 5.0},
            {"chunk_id": "c", "score": 4.0},
        ]
        merged = retriever._merge_results(vec_results, bm25_results)
        ids = [r["chunk_id"] for r in merged]
        assert len(ids) == len(set(ids))  # 无重复
        assert "a" in ids and "b" in ids and "c" in ids

    def test_exact_intent_prioritizes_bm25(self, retriever):
        vec_results = [{"chunk_id": "a", "score": 0.9}]
        bm25_results = [{"chunk_id": "b", "score": 5.0}]
        merged = retriever._merge_results(
            vec_results, bm25_results, intent=IntentType.EXACT
        )
        # BM25 结果应该排在前面
        assert merged[0]["chunk_id"] == "b"


class TestCrossDocAggregation:
    def test_limits_per_source(self, retriever):
        results = [
            {"chunk_id": f"en1990_{i}", "source": "EN 1990", "score": 0.9 - i * 0.1}
            for i in range(5)
        ] + [
            {"chunk_id": "en1991_0", "source": "EN 1991", "score": 0.5}
        ]
        aggregated = retriever._cross_doc_aggregate(results, max_per_source=2)
        en1990_count = sum(1 for r in aggregated if r["source"] == "EN 1990")
        assert en1990_count <= 2
        assert any(r["source"] == "EN 1991" for r in aggregated)
```

- [ ] **Step 2: Run tests → FAIL**

- [ ] **Step 3: Implement retrieval.py**

```python
"""混合检索层：向量检索 + BM25 + Reranker + Parent Retrieval"""
from __future__ import annotations

from dataclasses import dataclass

import structlog
from elasticsearch import AsyncElasticsearch
from FlagEmbedding import BGEM3FlagModel, FlagReranker
from pymilvus import Collection, connections

from server.config import ServerConfig
from server.models.schemas import Chunk, ChunkMetadata, IntentType

logger = structlog.get_logger()


@dataclass
class RetrievalResult:
    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]


class HybridRetriever:
    def __init__(self, config: ServerConfig):
        self.config = config
        self._embed_model: BGEM3FlagModel | None = None
        self._reranker: FlagReranker | None = None
        self._es: AsyncElasticsearch | None = None
        self._collection: Collection | None = None

    @property
    def embed_model(self) -> BGEM3FlagModel:
        if self._embed_model is None:
            self._embed_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        return self._embed_model

    @property
    def reranker(self) -> FlagReranker:
        if self._reranker is None:
            self._reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
        return self._reranker

    async def _get_es(self) -> AsyncElasticsearch:
        if self._es is None:
            self._es = AsyncElasticsearch(self.config.es_url)
        return self._es

    def _get_collection(self) -> Collection:
        if self._collection is None:
            connections.connect(host=self.config.milvus_host, port=self.config.milvus_port)
            self._collection = Collection(self.config.milvus_collection)
            self._collection.load()
        return self._collection

    # --- 向量检索 ---
    async def _vector_search(self, query: str, top_k: int, filters: dict) -> list[dict]:
        embedding = self.embed_model.encode([query], return_dense=True)["dense_vecs"][0].tolist()
        collection = self._get_collection()

        expr_parts = []
        if "source" in filters:
            expr_parts.append(f'source == "{filters["source"]}"')
        if "element_type" in filters:
            expr_parts.append(f'element_type == "{filters["element_type"]}"')
        expr = " and ".join(expr_parts) if expr_parts else None

        results = collection.search(
            data=[embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "source", "element_type"],
        )

        return [
            {"chunk_id": hit.entity.get("chunk_id"), "source": hit.entity.get("source"), "score": hit.score}
            for hit in results[0]
        ]

    # --- BM25 检索 ---
    async def _bm25_search(self, query: str, top_k: int, filters: dict) -> list[dict]:
        es = await self._get_es()
        must = [{"multi_match": {"query": query, "fields": ["content", "embedding_text"]}}]
        filter_clauses = []
        if "source" in filters:
            filter_clauses.append({"term": {"source": filters["source"]}})
        if "element_type" in filters:
            filter_clauses.append({"term": {"element_type": filters["element_type"]}})

        body = {"query": {"bool": {"must": must, "filter": filter_clauses}}, "size": top_k}
        resp = await es.search(index=self.config.es_index, body=body)

        return [
            {"chunk_id": hit["_id"], "source": hit["_source"].get("source", ""), "score": hit["_score"]}
            for hit in resp["hits"]["hits"]
        ]

    # --- 合并去重 ---
    def _merge_results(
        self,
        vec_results: list[dict],
        bm25_results: list[dict],
        intent: IntentType = IntentType.REASONING,
    ) -> list[dict]:
        seen: set[str] = set()
        merged: list[dict] = []

        # 精确查询时 BM25 优先
        primary = bm25_results if intent == IntentType.EXACT else vec_results
        secondary = vec_results if intent == IntentType.EXACT else bm25_results

        for r in primary:
            if r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                merged.append(r)
        for r in secondary:
            if r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                merged.append(r)
        return merged

    # --- 跨文档聚合 ---
    def _cross_doc_aggregate(self, results: list[dict], max_per_source: int = 3) -> list[dict]:
        source_counts: dict[str, int] = {}
        aggregated: list[dict] = []
        for r in results:
            src = r.get("source", "")
            count = source_counts.get(src, 0)
            if count < max_per_source:
                aggregated.append(r)
                source_counts[src] = count + 1
        return aggregated

    # --- Rerank ---
    def _rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []
        pairs = [(query, c.embedding_text or c.content) for c in chunks]
        scores = self.reranker.compute_score(pairs)
        if isinstance(scores, float):
            scores = [scores]
        scored = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    # --- 获取完整 chunk ---
    async def _fetch_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        es = await self._get_es()
        chunks = []
        for cid in chunk_ids:
            try:
                doc = await es.get(index=self.config.es_index, id=cid)
                src = doc["_source"]
                chunks.append(Chunk(
                    chunk_id=cid,
                    content=src.get("content", ""),
                    embedding_text=src.get("embedding_text", ""),
                    metadata=ChunkMetadata(**{
                        k: src[k] for k in ChunkMetadata.model_fields if k in src
                    }),
                ))
            except Exception:
                logger.warning("chunk_fetch_failed", chunk_id=cid)
        return chunks

    # --- 获取 parent chunk ---
    async def _fetch_parent_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        parent_ids = set()
        for c in chunks:
            if c.metadata.parent_chunk_id:
                parent_ids.add(c.metadata.parent_chunk_id)
        return await self._fetch_chunks(list(parent_ids))

    # --- 主检索流程 ---
    async def retrieve(
        self,
        query: str,
        intent: IntentType = IntentType.REASONING,
        filters: dict | None = None,
    ) -> RetrievalResult:
        filters = filters or {}
        cfg = self.config

        # 并发执行双路检索
        try:
            vec_results = await self._vector_search(query, cfg.vector_top_k, filters)
        except Exception:
            logger.warning("vector_search_failed, falling back to BM25 only")
            vec_results = []

        bm25_results = await self._bm25_search(query, cfg.bm25_top_k, filters)

        # 合并 + 跨文档聚合
        merged = self._merge_results(vec_results, bm25_results, intent)
        aggregated = self._cross_doc_aggregate(merged)

        # 获取完整 chunk
        chunk_ids = [r["chunk_id"] for r in aggregated]
        chunks = await self._fetch_chunks(chunk_ids)

        # Rerank
        reranked = self._rerank(query, chunks, cfg.rerank_top_n)
        final_chunks = [c for c, _ in reranked]
        scores = [s for _, s in reranked]

        # Parent retrieval
        parent_chunks = await self._fetch_parent_chunks(final_chunks)

        return RetrievalResult(
            chunks=final_chunks,
            parent_chunks=parent_chunks,
            scores=scores,
        )

    async def close(self):
        if self._es:
            await self._es.close()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/server/test_retrieval.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add server/core/retrieval.py tests/server/test_retrieval.py
git commit -m "feat(server): add hybrid retrieval - vector + BM25 + rerank"
```

---

## Task 10: Server — Generation Layer

**Files:**
- Create: `server/core/generation.py`
- Create: `tests/server/test_generation.py`

- [ ] **Step 1: Write failing tests**

```python
"""测试生成层（mock LLM）"""
from unittest.mock import AsyncMock, patch
import json

import pytest

from server.core.generation import build_prompt, parse_llm_response, generate_answer
from server.models.schemas import Chunk, ChunkMetadata, ElementType, Confidence


@pytest.fixture
def context_chunks(sample_text_chunk, sample_table_chunk):
    return [sample_text_chunk, sample_table_chunk]


class TestBuildPrompt:
    def test_includes_question(self, context_chunks):
        prompt = build_prompt("巴黎地铁寿命", context_chunks, [])
        assert "巴黎地铁寿命" in prompt

    def test_includes_source_info(self, context_chunks):
        prompt = build_prompt("test", context_chunks, [])
        assert "EN 1990:2002" in prompt
        assert "2.3" in prompt

    def test_includes_glossary(self, context_chunks):
        glossary = {"设计使用年限": "design working life"}
        prompt = build_prompt("test", context_chunks, [], glossary_terms=glossary)
        assert "design working life" in prompt


class TestParseLlmResponse:
    def test_parse_valid_json(self):
        raw = json.dumps({
            "answer": "100年",
            "sources": [{"file": "EN 1990", "title": "Basis", "section": "2.3",
                         "page": 28, "clause": "Table 2.1", "original_text": "bridges",
                         "translation": "桥梁"}],
            "related_refs": ["Annex A"],
            "confidence": "high"
        })
        result = parse_llm_response(raw)
        assert result.answer == "100年"
        assert result.confidence == Confidence.HIGH
        assert len(result.sources) == 1

    def test_fallback_on_invalid_json(self):
        raw = "这是一个非 JSON 的回答"
        result = parse_llm_response(raw)
        assert result.answer == raw
        assert result.confidence == Confidence.LOW
```

- [ ] **Step 2: Run tests → FAIL**

- [ ] **Step 3: Implement generation.py**

```python
"""生成层：Prompt 组装 + LLM 调用 + 结构化输出"""
from __future__ import annotations

import json

import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.models.schemas import (
    Chunk,
    Confidence,
    QueryResponse,
    Source,
)

logger = structlog.get_logger()

_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师理解和查询规范内容。

规则：
1. 所有回答必须基于提供的规范原文，不要编造规范中不存在的内容。
2. 回答用中文，但保留原文中的关键术语（如条款编号、表格编号、公式编号）。
3. 必须标注出处（文件名、章节、页码、条款号）。
4. 对原文关键段落提供中文翻译。
5. 如果需要推理，说明推理过程。

输出格式：严格 JSON，结构如下：
{
  "answer": "中文回答",
  "sources": [{"file": "EN 1990:2002", "title": "...", "section": "...", "page": 28, "clause": "...", "original_text": "...", "translation": "..."}],
  "related_refs": ["相关的其他规范引用"],
  "confidence": "high|medium|low"
}"""


def build_prompt(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
) -> str:
    """组装完整 prompt"""
    parts: list[str] = []

    # 术语表
    if glossary_terms:
        terms = ", ".join(f"{zh}={en}" for zh, en in glossary_terms.items())
        parts.append(f"相关术语对照：{terms}\n")

    # 检索上下文
    parts.append("检索到的规范内容：\n")
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        source_info = f"{meta.source}, Page {','.join(map(str, meta.page_numbers))}, {' > '.join(meta.section_path)}"
        parts.append(f"[{i}] {source_info}\n{chunk.content}\n")

    # Parent 上下文（如果 child+parent 未超限，追加）
    if parent_chunks:
        parts.append("\n扩展上下文（章节级）：\n")
        for pc in parent_chunks[:2]:
            parts.append(f"[Parent] {' > '.join(pc.metadata.section_path)}\n{pc.content[:2000]}\n")

    # 对话历史
    if conversation_history:
        parts.append("\n之前的对话：\n")
        for h in conversation_history[-2:]:
            parts.append(f"Q: {h['question']}\nA: {h['answer'][:500]}\n")

    parts.append(f"\n用户问题：{question}")
    return "\n".join(parts)


def parse_llm_response(raw: str) -> QueryResponse:
    """解析 LLM 的 JSON 响应，失败时降级"""
    # 尝试从 markdown code block 中提取 JSON
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(raw)
        sources = [Source(**s) for s in data.get("sources", [])[:5]]
        return QueryResponse(
            answer=data.get("answer", ""),
            sources=sources,
            related_refs=data.get("related_refs", []),
            confidence=Confidence(data.get("confidence", "low")),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("llm_response_parse_failed", raw=raw[:200])
        return QueryResponse(
            answer=raw,
            sources=[],
            related_refs=[],
            confidence=Confidence.LOW,
        )


async def generate_answer(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
) -> QueryResponse:
    """调用 LLM 生成回答"""
    cfg = config or ServerConfig()
    prompt = build_prompt(question, chunks, parent_chunks, glossary_terms, conversation_history)

    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    try:
        resp = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        return parse_llm_response(raw)
    except Exception:
        logger.exception("llm_call_failed")
        return QueryResponse(
            answer="LLM 服务暂时不可用，以下是检索到的相关规范片段。",
            sources=[],
            confidence=Confidence.LOW,
            degraded=True,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/server/test_generation.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add server/core/generation.py tests/server/test_generation.py
git commit -m "feat(server): add generation layer - prompt assembly + structured output"
```

---

## Task 11: Server — Conversation + API Routes

**Files:**
- Create: `server/core/conversation.py`
- Create: `server/deps.py`
- Create: `server/api/v1/router.py`
- Create: `server/api/v1/query.py`
- Create: `server/api/v1/documents.py`
- Create: `server/api/v1/glossary.py`
- Create: `server/main.py`
- Create: `tests/server/test_api.py`

- [ ] **Step 1: Implement conversation.py**

```python
"""会话状态管理（内存缓存，TTL 24h）"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from cachetools import TTLCache


@dataclass
class ConversationState:
    conversation_id: str
    history: list[dict] = field(default_factory=list)  # [{question, answer, chunks}]


class ConversationManager:
    def __init__(self, ttl_hours: int = 24, max_size: int = 1000):
        self._cache: TTLCache = TTLCache(maxsize=max_size, ttl=ttl_hours * 3600)

    def get_or_create(self, conversation_id: str | None = None) -> ConversationState:
        if conversation_id and conversation_id in self._cache:
            return self._cache[conversation_id]
        cid = conversation_id or str(uuid.uuid4())
        state = ConversationState(conversation_id=cid)
        self._cache[cid] = state
        return state

    def add_turn(self, conversation_id: str, question: str, answer: str) -> None:
        state = self._cache.get(conversation_id)
        if state:
            state.history.append({"question": question, "answer": answer})
            # 保留最近 3 轮
            if len(state.history) > 3:
                state.history = state.history[-3:]
```

- [ ] **Step 2: Implement deps.py (dependency injection)**

```python
"""FastAPI 依赖注入"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from server.config import ServerConfig
from server.core.conversation import ConversationManager
from server.core.retrieval import HybridRetriever


@lru_cache
def get_config() -> ServerConfig:
    return ServerConfig()


@lru_cache
def get_conversation_manager() -> ConversationManager:
    config = get_config()
    return ConversationManager(ttl_hours=config.conversation_ttl_hours)


@lru_cache
def get_retriever() -> HybridRetriever:
    return HybridRetriever(get_config())


@lru_cache
def get_glossary() -> dict[str, str]:
    config = get_config()
    path = Path(config.glossary_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
```

- [ ] **Step 3: Implement API routes**

`server/api/v1/query.py`:
```python
"""POST /api/v1/query — 问答主接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.deps import get_config, get_conversation_manager, get_glossary, get_retriever
from server.core.query_understanding import analyze_query
from server.core.generation import generate_answer
from server.models.schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    config=Depends(get_config),
    retriever=Depends(get_retriever),
    glossary=Depends(get_glossary),
    conv_mgr=Depends(get_conversation_manager),
) -> QueryResponse:
    # 查询理解
    analysis = await analyze_query(req.question, glossary, config)

    # 合并引导层过滤条件
    filters = analysis.filters
    if req.domain:
        filters["source"] = req.domain

    # 检索
    result = await retriever.retrieve(
        query=analysis.rewritten_query,
        intent=analysis.intent,
        filters=filters,
    )

    # 会话上下文
    conv = conv_mgr.get_or_create(req.conversation_id)

    # 生成
    response = await generate_answer(
        question=req.question,
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        glossary_terms=analysis.matched_terms,
        conversation_history=conv.history,
        config=config,
    )
    response.conversation_id = conv.conversation_id

    # 记录对话
    conv_mgr.add_turn(conv.conversation_id, req.question, response.answer)

    return response
```

`server/api/v1/documents.py`:
```python
"""GET /api/v1/documents — 文档列表 + 页面预览"""
from __future__ import annotations

from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from server.deps import get_config
from server.models.schemas import DocumentInfo

router = APIRouter()


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(config=Depends(get_config)) -> list[DocumentInfo]:
    pdf_dir = Path(config.pdf_dir)
    docs = []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        doc = fitz.open(str(pdf_path))
        docs.append(DocumentInfo(
            id=pdf_path.stem,
            name=pdf_path.stem.replace("_", " "),
            title=doc.metadata.get("title", pdf_path.stem),
            total_pages=len(doc),
            chunk_count=0,  # 后续可从 ES 查询
        ))
        doc.close()
    return docs


@router.get("/documents/{doc_id}/page/{page}")
async def get_page_image(doc_id: str, page: int, config=Depends(get_config)) -> Response:
    pdf_path = Path(config.pdf_dir) / f"{doc_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, f"Document {doc_id} not found")

    doc = fitz.open(str(pdf_path))
    if page < 1 or page > len(doc):
        raise HTTPException(404, f"Page {page} out of range")

    pix = doc[page - 1].get_pixmap(dpi=150)
    doc.close()
    return Response(content=pix.tobytes("png"), media_type="image/png")
```

`server/api/v1/glossary.py`:
```python
"""GET /api/v1/glossary, /api/v1/suggest"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.deps import get_glossary
from server.models.schemas import GlossaryEntry

router = APIRouter()


@router.get("/glossary", response_model=list[GlossaryEntry])
async def list_glossary(
    source: str | None = None,
    q: str | None = None,
    glossary=Depends(get_glossary),
) -> list[GlossaryEntry]:
    entries = []
    for zh, en in glossary.items():
        if q and q not in zh and q not in en:
            continue
        entries.append(GlossaryEntry(zh=[zh], en=en))
    return entries


@router.get("/suggest")
async def suggest() -> dict:
    return {
        "hot_questions": [
            "混凝土梁的抗弯承载力如何计算？",
            "风荷载的基本风压如何取值？",
            "设计使用年限怎么确定？",
            "荷载组合的基本原则是什么？",
            "地震设计的重要性系数怎么确定？",
        ],
        "domains": [
            {"id": "EN 1990", "name": "结构基础"},
            {"id": "EN 1991", "name": "荷载与作用"},
            {"id": "EN 1992", "name": "混凝土结构"},
            {"id": "EN 1993", "name": "钢结构"},
            {"id": "EN 1994", "name": "钢-混凝土组合结构"},
            {"id": "EN 1995", "name": "木结构"},
            {"id": "EN 1996", "name": "砌体结构"},
            {"id": "EN 1997", "name": "岩土工程"},
            {"id": "EN 1998", "name": "抗震设计"},
            {"id": "EN 1999", "name": "铝结构"},
        ],
        "query_types": [
            {"id": "clause", "name": "查条款"},
            {"id": "concept", "name": "问概念"},
            {"id": "parameter", "name": "算参数"},
            {"id": "comparison", "name": "比差异"},
        ],
    }
```

`server/api/v1/router.py`:
```python
"""v1 路由聚合"""
from fastapi import APIRouter

from server.api.v1 import documents, glossary, query

router = APIRouter(prefix="/api/v1")
router.include_router(query.router, tags=["Query"])
router.include_router(documents.router, tags=["Documents"])
router.include_router(glossary.router, tags=["Glossary"])
```

`server/main.py`:
```python
"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.v1.router import router as v1_router
from server.deps import get_retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    retriever = get_retriever()
    await retriever.close()


app = FastAPI(
    title="Eurocode QA API",
    description="欧洲建筑规范智能问答系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)
```

- [ ] **Step 4: Write API integration tests**

```python
"""API 集成测试（mock 外部依赖）"""
from unittest.mock import AsyncMock, patch, MagicMock
import json

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestQueryEndpoint:
    def test_query_validation(self, client):
        # 缺少必填字段
        resp = client.post("/api/v1/query", json={})
        assert resp.status_code == 422

    def test_question_max_length(self, client):
        resp = client.post("/api/v1/query", json={"question": "x" * 501})
        assert resp.status_code == 422


class TestDocumentsEndpoint:
    def test_list_documents(self, client):
        resp = client.get("/api/v1/documents")
        # 可能返回空列表（无PDF）或200
        assert resp.status_code == 200

class TestGlossaryEndpoint:
    def test_suggest(self, client):
        resp = client.get("/api/v1/suggest")
        assert resp.status_code == 200
        data = resp.json()
        assert "hot_questions" in data
        assert "domains" in data
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/server/test_api.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add server/ tests/server/test_api.py
git commit -m "feat(server): add API routes, conversation manager, and FastAPI app"
```

---

## Task 12: Docker Compose + Initial Glossary

**Files:**
- Create: `docker-compose.yml`
- Create: `data/glossary.json`
- Create: `Dockerfile`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: "3.8"

services:
  milvus-etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  milvus-minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    command: minio server /minio_data

  milvus:
    image: milvusdb/milvus:v2.4-latest
    depends_on:
      - milvus-etcd
      - milvus-minio
    environment:
      ETCD_ENDPOINTS: milvus-etcd:2379
      MINIO_ADDRESS: milvus-minio:9000
    ports:
      - "19530:19530"

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"

  app:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      - milvus
      - elasticsearch
    env_file: .env
    volumes:
      - ./data:/app/data
    command: uvicorn server.main:app --host 0.0.0.0 --port 8080
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY . .

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: Create initial glossary**

```json
{
  "设计使用年限": "design working life",
  "设计寿命": "design working life",
  "极限状态": "limit state",
  "承载能力极限状态": "ultimate limit state",
  "正常使用极限状态": "serviceability limit state",
  "分项系数": "partial factor",
  "荷载组合": "combination of actions",
  "可变荷载": "variable action",
  "永久荷载": "permanent action",
  "偶然荷载": "accidental action",
  "抗力": "resistance",
  "设计值": "design value",
  "特征值": "characteristic value",
  "代表值": "representative value",
  "结构可靠性": "structural reliability",
  "耐久性": "durability",
  "适用性": "serviceability",
  "安全性": "safety",
  "鲁棒性": "robustness",
  "地震作用": "seismic action",
  "风荷载": "wind action",
  "雪荷载": "snow load",
  "活荷载": "imposed load",
  "自重": "self-weight",
  "预应力": "prestressing",
  "徐变": "creep",
  "收缩": "shrinkage",
  "疲劳": "fatigue",
  "屈曲": "buckling",
  "挠度": "deflection",
  "裂缝宽度": "crack width",
  "保护层厚度": "concrete cover",
  "配筋率": "reinforcement ratio",
  "抗弯承载力": "bending resistance",
  "抗剪承载力": "shear resistance",
  "锚固长度": "anchorage length",
  "搭接长度": "lap length"
}
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml Dockerfile data/glossary.json
git commit -m "feat: add Docker Compose, Dockerfile, and initial glossary"
```

---

## Task 13: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write E2E test script**

```python
"""端到端冒烟测试

需要先启动 docker-compose 和 pipeline。
运行方式: pytest tests/test_e2e.py -v --e2e
"""
import pytest
import httpx

E2E_BASE_URL = "http://localhost:8080"


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests (need running services)")


@pytest.mark.e2e
class TestE2E:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=E2E_BASE_URL, timeout=30.0)

    def test_health(self, client):
        resp = client.get("/api/v1/suggest")
        assert resp.status_code == 200

    def test_documents_list(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) > 0

    def test_query_basic(self, client):
        resp = client.post("/api/v1/query", json={
            "question": "设计使用年限怎么确定？",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"]
        assert data["confidence"] in ["high", "medium", "low", "none"]
        assert data["conversation_id"]

    def test_query_with_domain(self, client):
        resp = client.post("/api/v1/query", json={
            "question": "荷载组合的基本原则",
            "domain": "EN 1990",
        })
        assert resp.status_code == 200
        data = resp.json()
        # source 应该包含 EN 1990
        if data["sources"]:
            assert any("EN 1990" in s["file"] for s in data["sources"])

    def test_query_conversation(self, client):
        # 第一轮
        resp1 = client.post("/api/v1/query", json={"question": "设计使用年限怎么确定？"})
        cid = resp1.json()["conversation_id"]

        # 追问
        resp2 = client.post("/api/v1/query", json={
            "question": "那对应的荷载组合怎么取？",
            "conversation_id": cid,
        })
        assert resp2.status_code == 200
        assert resp2.json()["conversation_id"] == cid

    def test_glossary(self, client):
        resp = client.get("/api/v1/glossary")
        assert resp.status_code == 200
        assert len(resp.json()) > 0
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end smoke test suite"
```

---

## Task 14: Run All Unit Tests + Final Verification

- [ ] **Step 1: Run full test suite (unit tests only)**

Run: `uv run pytest tests/ -v --ignore=tests/test_e2e.py`
Expected: all PASS

- [ ] **Step 2: Verify project structure**

Run: `find . -name '*.py' -not -path './.venv/*' | sort`
Expected: all files from the plan exist

- [ ] **Step 3: Verify Docker Compose starts**

Run: `docker compose up -d milvus elasticsearch`
Expected: Milvus on :19530, ES on :9200

- [ ] **Step 4: Verify server starts**

Run: `uv run uvicorn server.main:app --port 8080`
Expected: Swagger at http://localhost:8080/docs

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: verify all tests pass and services start"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Project scaffolding | pyproject.toml, schemas.py, configs |
| 2 | Structure parser | pipeline/structure.py |
| 3 | Mixed chunker | pipeline/chunk.py |
| 4 | MinerU client | pipeline/parse.py |
| 5 | LLM summaries | pipeline/summarize.py |
| 6 | Embedding + indexing | pipeline/index.py |
| 7 | Pipeline CLI | pipeline/run.py |
| 8 | Query understanding | server/core/query_understanding.py |
| 9 | Hybrid retrieval | server/core/retrieval.py |
| 10 | Generation | server/core/generation.py |
| 11 | API routes + app | server/api/v1/*.py, server/main.py |
| 12 | Docker + glossary | docker-compose.yml, glossary.json |
| 13 | E2E smoke test | tests/test_e2e.py |
| 14 | Final verification | — |

**Estimated effort:** 14 tasks, each with 4-8 steps.
