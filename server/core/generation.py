"""Generation layer: prompt assembly + LLM call + structured output parsing."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import tiktoken
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.models.schemas import Chunk, Confidence, ElementType, QueryResponse, Source

logger = structlog.get_logger()

_enc = tiktoken.get_encoding("cl100k_base")
def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _extract_json_text(raw: str) -> str:
    """从可能带 Markdown 代码块的文本中提取 JSON 内容。"""
    cleaned = raw
    if "```json" in cleaned:
        return cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in cleaned:
        return cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return cleaned


def _collect_pending_source_indexes(sources: list[Source]) -> list[int]:
    """收集仍需补齐翻译的 source 下标。"""
    return [
        index
        for index, source in enumerate(sources)
        if not source.translation.strip() and source.original_text.strip()
    ]


def _build_document_id(source: str) -> str:
    """Build a stable document identifier from source metadata."""
    normalized = re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", source.strip())
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _build_locator_text(content: str, max_length: int = 240) -> str:
    """Build a shorter normalized text snippet suitable for PDF search."""
    normalized = re.sub(r"\[\->\s*[^\]]*\]", " ", content)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        normalized = re.sub(r"\s+", " ", content).strip()
    if len(normalized) <= max_length:
        return normalized

    truncated = normalized[:max_length].rsplit(" ", 1)[0].strip()
    return truncated or normalized[:max_length].strip()


def _build_highlight_text(content: str, page_numbers: list[int]) -> str:
    """Build the full text used for PDF paragraph highlighting.

    Keep the full chunk semantics intact and let the frontend derive the best
    page-local overlap against the rendered PDF text layer. Only retrieval
    markers and simple HTML table wrappers are stripped out here.
    """
    del page_numbers

    normalized = re.sub(r"\[\->\s*[^\]]*\]", "", content)
    normalized = re.sub(r"</?(?:table|thead|tbody|tr|td|th|br)\b[^>]*>", " ", normalized)
    normalized = normalized.strip()
    if normalized:
        return normalized
    return content.strip()


def _normalize_table_html(content: str) -> str:
    """Normalize HTML table strings for robust matching."""
    return re.sub(r"\s+", "", content).casefold()


def _extract_table_caption(content: str) -> str:
    """Extract the caption line when a table chunk starts with one."""
    for line in content.splitlines():
        candidate = line.strip()
        if re.match(r"^Table\s+[A-Z]?\d+(?:\.\d+)*\b", candidate):
            return candidate
        if candidate:
            break
    return ""


def _extract_table_html(content: str) -> str:
    """Extract the HTML table fragment from a chunk when present."""
    match = re.search(r"<table\b[^>]*>.*?</table>", content, re.DOTALL)
    return match.group(0).strip() if match else ""


@lru_cache(maxsize=64)
def _load_content_list_payload(content_list_path: str) -> list[dict[str, Any]]:
    """Load a parsed MinerU content_list file from disk."""
    path = Path(content_list_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("content_list_load_failed", path=content_list_path, exc_info=True)
        return []
    return payload if isinstance(payload, list) else []


def _resolve_content_list_path(config: ServerConfig, document_id: str) -> Path:
    """Resolve the MinerU content_list path for a document."""
    return Path(config.parsed_dir) / document_id / f"{document_id}_content_list.json"


def _extract_content_list_caption(entry: dict[str, Any]) -> str:
    """Normalize content_list table captions into a single string."""
    caption = entry.get("table_caption", [])
    if isinstance(caption, list):
        return " ".join(str(part).strip() for part in caption if str(part).strip()).strip()
    if isinstance(caption, str):
        return caption.strip()
    return ""


def _resolve_table_source_geometry(
    chunk: Chunk,
    document_id: str,
    config: ServerConfig,
) -> tuple[list[float], str]:
    """Resolve bbox and page for a table chunk from MinerU content_list."""
    content_list_path = _resolve_content_list_path(config, document_id)
    entries = _load_content_list_payload(str(content_list_path))
    if not entries:
        return [], ""

    chunk_caption = _extract_table_caption(chunk.content)
    chunk_table_html = _extract_table_html(chunk.content)
    normalized_chunk_html = _normalize_table_html(chunk_table_html) if chunk_table_html else ""
    candidate_page_indexes = set(chunk.metadata.page_file_index)

    best_bbox: list[float] = []
    best_page = ""
    best_score = -1

    for entry in entries:
        if entry.get("type") != "table":
            continue
        bbox = entry.get("bbox")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, (int, float)) for value in bbox)
        ):
            continue

        score = 0
        page_idx = entry.get("page_idx")
        if isinstance(page_idx, int) and page_idx in candidate_page_indexes:
            score += 4

        entry_caption = _extract_content_list_caption(entry)
        if chunk_caption and entry_caption and entry_caption == chunk_caption:
            score += 8
        elif chunk_caption and entry_caption and entry_caption in chunk.content:
            score += 4

        entry_table_html = str(entry.get("table_body", "")).strip()
        if normalized_chunk_html and entry_table_html:
            normalized_entry_html = _normalize_table_html(entry_table_html)
            if normalized_entry_html == normalized_chunk_html:
                score += 10
            elif normalized_entry_html and normalized_entry_html in _normalize_table_html(chunk.content):
                score += 5

        if score <= best_score:
            continue

        best_score = score
        best_bbox = [float(value) for value in bbox]
        best_page = str(page_idx + 1) if isinstance(page_idx, int) else ""

    if best_score < 5:
        return [], ""
    return best_bbox, best_page


def _normalize_sources(sources: list[Source]) -> list[Source]:
    """Backfill source fields using backend normalization rules."""
    normalized_sources: list[Source] = []
    for source in sources:
        document_id = source.document_id.strip() or _build_document_id(source.file)
        highlight_text = source.highlight_text.strip() or _build_highlight_text(
            source.original_text,
            [int(source.page)] if str(source.page).strip().isdigit() else [],
        )
        locator_text = source.locator_text.strip() or _build_locator_text(
            highlight_text or source.original_text
        )
        normalized_sources.append(
            source.model_copy(
                update={
                    "document_id": document_id,
                    "highlight_text": highlight_text,
                    "locator_text": locator_text,
                    "translation": "",
                }
            )
        )
    return normalized_sources


def _parse_source_payload(payload: object) -> Source | None:
    """Parse a single source payload leniently and keep partial data when possible."""
    if not isinstance(payload, dict):
        return None

    return Source(
        file=str(payload.get("file", "")),
        document_id=str(payload.get("document_id", "")),
        element_type=payload.get("element_type", ElementType.TEXT),
        bbox=payload.get("bbox", []),
        title=str(payload.get("title", "")),
        section=str(payload.get("section", "")),
        page=payload.get("page", ""),
        clause=str(payload.get("clause", "")),
        original_text=str(payload.get("original_text", "")),
        locator_text=str(payload.get("locator_text", "")),
        highlight_text=str(payload.get("highlight_text", "")),
        translation=str(payload.get("translation", "")),
    )


# 系统提示词：指导 LLM 以 Eurocode 专家身份回答问题
_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师理解和查询规范内容。

规则：
1. 所有回答必须基于提供的规范原文，不要编造规范中不存在的内容。
2. 回答用中文，但保留原文中的关键术语（如条款编号、表格编号、公式编号）。
3. 必须标注出处（文件名、章节、页码、条款号），且条款号只能使用检索片段头部标注的 Clause 字段值，不要引用片段正文中提到的其他条款号作为出处。
4. sources 字段只返回原文定位信息，不要在 sources.translation 中填写中文翻译，统一返回空字符串。
5. 如果需要推理，说明推理过程。
6. 先给出基于当前片段可以直接确认的答案，不要先写空泛否定。
7. 如果当前片段只能支持部分答案，先明确写出"当前片段可确认"的内容，再单独说明"仍需补充"的信息或应参考的其他规范。
8. 只有在当前片段连部分答案都无法支持时，才说明"根据当前检索片段无法确认"，并解释具体缺口。

输出格式：严格 JSON，结构如下：
{
  "answer": "中文回答",
  "sources": [{"file": "EN 1990:2002", "title": "...", "section": "...", "page": 28, "clause": "...", "original_text": "...", "translation": ""}],
  "related_refs": ["相关的其他规范引用"],
  "confidence": "high|medium|low"
}"""

