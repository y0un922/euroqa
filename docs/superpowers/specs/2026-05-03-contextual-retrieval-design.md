# Contextual Retrieval Design

## Status

- **Status**: ⏸ DEFERRED — implementation gated on [Chunking Fix](/Users/youngz/webdav/Euro_QA/docs/superpowers/specs/2026-05-03-chunking-fix-design.md) (sub-project 1) 在 master 上落地并经用户验证有效
- **Branch**: `feature/contextual-retrieval`（基于完成 chunking-fix 之后的 master 创建；本子项目是测试性功能，分支隔离便于回退）
- **Depends on**: chunking-fix 完成并验证有效
- **Blocks**: 无
- **Author**: yangzhuo
- **Date**: 2026-05-03

## Goal

在不破坏现有 master 的前提下，给三篇 Eurocode PDF 的 chunk 索引引入 Anthropic 风格的 contextual retrieval：每个 chunk 在写入 Milvus 向量库 + Elasticsearch BM25 之前，先用 LLM 生成一段"该 chunk 在文档中的位置/语境"短文本前缀，让 embedding 与 BM25 都吃到这层语境信号。本子项目是**测试性功能**——用户重建索引、主观/抽样对比检索质量后决定是否合并。如果效果不佳，整个分支回退，master 不受影响。

## Context

### 论文背景

Anthropic 2024 年 9 月发布的 [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) 报告称：
- 仅 contextualize 向量召回：失败率 -35%
- 向量 + BM25 都 contextualize：-49%
- 再叠 rerank：-67%

我们已有 rerank（`server/core/retrieval.py`），所以核心问题是把 contextualize 信号注入 embedding 与 BM25 两个索引层。

### 现有系统架构（截至 2026-05-03）

- **检索栈**：Milvus 向量召回 + Elasticsearch BM25 + rerank + 父块补全（hybrid）
- **LLM 栈**：DeepSeek（OpenAI 兼容 API），通过 `LLM_BASE_URL` + `LLM_MODEL` 配置；context 上限约 64K tokens
- **Embedding**：bge-m3（dim=1024，HNSW M=16, efConstruction=256）
- **Chunk 模型**（`server/models/schemas.py`）：`Chunk` 同时持有 `content`（展示用，raw）与 `embedding_text`（索引用，可被改写），两字段已天然解耦——这是本子项目的关键设计杠杆
- **Pipeline**：Stage 1 (parse) → 2 (structure) → 3 (chunk) → 3.5 (LLM 摘要特殊 chunk) → 4 (index)

`pipeline/summarize.py::enrich_chunk_summaries` 已经实现了"用 LLM 替换 special chunk 的 `embedding_text`"逻辑（即 `chunk.py:391` 注释里说的 "Task 5"），所以本子项目的扩展槽位天然存在——只需把 Stage 3.5 从"仅处理特殊 chunk"扩展到"处理所有 chunk"。

### Index 字段使用

`pipeline/index.py` 实测：
- Milvus 仅写入 `embedding_text` 的 embedding（`index.py:65, 69`）
- Elasticsearch 同时索引 `content` 与 `embedding_text` 两个字段（`index.py:88-89, 171-172`），都参与 BM25 评分

**含义**：把 contextualized 文本写进 `embedding_text`，**Milvus + ES 同时受益**，retrieval 端零改动。这是 Anthropic 完整配方（向量 + BM25 同时 contextualize）的天然落地点。

## Decisions

