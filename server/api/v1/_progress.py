"""SSE progress event formatting helpers for query endpoints."""

from __future__ import annotations

import json
import time
import uuid

from structlog.contextvars import get_contextvars

from server.agents.evidence import EvidenceBundle
from server.agents.tool_progress import ToolSubStep

_QUESTION_TYPE_LABELS = {
    "rule": "规则/假设类问题",
    "parameter": "参数/限值类问题",
    "calculation": "计算类问题",
    "mechanism": "机理/影响因素类问题",
}


def _field_value(payload: object, key: str) -> object:
    """Read a value from a dict, model, enum-like object, or namespace."""
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _enum_value(payload: object) -> str | None:
    """Normalize enum-like values to a displayable string."""
    if payload is None:
        return None
    value = getattr(payload, "value", payload)
    return str(value) if value is not None else None


def _target_summary(target_hint: object) -> str:
    """Build a compact user-facing target string from routing hints."""
    parts: list[str] = []
    document = _field_value(target_hint, "document")
    clause = _field_value(target_hint, "clause")
    obj = _field_value(target_hint, "object")
    if document:
        parts.append(str(document))
    if clause:
        parts.append(f"Clause {clause}")
    if obj:
        parts.append(str(obj))
    return " ".join(parts)


def _source_count(chunks: list[object]) -> int:
    """Count distinct source labels in retrieved chunks."""
    sources: set[str] = set()
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None)
        source = getattr(metadata, "source", "")
        if source:
            sources.add(str(source))
    return len(sources)


def _progress_event(
    *,
    stage: str,
    status: str,
    title: str,
    summary: str,
    started_at: float,
    facts: dict | None = None,
) -> dict:
    """Create one query progress SSE payload."""
    return {
        "id": uuid.uuid4().hex,
        "stage": stage,
        "status": status,
        "title": title,
        "summary": summary,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "facts": facts or {},
        "request_id": get_contextvars().get("request_id", ""),
    }


def _progress_sse_event(
    *,
    stage: str,
    status: str,
    title: str,
    summary: str,
    started_at: float,
    facts: dict | None = None,
) -> dict[str, str]:
    """Create one progress SSE event."""
    return {
        "event": "progress",
        "data": json.dumps(
            _progress_event(
                stage=stage,
                status=status,
                title=title,
                summary=summary,
                started_at=started_at,
                facts=facts,
            ),
            ensure_ascii=False,
        ),
    }


def _commentary_sse_event(text: str, started_at: float) -> dict[str, str]:
    """Create one commentary SSE event for agent progress narration."""
    return {
        "event": "commentary",
        "data": json.dumps(
            {
                "text": text,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "request_id": get_contextvars().get("request_id", ""),
            },
            ensure_ascii=False,
        ),
    }


def _error_sse_event(*, code: int, message: str) -> dict[str, str]:
    """Create one error SSE event."""
    return {
        "event": "error",
        "data": json.dumps({"code": code, "message": message}, ensure_ascii=False),
    }


def _tool_progress_sse_event(
    step: ToolSubStep,
    started_at: float,
) -> dict[str, str]:
    """Create one tool sub-step SSE event."""
    return {
        "event": "tool_progress",
        "data": json.dumps(
            {
                "tool_name": step.tool_name,
                "step": {
                    "step_id": step.step_id,
                    "status": step.status,
                    "title": step.title,
                    "summary": step.summary,
                    "metadata": step.metadata,
                    "elapsed_ms": step.elapsed_ms,
                    "parent_step_id": step.parent_step_id,
                },
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "request_id": get_contextvars().get("request_id", ""),
            },
            ensure_ascii=False,
        ),
    }


def _understanding_summary(analysis: object) -> tuple[str, dict]:
    """Summarize query-understanding output for end users."""
    question_type = _enum_value(_field_value(analysis, "question_type"))
    label = _QUESTION_TYPE_LABELS.get(question_type or "", "规范问答问题")
    target = _target_summary(_field_value(analysis, "target_hint"))
    if target:
        summary = f"识别为{label}，优先查找 {target}。"
    else:
        summary = f"识别为{label}，将进行跨文档规范检索。"
    facts = {"question_type": question_type}
    if target:
        facts["target"] = target
    return summary, facts


def _retrieval_summary(result: object) -> tuple[str, dict]:
    """Summarize retrieved evidence counts without exposing raw chunks."""
    chunks = list(getattr(result, "chunks", []) or [])
    ref_chunks = list(getattr(result, "ref_chunks", []) or [])
    evidence_count = len(chunks) + len(ref_chunks)
    source_count = _source_count(chunks + ref_chunks)
    if evidence_count == 0:
        summary = "暂未稳定定位到规范证据，回答会明确说明当前证据不足。"
    elif source_count > 0:
        summary = (
            f"找到 {evidence_count} 条相关规范证据，覆盖 {source_count} 个文档来源。"
        )
    else:
        summary = f"找到 {evidence_count} 条相关规范证据。"
    return summary, {
        "evidence_count": evidence_count,
        "source_count": source_count,
    }


def _reference_summary(result: object) -> tuple[str, dict]:
    """Summarize deterministic and fallback cross-reference closure."""
    resolved_refs = list(getattr(result, "resolved_refs", []) or [])
    unresolved_refs = list(getattr(result, "unresolved_refs", []) or [])
    ref_chunks = list(getattr(result, "ref_chunks", []) or [])
    if resolved_refs and unresolved_refs:
        summary = (
            f"已补齐 {', '.join(resolved_refs)}；"
            f"仍有 {', '.join(unresolved_refs)} 未补齐。"
        )
    elif resolved_refs:
        summary = f"已补齐 {', '.join(resolved_refs)}。"
    elif unresolved_refs:
        summary = f"仍有 {', '.join(unresolved_refs)} 未补齐，回答会提示证据不足。"
    elif ref_chunks:
        summary = f"已补齐 {len(ref_chunks)} 条表格、公式或附录引用。"
    else:
        summary = "未发现必须补充的表格、公式或附录引用。"
    return summary, {
        "resolved_refs": resolved_refs,
        "unresolved_refs": unresolved_refs,
    }


def _guide_summary(result: object) -> tuple[str, str, dict]:
    """Summarize Designers' Guide and worked-example evidence."""
    guide_count = len(getattr(result, "guide_chunks", []) or [])
    example_count = len(getattr(result, "guide_example_chunks", []) or [])
    total = guide_count + example_count
    facts = {"guide_count": guide_count, "example_count": example_count}
    if total == 0:
        return "skipped", "当前问题未命中可用的 Designers' Guide 参考或算例。", facts
    return (
        "completed",
        f"找到 {total} 条 Designers' Guide 参考，可作为理解补充。",
        facts,
    )


def _agent_stage_summary(bundle: EvidenceBundle) -> tuple[str, dict]:
    """Summarize the agent routing outcome for progress payloads."""
    facts: dict[str, object] = {
        "needs_rag": bundle.has_rag_evidence,
        "tool_calls": len(bundle.tool_trace),
    }
    if bundle.has_rag_evidence:
        facts["chunk_count"] = bundle.chunk_count
        summary = f"已确认为规范问题，检索到 {bundle.chunk_count} 条证据。"
    elif bundle.tool_trace:
        summary = "Agent 已调用工具但未形成可引用规范证据，直接回复。"
    else:
        summary = "识别为闲聊、上下文充足或需澄清的问题，直接回复。"
    return summary, facts
