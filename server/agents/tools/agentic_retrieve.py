from __future__ import annotations

import asyncio
import json
import re

from agents import RunContextWrapper, function_tool

from shared.reference_graph import extract_reference_labels
from server.agents.deps import QADeps
from server.agents.tool_progress import RETRIEVE_STEPS, ToolProgressEmitter
from server.agents.tools.retrieve import (
    _base_filters,
    _clamp_top_k,
    _limit_retrieval_result,
)
from server.core.evidence_planner import (
    EvidencePlan,
    EvidenceSlot,
    SourceInventoryItem,
    plan_evidence,
)
from server.core.query_understanding import analyze_query
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, RoutingTargetHint

_DEFAULT_TOP_K = 8
_MAX_SLOT_TOP_K = 6
_MAX_INFERRED_OBJECTS_PER_SLOT = 3
_VALUE_QUERY_RE = re.compile(
    r"取值|数值|系数|限值|参数|value|values?|factor|factors?|limit|limits?",
    re.IGNORECASE,
)
_OBJECT_REF_RE = re.compile(r"^(Table|Expression)\b", re.IGNORECASE)
_NUMERIC_VALUE_RE = re.compile(r"(?<!\d)(?:0\.\d+|1(?:\.\d+)?|[2-9](?:\.\d+)?)(?!\d)")
_REFERENCE_NUMBER_RE = re.compile(
    r"\b(?:Table|Figure)\s+[A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?"
    r"|\bExpression\s*\(\s*\d+(?:\.\d+)*\s*\)"
    r"|\bEN\s+\d{4}(?:-\d+(?:-\d+)?)?\b"
    r"|\b(?:Clause|Section|Annex)\s+[A-Z]?\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)


@function_tool
async def retrieve_agentic(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> str:
    """面向复合问题的证据规划检索：先拆分 evidence slots，再逐槽检索。"""
    return await _retrieve_agentic_impl(ctx, query, top_k=top_k)


@function_tool
async def list_sources(ctx: RunContextWrapper[QADeps]) -> str:
    """列出当前知识库可检索的 source 元数据清单。"""
    inventory = await _source_inventory(ctx)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "list_sources",
            "source_count": len(inventory),
        }
    )
    if not inventory:
        return "未能读取 source 清单；后续检索将不使用 source hint。"
    lines = [f"可用 source 共 {len(inventory)} 个："]
    for item in inventory[:20]:
        title = f" | {item.title}" if item.title and item.title != item.source else ""
        count = f" | chunks={item.chunk_count}" if item.chunk_count else ""
        lines.append(f"- {item.source}{title}{count}")
    return "\n".join(lines)


@function_tool
async def lookup_object(
    ctx: RunContextWrapper[QADeps],
    label: str,
    source: str = "",
    top_k: int = 3,
) -> str:
    """按 Table/Figure/Expression/Annex/Clause 标签精确查找规范对象。"""
    lookup = getattr(ctx.context.retriever, "lookup_object", None)
    if lookup is None:
        return "当前检索器不支持 lookup_object。"
    filters = _base_filters(ctx)
    if source.strip():
        filters["source"] = source.strip()
    chunks = await lookup(label, filters=filters, top_k=_clamp_top_k(top_k))
    if chunks:
        result = RetrievalResult(
            chunks=chunks,
            parent_chunks=[],
            scores=[1.0] * len(chunks),
            groundedness="partial",
        )
        ctx.context.bundle.add_retrieval(result)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "lookup_object",
            "label": label,
            "source": source.strip() or None,
            "chunk_count": len(chunks),
        }
    )
    return _format_chunk_list("对象查找结果", chunks)


@function_tool
async def open_chunk(
    ctx: RunContextWrapper[QADeps],
    chunk_id: str,
    neighbors: int = 1,
) -> str:
    """按 chunk_id 打开片段，可附带父级上下文。"""
    opener = getattr(ctx.context.retriever, "open_chunk", None)
    if opener is None:
        return "当前检索器不支持 open_chunk。"
    chunks = await opener(chunk_id, neighbors=max(0, min(int(neighbors), 2)))
    if chunks:
        result = RetrievalResult(
            chunks=chunks,
            parent_chunks=[],
            scores=[1.0] * len(chunks),
            groundedness="partial",
        )
        ctx.context.bundle.add_retrieval(result)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "open_chunk",
            "chunk_id": chunk_id,
            "neighbors": neighbors,
            "chunk_count": len(chunks),
        }
    )
    return _format_chunk_list("打开片段结果", chunks)


