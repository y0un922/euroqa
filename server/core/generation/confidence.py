from __future__ import annotations

import json

import structlog

from server.core.generation.citations import _extract_json_text
from server.core.generation.sources import _parse_source_payload
from server.models.schemas import Chunk, Confidence, QueryResponse

logger = structlog.get_logger()


def _infer_answer_confidence(
    scores: list[float] | None,
    has_sources: bool,
    groundedness: str | None = None,
) -> Confidence:
    """Infer external answer confidence from retrieval evidence."""
    if not has_sources:
        return Confidence.LOW

    normalized_groundedness = (groundedness or "").strip().lower()
    if normalized_groundedness == "not_grounded":
        return Confidence.LOW

    if not scores:
        return Confidence.MEDIUM

    top = max(scores)
    if top >= 0.85:
        if normalized_groundedness == "partial":
            return Confidence.MEDIUM
        return Confidence.HIGH
    if top >= 0.55:
        return Confidence.MEDIUM
    return Confidence.LOW


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
            for source in (_parse_source_payload(item) for item in raw_sources)
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
