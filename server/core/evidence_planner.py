"""Evidence planning for source-aware agentic retrieval."""

from __future__ import annotations

import json
import re
from typing import Literal

import httpx
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from shared.reference_graph import normalize_reference_label
from server.config import ServerConfig
from server.core.query_understanding import QueryAnalysis

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are an evidence planning component for Eurocode RAG.

Split the user's question into a small set of evidence slots. Each slot should
represent one independently searchable evidence need, not one answer paragraph.
Use the available source inventory when choosing source_hints, but do not invent
source IDs that are not listed.

Return only JSON:
{
  "strategy": "single|slot",
  "slots": [
    {
      "id": "short_snake_case",
      "description": "what evidence is needed",
      "query": "self-contained search query",
      "search_queries": ["1-3 concrete search queries"],
      "required": true,
      "source_hints": ["optional source IDs from inventory"],
      "object_labels": ["optional exact Table/Figure/Expression/Annex labels"],
      "retry_query": "optional broader retry query"
    }
  ],
  "reason": "short reason"
}

Rules:
- Prefer one slot for simple questions.
- Use 2-4 slots for compound questions that ask for multiple categories, tables,
  clauses, design situations, or parameter families.
- Keep search_queries specific enough to retrieve values, not only commentary.
- Put explicit table/figure/expression labels in object_labels.
"""

_COMPOUND_SPLIT_RE = re.compile(
    r"(?:和|及|与|以及|、|/|\band\b|\bor\b|\bplus\b)", re.IGNORECASE
)
_OBJECT_RE = re.compile(
    r"\b(?:Table|Figure|Expression|Annex)\s+[A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?",
    re.IGNORECASE,
)


class SourceInventoryItem(BaseModel):
    """A compact source entry exposed to the evidence planner."""

    source: str
    title: str = ""
    chunk_count: int = 0


class EvidenceSlot(BaseModel):
    """One independently searchable evidence need."""

    id: str
    description: str
    query: str
    search_queries: list[str] = Field(default_factory=list)
    required: bool = True
    source_hints: list[str] = Field(default_factory=list)
    object_labels: list[str] = Field(default_factory=list)
    retry_query: str | None = None

    def normalized_queries(self) -> list[str]:
        """Return deduplicated non-empty queries for retrieval."""
        queries = [self.query, *self.search_queries]
        seen: set[str] = set()
        normalized: list[str] = []
        for query in queries:
            stripped = query.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized


class EvidencePlan(BaseModel):
    """Bounded retrieval plan generated before slot search."""

    strategy: Literal["single", "slot"] = "single"
    slots: list[EvidenceSlot] = Field(default_factory=list)
    reason: str = ""

    @property
    def uses_slots(self) -> bool:
        return self.strategy == "slot" and len(self.slots) > 1


async def plan_evidence(
    question: str,
    analysis: QueryAnalysis,
    source_inventory: list[SourceInventoryItem],
    config: ServerConfig,
) -> EvidencePlan:
    """Plan evidence slots with LLM output and deterministic fallback."""
    if not config.agentic_search_enabled:
        return _single_slot_plan(question, analysis, reason="agentic_search_disabled")

    try:
        raw = await _call_planner_llm(question, analysis, source_inventory, config)
        parsed = _parse_plan(raw, question, analysis, config)
        if parsed.slots:
            return parsed
    except Exception as exc:
        logger.warning(
            "evidence_planner_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )

    return _heuristic_plan(question, analysis, source_inventory, config)


async def _call_planner_llm(
    question: str,
    analysis: QueryAnalysis,
    source_inventory: list[SourceInventoryItem],
    config: ServerConfig,
) -> str:
    payload = {
        "question": question,
        "rewritten_question": analysis.rewritten_question,
        "expanded_queries": analysis.expanded_queries,
        "filters": analysis.filters,
        "requested_objects": analysis.requested_objects,
        "question_type": (
            analysis.question_type.value if analysis.question_type else None
        ),
        "intent_label": analysis.intent_label,
        "target_hint": (
            analysis.target_hint.model_dump() if analysis.target_hint else None
        ),
        "source_inventory": [item.model_dump() for item in source_inventory[:50]],
    }
    timeout_seconds = max(1.0, config.agentic_search_planner_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_agentic_search_planner_api_key,
        base_url=config.resolved_agentic_search_planner_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    response = await client.chat.completions.create(
        model=config.resolved_agentic_search_planner_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=900,
    )
    return response.choices[0].message.content or ""


def _parse_plan(
    raw: str,
    question: str,
    analysis: QueryAnalysis,
    config: ServerConfig,
) -> EvidencePlan:
    cleaned = raw.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    data = json.loads(cleaned)
    plan = EvidencePlan.model_validate(data)
    return _normalize_plan(plan, question, analysis, config)


def _normalize_plan(
    plan: EvidencePlan,
    question: str,
    analysis: QueryAnalysis,
    config: ServerConfig,
) -> EvidencePlan:
    max_slots = max(1, min(config.agentic_search_max_slots, 6))
    slots: list[EvidenceSlot] = []
    for index, slot in enumerate(plan.slots[:max_slots], start=1):
        normalized = EvidenceSlot(
            id=_safe_slot_id(slot.id, index),
            description=slot.description.strip() or slot.query.strip() or question,
            query=slot.query.strip() or question,
            search_queries=[
                query.strip() for query in slot.search_queries if query.strip()
            ][:3],
            required=slot.required,
            source_hints=list(dict.fromkeys(s.strip() for s in slot.source_hints if s.strip())),
            object_labels=_normalize_object_labels(slot.object_labels),
            retry_query=slot.retry_query.strip() if slot.retry_query else None,
        )
        slots.append(normalized)
    if not slots:
        slots = _single_slot_plan(question, analysis, reason="empty_plan").slots
    strategy: Literal["single", "slot"] = "slot" if len(slots) > 1 else "single"
    return EvidencePlan(strategy=strategy, slots=slots, reason=plan.reason.strip())


def _heuristic_plan(
    question: str,
    analysis: QueryAnalysis,
    source_inventory: list[SourceInventoryItem],
    config: ServerConfig,
) -> EvidencePlan:
    del source_inventory
    normalized_question = _planning_question(question, analysis.rewritten_question)
    explicit_objects = _normalize_object_labels(
        [*analysis.requested_objects, *_OBJECT_RE.findall(normalized_question)]
    )
    target_object = (
        analysis.target_hint.object.strip()
        if analysis.target_hint and analysis.target_hint.object
        else ""
    )
    if not _looks_compound(normalized_question, explicit_objects, target_object):
        return _single_slot_plan(normalized_question, analysis, reason="heuristic_single")

    terms = _split_compound_terms(normalized_question)
    slots: list[EvidenceSlot] = []
    for index, term in enumerate(terms[: config.agentic_search_max_slots], start=1):
        query = _slot_query(normalized_question, term)
        slots.append(
            EvidenceSlot(
                id=f"slot_{index}",
                description=f"Evidence for {term}",
                query=query,
                search_queries=[query, *analysis.expanded_queries[:1]],
                object_labels=[
                    label
                    for label in explicit_objects
                    if term.lower() in label.lower() or len(terms) == 1
                ],
                retry_query=f"{term} {normalized_question}",
            )
        )
    if len(slots) <= 1:
        return _single_slot_plan(normalized_question, analysis, reason="heuristic_single")
    return EvidencePlan(strategy="slot", slots=slots, reason="heuristic_compound")


def _single_slot_plan(
    question: str,
    analysis: QueryAnalysis,
    *,
    reason: str,
) -> EvidencePlan:
    slot = EvidenceSlot(
        id="main",
        description="Primary evidence for the question",
        query=analysis.rewritten_question or question,
        search_queries=analysis.expanded_queries,
        object_labels=analysis.requested_objects,
    )
    return EvidencePlan(strategy="single", slots=[slot], reason=reason)


def _looks_compound(
    question: str,
    explicit_objects: list[str],
    target_object: str,
) -> bool:
    if len(explicit_objects) > 1:
        return True
    if target_object and _COMPOUND_SPLIT_RE.search(target_object):
        return True
    return bool(_COMPOUND_SPLIT_RE.search(question))


def _planning_question(question: str, rewritten_question: str | None) -> str:
    """Prefer rewritten text unless it loses compound cues from the user text."""
    original = question.strip()
    rewritten = (rewritten_question or "").strip()
    if not rewritten:
        return original
    original_compound = bool(_COMPOUND_SPLIT_RE.search(original))
    rewritten_compound = bool(_COMPOUND_SPLIT_RE.search(rewritten))
    if original_compound and not rewritten_compound:
        return original
    return rewritten


def _split_compound_terms(question: str) -> list[str]:
    parts = [part.strip(" ，,。；;") for part in _COMPOUND_SPLIT_RE.split(question)]
    useful = [part for part in parts if 2 <= len(part) <= 80]
    return useful[:4] or [question]


def _slot_query(question: str, term: str) -> str:
    if term in question:
        return f"{term}；{question}"
    return f"{term} {question}"


def _normalize_object_labels(labels: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for label in labels:
        value = normalize_reference_label(label) or label.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _safe_slot_id(value: str, index: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return normalized or f"slot_{index}"