| ID | 决策 | 拒绝的替代方案 | 理由 |
|----|------|----------------|------|
| A | 独立 feature 分支 `feature/contextual-retrieval`，不合 master 即可整体回退 | feature flag / 独立模块旁路 | 测试性功能，KISS；feature flag 让 master 长期带 if-else；旁路模块需双份索引存储 |
| B1 | 完整配方：向量 + BM25 同时 contextualize（写入 `embedding_text` 即可两路兼得） | 仅向量侧 / 仅 BM25 侧 | 索引字段天然支持；Anthropic 数据显示完整配方比单侧多 14% 改善 |
| C1 | 图片 chunk 走纯文本路径：仅用 alt + 父 section + 文档摘要，不用视觉 LLM | 视觉 LLM / 混合 | 你的 IMAGE chunk `content` 是 `![alt](path)` markdown，本质是"语境锚点"而非"图片内容"；视觉 LLM 引入新依赖、新成本、新失败模式，对测试性功能性价比低 |
| D3 | 配置化 LLM Provider：抽 `Contextualizer` 接口，默认 DeepSeek，env 可切 Anthropic | 仅 DeepSeek（YAGNI 路线） / 仅 Anthropic | 用户明确要求保留切换能力；薄抽象，两实现各 ~50 行 |
| E2 | 特殊 chunk 一次 LLM 调用同时产出 context + 语义化描述（取代原 Stage 3.5 摘要逻辑） | 仅 contextualize 不动 raw / 两次独立调用 | raw markdown table / LaTeX formula 直接 embedding 质量差，必须语义化；E2 一次调用两件事都做完，A/B 评估时 contextualize + 语义化作为整体生效，归因更干净 |
| F | 默认并发 8，`config.contextualize_concurrency` 可调；失败重试 ≤2 次（沿用 `_SUMMARY_MAX_ATTEMPTS`） | 串行 / 异步队列 | asyncio + Semaphore 已是现有 stack 的成熟模式 |
| G | doc summary 不持久化（仅 Stage 3.5 单次执行内存活）| 写 artifact / 写 metadata | 重跑成本极低（每篇一次额外 LLM 调用），缓存层不值得 |
| H | parent_section_text 透传 parent chunk content（不二次截断）| 截到 3K tokens | 已由 chunking 阶段 4K cap 保证；二次截断只损失信息无收益 |
| I | doc_outline_text 用结构化构造（每节 200 字符前文）而非"事后截断" | 全文截断 | 全文动辄超 64K context window；按节构造保证 ~7-15K tokens 内 |
| J | section_path 加入 prompt 作为 grounding 信号 | 不加 | metadata 现成有；让 LLM 知道 chunk 在文档大纲哪个位置，提高 context 质量；零额外成本 |

## Architecture (Section 1 of detailed design)

不新增 pipeline 阶段，**就地扩展现有 Stage 3.5**：

```
Stage 1 (PDF→MD)         不动
Stage 2 (Tree)           不动（chunking-fix 已修好层级）
Stage 3 (Chunking)       不动（chunking-fix 已修好递归切分）；产物：embedding_text = raw content
        ▼
Stage 3.5 (扩展)         ★ 改造重点 ★
  ① 文档级摘要：每篇 doc 调一次 LLM，产出 ~1-2K tokens 的 doc summary，仅在内存中流转
  ② Per-chunk contextualize：
     • 文本 chunk → embedding_text = "[CTX] " + context_blurb + "\n\n" + content
     • 特殊 chunk → embedding_text = "[CTX] " + context_blurb + "\n\n[DESC] " + semantic_description
  ③ content 字段保持 raw，前端 EvidencePanel 展示零影响
        ▼
Stage 4 (Index)          不动；自然把 contextualized embedding_text 写进 Milvus + ES
        ▼
检索路径 (server/core)    完全不动
```

**新增 / 改造的文件**：

| 文件 | 改动 |
|------|------|
| `pipeline/summarize.py` | 重构为 `pipeline/contextualize.py`（或保留文件名扩展逻辑），核心函数 `enrich_chunks` 替代现有 `enrich_chunk_summaries` |
| `pipeline/contextualizer.py`（新）| `Contextualizer` 抽象 + `DeepSeekContextualizer` + `AnthropicContextualizer` 两份实现 |
| `pipeline/run.py` | Stage 3.5 调用点改名，progress callback 反映 "all chunks" |
| `pipeline/config.py` | 新增 `contextualize_provider`（默认 `"deepseek"`）、`contextualize_concurrency`（默认 8）|
| `pyproject.toml` | 加 optional dep `anthropic`（extra `[contextualize-anthropic]`）|
| 测试 | 新增 `tests/pipeline/test_contextualizer.py` + `tests/pipeline/test_contextualize_stage.py` |

**回退路径**：删除/不合并 feature 分支即可。`master` 上 `pipeline/summarize.py` 旧版本完全不受影响。

## Contextualizer Interface (Section 2 of detailed design)