async def _retrieve_agentic_impl(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> str:
    effective_top_k = min(_clamp_top_k(top_k), _MAX_SLOT_TOP_K)
    progress = ToolProgressEmitter("retrieve_agentic", ctx.context.tool_progress)
    history = (
        ctx.context.conversation_state.history
        if ctx.context.conversation_state
        else None
    )

    await progress.start(
        "query_understanding",
        RETRIEVE_STEPS["query_understanding"]["title"],
        "正在理解问题并准备 evidence planning",
    )
    analysis = await analyze_query(
        query,
        ctx.context.glossary,
        ctx.context.config,
        history,
    )
    await progress.complete(
        "query_understanding",
        RETRIEVE_STEPS["query_understanding"]["title"],
        _format_understanding_summary(
            analysis,
            bool(analysis.rewritten_question and analysis.rewritten_question != query),
        ),
        metadata={
            "original_query": query,
            "rewritten_question": analysis.rewritten_question,
            "question_type": (
                analysis.question_type.value if analysis.question_type else None
            ),
            "expanded_queries": analysis.expanded_queries,
            "target_hint": _serialize_target_hint(analysis),
        },
    )

    await progress.start(
        "evidence_planning",
        "证据规划",
        "正在读取 source 清单并拆分证据需求",
    )
    inventory = await _source_inventory(ctx)
    plan = await plan_evidence(query, analysis, inventory, ctx.context.config)
    await progress.complete(
        "evidence_planning",
        "证据规划",
        f"生成 {len(plan.slots)} 个 evidence slot，strategy={plan.strategy}",
        metadata={
            "strategy": plan.strategy,
            "slot_count": len(plan.slots),
            "reason": plan.reason,
        },
    )

    slot_summaries: list[dict[str, object]] = []
    first_round_results = await asyncio.gather(
        *[
            _retrieve_slot(
                ctx,
                analysis=analysis,
                slot=slot,
                top_k=effective_top_k,
                progress=progress,
            )
            for slot in plan.slots
        ]
    )
    for slot, result in zip(plan.slots, first_round_results, strict=True):
        inferred_objects = _infer_required_object_labels(slot, result)
        if inferred_objects:
            result = await _lookup_slot_objects(
                ctx,
                slot=slot,
                result=result,
                labels=inferred_objects,
            )
            slot = slot.model_copy(
                update={
                    "object_labels": list(
                        dict.fromkeys([*slot.object_labels, *inferred_objects])
                    )
                }
            )
        status = _evaluate_slot(slot, result)
        if status != "missing" and _value_slot_lacks_values(slot, result):
            status = "missing"
        if status == "missing" and slot.retry_query:
            retry_slot = slot.model_copy(
                update={
                    "query": slot.retry_query,
                    "search_queries": [slot.retry_query],
                }
            )
            retry_result = await _retrieve_slot(
                ctx,
                analysis=analysis,
                slot=retry_slot,
                top_k=effective_top_k,
                progress=progress,
            )
            retry_status = _evaluate_slot(slot, retry_result)
            if retry_status != "missing" and _value_slot_lacks_values(
                retry_slot, retry_result
            ):
                retry_status = "missing"
            if _slot_status_rank(retry_status) > _slot_status_rank(status):
                status = retry_status
                result = retry_result
        slot_summaries.append(
            {
                "id": slot.id,
                "description": slot.description,
                "status": status,
                "chunk_count": len(result.chunks),
                "object_labels": slot.object_labels,
            }
        )
    agentic_groundedness = _groundedness_from_slot_summaries(slot_summaries, plan)
    ctx.context.bundle.groundedness = agentic_groundedness
    ctx.context.bundle.slot_results = slot_summaries
    ctx.context.bundle.unresolved_slots = [
        str(slot["description"])
        for slot in slot_summaries
        if slot["status"] == "missing"
    ]
    ctx.context.bundle.unresolved_refs = _merge_strings(
        ctx.context.bundle.unresolved_refs,
        [f"Evidence slot: {slot}" for slot in ctx.context.bundle.unresolved_slots],
    )

    ctx.context.bundle.tool_trace.append(
        {
            "tool": "retrieve_agentic",
            "query": query,
            "top_k": effective_top_k,
            "plan": _serialize_plan(plan),
            "slots": slot_summaries,
            "chunk_count": ctx.context.bundle.chunk_count,
            "groundedness": agentic_groundedness,
        }
    )
    return _format_agentic_summary(plan, slot_summaries, agentic_groundedness)


async def _retrieve_slot(
    ctx: RunContextWrapper[QADeps],
    *,
    analysis,
    slot: EvidenceSlot,
    top_k: int,
    progress: ToolProgressEmitter,
) -> RetrievalResult:
    filters = dict(analysis.filters)
    filters.update(_base_filters(ctx))
    if slot.source_hints:
        if len(slot.source_hints) == 1:
            filters["source"] = slot.source_hints[0]
            filters.pop("sources", None)
        else:
            filters["sources"] = slot.source_hints
            filters.pop("source", None)

    target_hint = analysis.target_hint
    if target_hint is None and slot.source_hints:
        target_hint = RoutingTargetHint(
            document=slot.source_hints[0],
            clause=None,
            object=", ".join(slot.object_labels) or None,
        )
    requested_objects = list(
        dict.fromkeys([*analysis.requested_objects, *slot.object_labels])
    )
    queries = slot.normalized_queries()
    await progress.start(
        f"slot_{slot.id}",
        f"证据槽 {slot.id}",
        f"正在检索：{slot.description}",
        parent_step_id="hybrid_search",
    )
    result = await ctx.context.retriever.retrieve(
        queries,
        original_query=slot.query,
        filters=filters,
        intent_label=analysis.intent_label,
        question_type=analysis.question_type,
        guide_hint=analysis.guide_hint,
        target_hint=target_hint,
        requested_objects=requested_objects,
        preferred_element_type=analysis.preferred_element_type,
        top_k=top_k,
        progress=None,
    )
    limited = _limit_retrieval_result(result, top_k)
    ctx.context.bundle.add_retrieval(limited)
    await progress.complete(
        f"slot_{slot.id}",
        f"证据槽 {slot.id}",
        f"找到 {len(limited.chunks)} 个片段，groundedness={limited.groundedness}",
        metadata={
            "chunk_count": len(limited.chunks),
            "groundedness": limited.groundedness,
            "queries": queries,
            "source_hints": slot.source_hints,
            "object_labels": slot.object_labels,
        },
        parent_step_id="hybrid_search",
    )
    return limited


async def _source_inventory(
    ctx: RunContextWrapper[QADeps],
) -> list[SourceInventoryItem]:
    lister = getattr(ctx.context.retriever, "list_sources", None)
    if lister is None:
        return []
    try:
        raw_items = await lister(filters=_base_filters(ctx))
    except Exception:
        return []
    inventory: list[SourceInventoryItem] = []
    for item in raw_items:
        try:
            inventory.append(SourceInventoryItem.model_validate(item))
        except Exception:
            continue
    return inventory


def _evaluate_slot(slot: EvidenceSlot, result: RetrievalResult) -> str:
    if not result.chunks:
        return "missing"
    object_labels = {label.lower() for label in slot.object_labels}
    if object_labels:
        resolved_labels = {
            chunk.metadata.object_label.lower()
            for chunk in [*result.chunks, *result.ref_chunks]
            if chunk.metadata.object_label
        }
        if object_labels & resolved_labels:
            return "satisfied"
        return "partial"
    if result.groundedness == "grounded":
        return "satisfied"
    return "partial"


def _groundedness_from_slot_summaries(
    slot_summaries: list[dict[str, object]],
    plan: EvidencePlan,
) -> str:
    required_slot_ids = {slot.id for slot in plan.slots if slot.required}
    required_statuses = [
        str(summary["status"])
        for summary in slot_summaries
        if str(summary["id"]) in required_slot_ids
    ]
    if not required_statuses:
        statuses = [str(summary["status"]) for summary in slot_summaries]
        return "grounded" if any(status == "satisfied" for status in statuses) else "partial"
    if all(status == "satisfied" for status in required_statuses):
        return "grounded"
    if any(status in {"satisfied", "partial"} for status in required_statuses):
        return "partial"
    return "not_grounded"


async def _lookup_slot_objects(
    ctx: RunContextWrapper[QADeps],
    *,
    slot: EvidenceSlot,
    result: RetrievalResult,
    labels: list[str],
) -> RetrievalResult:
    lookup = getattr(ctx.context.retriever, "lookup_object", None)
    if lookup is None:
        return result

    filters = _base_filters(ctx)
    if slot.source_hints:
        if len(slot.source_hints) == 1:
            filters["source"] = slot.source_hints[0]
        else:
            filters["sources"] = slot.source_hints

    object_chunks: list[Chunk] = []
    for label in labels[:_MAX_INFERRED_OBJECTS_PER_SLOT]:
        chunks = await lookup(label, filters=filters, top_k=1)
        object_chunks.extend(chunks)
    if not object_chunks:
        return result

    supplemental = RetrievalResult(
        chunks=[],
        parent_chunks=[],
        scores=[],
        ref_chunks=object_chunks,
        groundedness=result.groundedness,
        resolved_refs=list(dict.fromkeys([*result.resolved_refs, *labels])),
        unresolved_refs=[
            label for label in result.unresolved_refs if label not in set(labels)
        ],
    )
    ctx.context.bundle.add_retrieval(supplemental)
    return RetrievalResult(
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        scores=result.scores,
        guide_chunks=result.guide_chunks,
        guide_example_chunks=result.guide_example_chunks,
        ref_chunks=_merge_chunks(result.ref_chunks, object_chunks),
        groundedness=result.groundedness,
        resolved_refs=list(dict.fromkeys([*result.resolved_refs, *labels])),
        unresolved_refs=[
            label for label in result.unresolved_refs if label not in set(labels)
        ],
    )


def _infer_required_object_labels(slot: EvidenceSlot, result: RetrievalResult) -> list[str]:
    if slot.object_labels or not _is_value_slot(slot):
        return []
    existing = {
        chunk.metadata.object_label
        for chunk in [*result.chunks, *result.ref_chunks]
        if chunk.metadata.object_label
    }
    labels: list[str] = []
    seen: set[str] = set()
    for chunk in result.chunks:
        candidates = [*chunk.metadata.ref_labels, *extract_reference_labels(chunk.content)]
        for label in candidates:
            normalized = label.strip()
            if (
                not normalized
                or normalized in existing
                or normalized in seen
                or not _OBJECT_REF_RE.match(normalized)
            ):
                continue
            seen.add(normalized)
            labels.append(normalized)
            if len(labels) >= _MAX_INFERRED_OBJECTS_PER_SLOT:
                return labels
    return labels


def _is_value_slot(slot: EvidenceSlot) -> bool:
    text = " ".join([slot.description, slot.query, *slot.search_queries])
    return bool(_VALUE_QUERY_RE.search(text))


def _value_slot_lacks_values(slot: EvidenceSlot, result: RetrievalResult) -> bool:
    if not _is_value_slot(slot):
        return False
    evidence_text = "\n".join(
        chunk.content for chunk in [*result.chunks, *result.ref_chunks]
    )
    if not evidence_text.strip():
        return True
    if any(
        chunk.metadata.element_type in ("table", "formula")
        for chunk in [*result.chunks, *result.ref_chunks]
    ):
        return False
    text_without_reference_numbers = _REFERENCE_NUMBER_RE.sub(" ", evidence_text)
    return _NUMERIC_VALUE_RE.search(text_without_reference_numbers) is None


def _merge_chunks(existing: list[Chunk], incoming: list[Chunk]) -> list[Chunk]:
    seen = {chunk.chunk_id for chunk in existing}
    merged = list(existing)
    for chunk in incoming:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
    return merged


def _merge_strings(existing: list[str], incoming: list[str]) -> list[str]:
    seen = set(existing)
    merged = list(existing)
    for item in incoming:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _slot_status_rank(status: str) -> int:
    return {"missing": 0, "partial": 1, "satisfied": 2}.get(status, 0)


def _serialize_plan(plan: EvidencePlan) -> dict[str, object]:
    return json.loads(plan.model_dump_json())


def _format_agentic_summary(
    plan: EvidencePlan,
    slot_summaries: list[dict[str, object]],
    groundedness: str,
) -> str:
    lines = [
        f"完成 evidence planning 检索：strategy={plan.strategy}, groundedness={groundedness}。",
        "Evidence slots:",
    ]
    for slot in slot_summaries:
        lines.append(
            "- {id}: {status}, chunks={chunk_count}, {description}".format(**slot)
        )
    if groundedness == "grounded":
        lines.append("证据已充足，请直接基于以上证据回复。")
    return "\n".join(lines)


def _format_chunk_list(title: str, chunks: list[Chunk]) -> str:
    if not chunks:
        return f"{title}: 未找到匹配片段。"
    lines = [f"{title}: {len(chunks)} 个片段"]
    for index, chunk in enumerate(chunks[:5], start=1):
        meta = chunk.metadata
        section = " > ".join(meta.section_path) if meta.section_path else "unknown"
        label = f" | {meta.object_label}" if meta.object_label else ""
        preview = chunk.content[:100].replace("\n", " ").strip()
        lines.append(f"{index}. {chunk.chunk_id} | {meta.source} | {section}{label}")
        if preview:
            lines.append(f"   摘要: {preview}...")
    return "\n".join(lines)


def _format_understanding_summary(analysis, was_rewritten: bool) -> str:
    question_type = (
        analysis.question_type.value if analysis.question_type else "unknown"
    )
    summary = f"识别为{question_type}问题，扩展 {len(analysis.expanded_queries)} 条查询"
    if was_rewritten and analysis.rewritten_question:
        return f"改写为：{analysis.rewritten_question}；{summary}"
    return summary


def _serialize_target_hint(analysis) -> dict | None:
    target_hint = analysis.target_hint
    if target_hint is None:
        return None
    return {
        "document": target_hint.document,
        "clause": target_hint.clause,
        "object": target_hint.object,
    }