# 流式模式专用提示词：输出 Markdown，不输出 JSON
_STREAM_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师理解和查询规范内容。

规则：
1. 所有回答必须严格基于提供的规范片段，不得编造规范中不存在的要求、数值或例外。
2. 直接输出 Markdown 正文，不要输出 JSON，不要输出 ```json 代码块，也不要输出 answer/sources/confidence 等键名。
3. 回答必须使用中文，并保留关键英文术语、条款编号、表格编号、公式编号。
4. 先给出工程师最关心的直接答案，再给出依据和说明；复杂问题可使用二级标题、项目符号或表格来组织内容。
5. 引用规则（非常重要）：
   - 只能引用检索片段头部标注的元数据（文件名、条款号、页码），不要引用片段正文中提到的其他条款号或交叉引用。
   - 格式示例：[EN 1990:2002 | 2.3(1) | p.28]，其中条款号必须来自片段标注的 Clause 字段。
   - 如果需要提及片段正文中的其他条款号（如"详见 A1.2.1"），直接写在正文中即可，不要用方括号包裹成引用格式。
6. 如果当前片段只能支持部分答案，先写"当前片段可确认"的部分，再写"仍需补充"或"需参考其他规范"的部分。
7. 不要把"根据当前检索片段无法确认"作为开头；只有在当前片段连部分答案都无法支持时，才可以使用这类表述。
8. 可以解释或翻译原文，但不要虚构来源。

目标：输出一段适合前端直接渲染的高质量 Markdown 中文答案。"""

_SOURCE_TRANSLATION_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，负责把规范原文片段翻译成简洁、准确的中文解释。

规则：
1. 严格基于给定原文翻译，不补充原文没有的信息。
2. 保留关键英文术语、条款号、表格号、公式号和文件名。
3. 输出应适合直接展示在"中文解释"面板中，优先使用自然中文，不写额外说明。
4. 如果原文中包含表格、枚举、层级说明或分点要求，请优先转换成 GFM Markdown 结构：
   - 表格优先转换为 Markdown table
   - 条列内容优先转换为项目列表或有序列表
   - 普通说明保持自然段
5. 不要输出 HTML 标签，不要输出 Markdown 代码块围栏。
6. 只输出严格 JSON，格式如下：
{
  "translations": [
    {"index": 0, "translation": "中文解释"}
  ]
}"""


def _should_enable_reasoning(config: ServerConfig) -> bool:
    """Return whether the current model/provider should request thinking tokens."""
    if not config.llm_enable_thinking:
        return False

    model_name = config.llm_model.lower()
    base_url = config.llm_base_url.lower()
    return "qwen" in model_name or "dashscope.aliyuncs.com" in base_url


def _build_stream_completion_kwargs(config: ServerConfig) -> dict[str, Any]:
    """Build optional kwargs for reasoning-capable streaming models."""
    kwargs: dict[str, Any] = {}
    if _should_enable_reasoning(config):
        kwargs["extra_body"] = {"enable_thinking": True}
    return kwargs


def build_prompt(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
) -> str:
    """将检索结果组装为发送给 LLM 的用户提示词。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段（已排序）
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录（多轮会话场景）

    Returns:
        组装完成的提示词字符串
    """
    parts: list[str] = []

    # 术语对照（帮助 LLM 理解中英对应关系）
    if glossary_terms:
        terms = ", ".join(f"{zh}={en}" for zh, en in glossary_terms.items())
        parts.append(f"相关术语对照：{terms}\n")

    # 主要检索片段
    parts.append("检索到的规范内容：\n")
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        page_str = ",".join(map(str, meta.page_numbers))
        section_str = " > ".join(meta.section_path)
        clause_str = ", ".join(meta.clause_ids[:3]) if meta.clause_ids else ""
        source_info = f"{meta.source}, Page {page_str}, {section_str}"
        if clause_str:
            source_info += f", Clause {clause_str}"
        parts.append(f"[{i}] {source_info}\n{chunk.content}\n")

    # Token budget check: only include parent if child+parent <= 3000 tokens
    child_tokens = sum(_count_tokens(c.content) for c in chunks)
    if parent_chunks and child_tokens < 3000:
        remaining = 3000 - child_tokens
        parts.append("\n扩展上下文（章节级）：\n")
        for pc in parent_chunks[:2]:
            pc_text = pc.content[:2000]
            if _count_tokens(pc_text) <= remaining:
                parts.append(f"[Parent] {' > '.join(pc.metadata.section_path)}\n{pc_text}\n")
                remaining -= _count_tokens(pc_text)

    # 历史对话（仅保留最近两轮，避免上下文膨胀）
    if conversation_history:
        parts.append("\n之前的对话：\n")
        for h in conversation_history[-2:]:
            parts.append(f"Q: {h['question']}\nA: {h['answer'][:500]}\n")

    parts.append(f"\n用户问题：{question}")
    return "\n".join(parts)


def _build_sources_from_chunks(
    chunks: list[Chunk],
    limit: int = 5,
    config: ServerConfig | None = None,
) -> list[Source]:
    """从检索结果的 metadata 直接构建 Source，不依赖 LLM JSON 解析。"""
    sources: list[Source] = []
    cfg = config or ServerConfig()
    for chunk in chunks[:limit]:
        meta = chunk.metadata
        document_id = _build_document_id(meta.source)
        # Primary: use bbox from pipeline metadata
        bbox = list(meta.bbox) if meta.bbox else []
        resolved_page = str(meta.bbox_page_idx + 1) if meta.bbox_page_idx >= 0 else ""

        # Fallback for table: runtime content_list traversal (legacy data without pipeline bbox)
        if not bbox and meta.element_type == ElementType.TABLE:
            bbox, resolved_page = _resolve_table_source_geometry(
                chunk,
                document_id,
                cfg,
            )

        sources.append(
            Source(
                file=meta.source,
                document_id=document_id,
                element_type=meta.element_type,
                bbox=bbox,
                title=meta.source_title,
                section=" > ".join(meta.section_path),
                page=resolved_page or (str(meta.page_numbers[0]) if meta.page_numbers else ""),
                clause=", ".join(meta.clause_ids[:2]) if meta.clause_ids else "",
                original_text=chunk.content,
                locator_text=_build_locator_text(chunk.content),
                highlight_text=_build_highlight_text(
                    chunk.content,
                    meta.page_numbers,
                ),
                translation="",
            )
        )
    return sources


def _build_source_translation_prompt(
    sources: list[Source], indexes: list[int] | None = None
) -> str:
    """为缺失翻译的 source 构造批量翻译提示词。"""
    payload: list[dict[str, str | int]] = []
    selected_indexes = indexes or _collect_pending_source_indexes(sources)
    for index in selected_indexes:
        source = sources[index]
        if source.translation.strip() or not source.original_text.strip():
            continue
        payload.append(
            {
                "index": index,
                "file": source.file,
                "section": source.section,
                "clause": source.clause,
                "original_text": source.original_text,
            }
        )

    if not payload:
        return ""

    return (
        "请把以下 Eurocode 来源原文翻译成可直接展示的中文解释。"
        "如果内容中存在表格、条列或层级结构，请优先转成适合前端渲染的 Markdown。"
        "返回严格 JSON，不要输出额外文字。\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


async def _call_source_translation_llm(
    prompt: str,
    config: ServerConfig | None = None,
) -> str:
    """调用 LLM 生成 source 中文翻译。"""
    cfg = config or ServerConfig()
    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    response = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": _SOURCE_TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content.strip()


def _parse_source_translation_map(raw: str) -> dict[int, str]:
    """解析 source 翻译响应，返回 index -> translation 映射。"""
    payload = json.loads(_extract_json_text(raw))
    translation_map: dict[int, str] = {}
    for item in payload.get("translations", []):
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        translation = item.get("translation")
        if isinstance(index, int) and isinstance(translation, str):
            text = translation.strip()
            if text:
                translation_map[index] = text
    return translation_map


async def _translate_source_batch(
    sources: list[Source],
    indexes: list[int],
    config: ServerConfig | None = None,
) -> dict[int, str]:
    """对指定 source 子集执行一次翻译请求。"""
    prompt = _build_source_translation_prompt(sources, indexes)
    if not prompt:
        return {}

    raw = await _call_source_translation_llm(prompt, config)
    return _parse_source_translation_map(raw)


async def _fill_missing_source_translations(
    sources: list[Source],
    config: ServerConfig | None = None,
) -> list[Source]:
    """为缺失 translation 的 source 补齐中文解释。"""
    pending_indexes = _collect_pending_source_indexes(sources)
    if not pending_indexes:
        return sources

    translation_map: dict[int, str] = {}
    try:
        translation_map = await _translate_source_batch(sources, pending_indexes, config)
    except json.JSONDecodeError:
        logger.warning(
            "source_translation_fill_batch_parse_failed_retrying_individually",
            pending_count=len(pending_indexes),
            exc_info=True,
        )
        for index in pending_indexes:
            try:
                translation_map.update(
                    await _translate_source_batch(sources, [index], config)
                )
            except Exception:
                logger.warning(
                    "source_translation_single_fill_failed",
                    source_index=index,
                    exc_info=True,
                )
    except Exception:
        logger.warning("source_translation_fill_failed", exc_info=True)
        return sources

    return [
        source.model_copy(
            update={
                "translation": source.translation.strip()
                or translation_map.get(index, "")
            }
        )
        for index, source in enumerate(sources)
    ]


def _build_related_refs_from_chunks(chunks: list[Chunk], limit: int = 8) -> list[str]:
    """从检索结果中收集去重的关联引用。"""
    seen: set[str] = set()
    refs: list[str] = []
    for chunk in chunks:
        for ref in chunk.metadata.cross_refs:
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
                if len(refs) >= limit:
                    return refs
    return refs


def _infer_stream_confidence(scores: list[float] | None, has_sources: bool) -> Confidence:
    """根据检索分数推断置信度。"""
    if not has_sources:
        return Confidence.LOW
    if not scores:
        return Confidence.MEDIUM
    top = max(scores)
    if top >= 0.85:
        return Confidence.HIGH
    if top >= 0.55:
        return Confidence.MEDIUM
    return Confidence.LOW


def parse_llm_response(raw: str) -> QueryResponse:
    """解析 LLM 返回的原始文本为结构化 QueryResponse。

    支持三种场景：
    1. 纯 JSON 字符串
    2. 被 ```json ... ``` 包裹的 JSON
    3. 非 JSON 文本（降级为低置信度原文回答）

    Args:
        raw: LLM 返回的原始文本

    Returns:
        结构化的 QueryResponse 对象
    """
    # 提取被 Markdown 代码块包裹的 JSON
    cleaned = _extract_json_text(raw)

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("llm_response_top_level_not_dict")
        raw_sources = data.get("sources", [])
        if not isinstance(raw_sources, list):
            raw_sources = []
        sources = [
            source
            for source in (_parse_source_payload(item) for item in raw_sources[:5])
            if source is not None
        ]
        try:
            confidence = Confidence(data.get("confidence", "low"))
        except ValueError:
            confidence = Confidence.LOW
        return QueryResponse(
            answer=data.get("answer", ""),
            sources=sources,
            related_refs=data.get("related_refs", []),
            confidence=confidence,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("llm_response_parse_failed", raw=raw[:200])
        return QueryResponse(
            answer=raw,
            sources=[],
            related_refs=[],
            confidence=Confidence.LOW,
        )


async def generate_answer_stream(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
):
    """流式生成 LLM 回答，通过异步生成器逐步输出。

    使用 Markdown 专用 prompt，直接输出可渲染文本（不输出 JSON）。
    done 事件的 sources 从检索结果的 metadata 直接构建，不依赖 LLM 解析。

    Yields:
        (event_type, data) 元组
    """
    cfg = config or ServerConfig()
    prompt = build_prompt(question, chunks, parent_chunks, glossary_terms, conversation_history)

    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    try:
        stream = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": _STREAM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
            stream=True,
            **_build_stream_completion_kwargs(cfg),
        )
        async for token in stream:
            delta = token.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ("reasoning", {"text": reasoning})

            content = delta.content
            if content:
                yield ("chunk", {"text": content, "done": False})

        # 从检索结果直接构建结构化元数据，不依赖 LLM 输出
        sources = _build_sources_from_chunks(chunks, config=cfg)
        related_refs = _build_related_refs_from_chunks(chunks)
        confidence = _infer_stream_confidence(scores, has_sources=bool(sources))
        yield ("done", {
            "sources": [s.model_dump() for s in sources],
            "related_refs": related_refs,
            "confidence": confidence.value,
        })
    except Exception:
        logger.exception("llm_stream_failed")
        yield ("error", {"message": "LLM 服务暂时不可用"})


async def generate_answer(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
) -> QueryResponse:
    """调用 LLM 生成基于检索内容的回答。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录
        config: 服务器配置（为空时使用默认配置）

    Returns:
        结构化的 QueryResponse；LLM 调用失败时返回降级响应
    """
    cfg = config or ServerConfig()
    prompt = build_prompt(
        question, chunks, parent_chunks, glossary_terms, conversation_history
    )

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
        response = parse_llm_response(raw)
        canonical_sources = _normalize_sources(
            _build_sources_from_chunks(chunks, config=cfg)
        )
        return response.model_copy(update={"sources": canonical_sources})
    except Exception:
        logger.exception("llm_call_failed")
        return QueryResponse(
            answer="LLM 服务暂时不可用，以下是检索到的相关规范片段。",
            sources=[],
            confidence=Confidence.LOW,
            degraded=True,
        )