```python
# pipeline/contextualizer.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ContextualizeRequest:
    doc_summary: str            # 文档级摘要 (~1-2K tokens)
    parent_section_text: str    # chunk 所在 section 的文本（已是 ≤4K，透传无截断）
    chunk_content: str          # raw chunk 内容
    chunk_kind: Literal["text", "table", "formula", "image"]
    section_path: list[str]     # ["Eurocode 2", "Section 3", "3.2 Concrete", "3.2.1 General"]
    chunk_alt: str = ""         # 仅 IMAGE：alt 文字

@dataclass(frozen=True)
class ContextualizeResult:
    context_blurb: str          # 永远存在 (~50-150 tokens)
    semantic_description: str   # 仅特殊 chunk 非空；text chunk 为空字符串

class Contextualizer(ABC):
    @abstractmethod
    async def generate_doc_summary(
        self, source_title: str, doc_outline_text: str
    ) -> str:
        """Per-document, called once per Stage 3.5 invocation."""

    @abstractmethod
    async def contextualize_chunk(
        self, request: ContextualizeRequest
    ) -> ContextualizeResult:
        """Per-chunk."""

    @property
    @abstractmethod
    def name(self) -> str:
        """For logging/debugging."""

def build_contextualizer(config: PipelineConfig) -> Contextualizer:
    """Factory；config.contextualize_provider ∈ {'deepseek', 'anthropic'}."""
    provider = config.contextualize_provider.lower()
    if provider == "deepseek":
        return DeepSeekContextualizer(config)
    if provider == "anthropic":
        # 仅在此 import，避免未装 anthropic 包时导入失败
        from pipeline.contextualizer_anthropic import AnthropicContextualizer
        return AnthropicContextualizer(config)
    raise ValueError(f"Unknown contextualize_provider: {provider}")
```

### Implementations

**`DeepSeekContextualizer`**：
- 复用现有 `AsyncOpenAI` 客户端模式（同 `summarize.py:_get_client`）
- Prompt 顺序固定：`[系统指令] → [doc_summary] → [section_path] → [parent_section] → [chunk]`
- 让 DeepSeek 自动前缀 KV cache 在同文档多 chunk 之间命中
- 无显式 cache API 调用

**`AnthropicContextualizer`**：
- 新增 `anthropic` SDK（optional dep）
- 使用 `cache_control: {"type": "ephemeral"}` 显式标记 `doc_summary` + `parent_section` 为可缓存
- per-chunk 只变 chunk 部分 → prompt cache 高命中率

### Prompt Templates（英文，对齐英文 Eurocode 语料）

**Doc summary prompt**（一篇 doc 一次）：
```
Below is the outline and excerpts of a regulatory/standards document titled '{title}'.
In 200-400 words, summarize its scope, structure, and key technical topics.
This summary will be used as context to improve search retrieval of individual chunks.

Outline:
{doc_outline_text}
```

**Per-chunk text contextualize prompt**：
```
Document summary: {doc_summary}

Section path: {" > ".join(section_path)}

Section containing the chunk:
{parent_section_text}

Chunk to situate:
{chunk_content}

In 1-3 sentences, give a short context that situates this chunk within the document for retrieval purposes. Output only the context, no preamble.
```

**Per-chunk special (table/formula/image) contextualize prompt**（要求 JSON 输出）：
```
Document summary: {doc_summary}
Section path: {" > ".join(section_path)}
Section containing the element:
{parent_section_text}

The element ({kind}) to situate:
{chunk_content}
{("Image alt text: " + chunk_alt) if kind == "image" else ""}

Respond with a JSON object exactly matching this schema:
{
  "context": "1-2 sentence context situating this element within the document",
  "description": "natural-language description of what this {kind} expresses (factors, formula meaning, figure subject, etc.)"
}
Output only the JSON, no preamble.
```

JSON 解析失败的降级：
- 整段输出当 `context_blurb`，`semantic_description` 留空
- `logger.warning("contextualize_json_parse_failed", chunk_id=..., raw=...[:200])`
- chunk 不会丢，只是退化为"低质量 contextualize"

## Pipeline Integration (Section 3 of detailed design)

### Per-document 处理流程

```python
for doc in documents:
    chunks_of_doc = [c for c in all_chunks if c.metadata.source == doc.source]

    # 1. 文档级摘要（1 次 LLM 调用）
    outline_text = build_outline_from_tree(doc.tree)  # 纯字符串，无 LLM
    doc_summary = await contextualizer.generate_doc_summary(
        source_title=doc.source_title,
        doc_outline_text=outline_text,
    )

    # 2. 并发 per-chunk contextualize
    semaphore = asyncio.Semaphore(config.contextualize_concurrency)

    async def _one(chunk: Chunk) -> ContextualizeResult:
        async with semaphore:
            return await contextualizer.contextualize_chunk(ContextualizeRequest(
                doc_summary=doc_summary,
                parent_section_text=_resolve_parent_section_text(chunk, all_chunks),
                chunk_content=chunk.content,
                chunk_kind=_chunk_kind(chunk),
                section_path=chunk.metadata.section_path,
                chunk_alt=_extract_alt_if_image(chunk),
            ))

    results = await asyncio.gather(*[_one(c) for c in chunks_of_doc], return_exceptions=True)

    # 3. 替换 embedding_text，content 不动
    for chunk, result in zip(chunks_of_doc, results):
        if isinstance(result, Exception):
            logger.warning("contextualize_failed", chunk_id=chunk.chunk_id, exc=str(result))
            continue  # fallback: keep raw embedding_text
        chunk.embedding_text = build_embedding_text(chunk, result)

    progress_callback(...)
```

### `build_embedding_text` 规则

```python
def build_embedding_text(chunk: Chunk, r: ContextualizeResult) -> str:
    if chunk.metadata.element_type == ElementType.TEXT:
        # text chunk（含 child / split / parent）：context + raw content
        return f"[CTX] {r.context_blurb}\n\n{chunk.content}"
    # table / formula / image：context + semantic description, 不含原 markdown
    return f"[CTX] {r.context_blurb}\n\n[DESC] {r.semantic_description}"
```

### `parent_section_text` 解析规则

| chunk 类型 | parent_section_text 取自 |
|------------|--------------------------|
| child text（叶 section 整段或 split 分片）| `metadata.parent_chunk_id` 指向的 parent chunk 的 `content` |
| parent text | 它本身的 `content`（自己即 combined）|
| special（table/formula/image）| `metadata.parent_text_chunk_id` 指向的 chunk 的 `content` |

依赖 chunking-fix 子项目已修好的 parent-child 链——这就是为什么本子项目必须等 sub-project 1 落地。

### `build_outline_from_tree`（纯函数，无 LLM）

递归遍历 `DocumentNode` 树：

```python
def build_outline_from_tree(tree: DocumentNode, *, first_para_max_chars: int = 200) -> str:
    """生成文档大纲文本：每节标题 + 该节直接 content 的第一段非空文字（截到 200 char）。"""
    lines: list[str] = []
    for node, depth in _walk_with_depth(tree):
        if node.element_type != ElementType.SECTION:
            continue
        indent = "  " * depth
        lines.append(f"{indent}{node.title}")
        first_para = _first_nonempty_paragraph(node.content)[:first_para_max_chars]
        if first_para:
            lines.append(f"{indent}  {first_para}…")
    text = "\n".join(lines)
    # 极端 outlier 安全网
    if _estimate_tokens(text) > 50000:
        logger.warning("outline_fallback_titles_only", source=tree.source)
        return _build_titles_only_outline(tree)
    return text
```

### 输入 token 预算

总输入到 per-chunk LLM 调用：1.5K (summary) + 4K (parent) + 0.8K (chunk) + 0.5K (system prompt) ≈ **7K tokens**。DeepSeek 64K 完全兜得住，并发 8 路无压力。

## Sections to Design After Sub-project 1 Lands

下列章节在 sub-project 2 实施前需要补全：

- **Section 4**: 配置项与 env 变量清单（`contextualize_provider`, `contextualize_concurrency`, `ANTHROPIC_API_KEY` 等）
- **Section 5**: 失败处理详细规则（哪些重试、哪些降级、哪些 fail-fast）
- **Section 6**: 测试策略（unit / integration / fixture 选取）
- **Section 7**: Acceptance criteria + Rollback plan

这些章节内容大体已在 brainstorming 讨论中拍定，sub-project 1 落地后整理成稿即可。

## Out of Scope

- 评测脚本 / 自动化 A/B harness（用户自己跑主观对比）
- 重 chunk 切分策略（由 sub-project 1 完成）
- 检索端 (`server/core/retrieval.py`) 任何改动
- 多语言切换 prompt（语料是英文 Eurocode，prompt 一律英文）
- 视觉 LLM 路径
- doc summary 持久化层
- 评测集合采购 / 标注

## Open Questions

待 sub-project 1 落地后再确认：

1. chunking-fix 实施后，chunk 总数从 ~700 涨到多少？影响 LLM 调用总成本估算
2. parent chunks 实际数量与 token 分布？影响"是否 contextualize parents"的成本判断
3. DeepSeek 自动前缀 KV cache 实测命中率？决定是否值得切换 Anthropic provider

## References

- [Anthropic Contextual Retrieval (2024-09)](https://www.anthropic.com/news/contextual-retrieval)
- [Sub-project 1: Chunking Fix Design](/Users/youngz/webdav/Euro_QA/docs/superpowers/specs/2026-05-03-chunking-fix-design.md)
- 现有相关代码：
  - `pipeline/summarize.py` - 现有 Stage 3.5 实现（待重构）
  - `pipeline/index.py` - 索引层（不动，但确认 `embedding_text` 进 Milvus + ES）
  - `server/models/schemas.py` - `Chunk` / `ChunkMetadata` 数据模型
