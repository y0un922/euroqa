from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.core.query_understanding import (
    extract_filters,
    extract_requested_objects,
    sanitize_input,
)

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You route and rewrite Eurocode QA questions for deterministic Eurocode retrieval.

Return only JSON:
{
  "rewritten_question": "self-contained question in English",
  "sub_queries": ["1-4 independent English retrieval queries"],
  "implicit_context": "short background or hidden requirement resolved from history",
  "needs_retrieval": true,
  "is_chitchat": false
}

Your only jobs:
- decide whether this question needs Eurocode evidence retrieval;
- resolve pronouns, ellipsis, and implicit context using recent conversation history;
- translate Chinese engineering questions into retrieval-friendly English;
- split compound questions into 1-4 independent search queries;
- mark greetings, small talk, or non-Eurocode questions as is_chitchat=true.

Sub-query rules:
- Each sub_query must be specific enough for keyword/vector retrieval.
- Cover theme, concrete requirements, background constraints, and implicit needs.
- Avoid overlapping sub_queries and avoid broad queries such as "Eurocode concrete".
- Good example for "混凝土材料强度与变形定义、关系及如何计算":
  [
    "EN 1992-1-1 concrete strength definitions fck fcm fctm",
    "EN 1992-1-1 concrete deformation definitions modulus creep shrinkage",
    "EN 1992-1-1 relationships and calculations for concrete strength values"
  ]

Set needs_retrieval=false only for greetings, small talk, or questions that do
not require Eurocode evidence. For Eurocode, engineering, formula, table, clause,
or design questions, set needs_retrieval=true.

Do not infer source_type. Do not classify intent. Do not invent clauses,
tables, formulas, standards, or object labels that the user/history did not
mention.
"""

_ASSESSMENT_PROMPT = """你负责判断已检索到的 Eurocode 证据是否足够回答用户问题。

只返回 JSON：
{
  "sufficient": true,
  "missing_queries": ["0-4 focused English retrieval queries"],
  "reason": "short reason"
}

评估维度：
- 主题定义：关键术语、对象、参数是否已有规范证据。
- 具体要求：定义、关系、计算步骤、公式、表格或限值是否齐全。
- 背景约束：标准、国家附录、构件/材料/设计场景等约束是否覆盖。
- 隐含需求：从对话历史或 implicit_context 得到的框架要求是否覆盖。

规则：
- 只有证据包含回答所需的关键定义、条文、公式、表格、限值或计算方法时，sufficient 才能为 true。
- 缺少被问题要求的 EN 条文、表格/公式、Designers' Guide 说明/示例或必要子主题时，sufficient=false。
- missing_queries 必须是英文，用于继续检索；必须指向具体缺口，不要重复 previous_queries。
- 不要回答用户，不要长篇引用，不要编造引用。
"""

_OUTLINE_PROMPT = """你是 Eurocode 中文回答的大纲规划器。

你将收到用户问题、英文改写、隐含上下文、对话历史和带 [Ref-N] 的预检索证据。
请只基于这些证据规划回答大纲，不要编造规范内容，不要使用未出现的引用。

只返回 JSON：
{
  "narrative_angle": "回答主线",
  "sections": [
    {"title": "小节标题", "bullets": ["要点"], "ref_ids": ["Ref-1"]}
  ],
  "calculation_steps": [
    {"step": "1. 计算步骤", "formula": "LaTeX formula if needed", "ref_ids": ["Ref-2"]}
  ],
  "self_check": ["最终回答前需要核对的事项"]
}

要求：
- 中文输出。
- sections 按最终回答顺序排列，优先覆盖定义、关系、计算、适用条件和证据缺口。
- 若问题包含“如何计算 / 计算方法 / 计算 / 求”等诉求，sections 必须包含“计算示例”或“算例”小节。
- calculation_steps 仅在问题不涉及计算/公式时才允许返回空数组。
- 当问题请求计算时，calculation_steps 必须规划一个可复现的具体数值算例：given 输入参数、每步代入数值、最终数值结果；不要只写空泛步骤。
- 若问题问“相互关系 / 关系”，sections 须包含覆盖本构关系（应力-应变 σ-ε）与设计参数随强度折减的关系小节。
- 关系小节应提示矩形应力块参数：fck≤50 时 λ=0.8、η=1.0；fck>50 时 λ=0.8-(fck-50)/400、η=1.0-(fck-50)/200，证据不足则标记缺口。
- ref_ids 只能使用证据中已经出现的 Ref-N，不要带方括号。
- 证据不足时仍给出可回答部分的大纲，并在 self_check 中标记缺口。
"""


@dataclass(frozen=True)
class DecomposedQuery:
    rewritten_question: str
    sub_queries: list[str]
    implicit_context: str = ""
    needs_retrieval: bool = True
    is_chitchat: bool = False
    requested_objects: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceAssessment:
    sufficient: bool
    missing_queries: list[str]
    reason: str = ""


async def decompose_query(
    question: str,
    conversation_history: list[dict],
    glossary: dict[str, str],
    config: ServerConfig,
) -> DecomposedQuery:
    """Rewrite and split a user question before deterministic retrieval."""
    sanitized = sanitize_input(question).strip()
    filters = extract_filters(sanitized)
    requested_objects = extract_requested_objects(sanitized, None)
    if not sanitized:
        return DecomposedQuery(
            rewritten_question=question,
            sub_queries=[question],
            implicit_context="",
            needs_retrieval=False,
            is_chitchat=True,
            requested_objects=requested_objects,
            filters=filters,
        )

    try:
        raw = await _call_decompose_llm(
            sanitized,
            conversation_history=conversation_history,
            glossary=glossary,
            config=config,
        )
        payload = _parse_decompose_payload(raw)
        rewritten = _clean_text(payload.get("rewritten_question")) or sanitized
        sub_queries = _normalize_sub_queries(payload.get("sub_queries"), rewritten)
        return DecomposedQuery(
            rewritten_question=rewritten,
            sub_queries=sub_queries,
            implicit_context=_clean_text(payload.get("implicit_context")),
            needs_retrieval=bool(payload.get("needs_retrieval", True)),
            is_chitchat=bool(payload.get("is_chitchat")),
            requested_objects=requested_objects,
            filters=filters,
        )
    except Exception as exc:
        logger.warning(
            "decompose_query_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return DecomposedQuery(
            rewritten_question=sanitized,
            sub_queries=[sanitized],
            implicit_context="",
            needs_retrieval=True,
            requested_objects=requested_objects,
            filters=filters,
        )


async def _call_decompose_llm(
    question: str,
    *,
    conversation_history: list[dict],
    glossary: dict[str, str],
    config: ServerConfig,
) -> str:
    timeout_seconds = max(1.0, config.decompose_llm_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_decompose_llm_api_key,
        base_url=config.resolved_decompose_llm_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    payload = {
        "question": question,
        "history": _compact_history(conversation_history),
        "glossary_terms": _matching_glossary_terms(question, glossary),
    }
    response = await client.chat.completions.create(
        model=config.resolved_decompose_llm_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=500,
        extra_body={"enable_thinking": False},
    )
    return response.choices[0].message.content or ""


async def assess_evidence(
    *,
    question: str,
    rewritten_question: str,
    implicit_context: str = "",
    evidence_text: str,
    previous_queries: list[str],
    config: ServerConfig,
) -> EvidenceAssessment:
    """Use the small planning model to decide if evidence covers the question."""
    if not evidence_text.strip():
        return EvidenceAssessment(
            sufficient=False,
            missing_queries=[rewritten_question or question],
            reason="no evidence",
        )
    try:
        raw = await _call_assessment_llm(
            question=question,
            rewritten_question=rewritten_question,
            implicit_context=implicit_context,
            evidence_text=evidence_text,
            previous_queries=previous_queries,
            config=config,
        )
        try:
            payload = _parse_decompose_payload(raw)
        except Exception:
            raw = await _call_assessment_llm(
                question=question,
                rewritten_question=rewritten_question,
                implicit_context=implicit_context,
                evidence_text=evidence_text,
                previous_queries=previous_queries,
                config=config,
            )
            payload = _parse_decompose_payload(raw)
        missing = _normalize_missing_queries(
            payload.get("missing_queries"),
            previous_queries,
        )
        return EvidenceAssessment(
            sufficient=bool(payload.get("sufficient")),
            missing_queries=missing,
            reason=_clean_text(payload.get("reason")),
        )
    except Exception as exc:
        logger.warning(
            "evidence_assessment_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return EvidenceAssessment(
            sufficient=True,
            missing_queries=[],
            reason="assessment_failed_fallback",
        )


async def _call_assessment_llm(
    *,
    question: str,
    rewritten_question: str,
    implicit_context: str,
    evidence_text: str,
    previous_queries: list[str],
    config: ServerConfig,
) -> str:
    timeout_seconds = max(1.0, config.decompose_llm_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_decompose_llm_api_key,
        base_url=config.resolved_decompose_llm_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    payload = {
        "question": question,
        "rewritten_question": rewritten_question,
        "implicit_context": implicit_context,
        "previous_queries": previous_queries[-8:],
        "evidence": evidence_text[:12000],
    }
    response = await client.chat.completions.create(
        model=config.resolved_decompose_llm_model,
        messages=[
            {"role": "system", "content": _ASSESSMENT_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=600,
        extra_body={"enable_thinking": False},
    )
    return response.choices[0].message.content or ""


async def outline_answer(
    *,
    question: str,
    rewritten_question: str,
    implicit_context: str,
    conversation_history: list[dict],
    evidence_text: str,
    config: ServerConfig,
) -> dict[str, object]:
    """Plan a structured answer outline from prefetched evidence."""
    if not evidence_text.strip():
        return {}
    try:
        raw = await _call_outline_llm(
            question=question,
            rewritten_question=rewritten_question,
            implicit_context=implicit_context,
            conversation_history=conversation_history,
            evidence_text=evidence_text,
            config=config,
        )
        return _normalize_outline_payload(_parse_decompose_payload(raw))
    except Exception as exc:
        logger.warning(
            "outline_answer_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return {}


async def _call_outline_llm(
    *,
    question: str,
    rewritten_question: str,
    implicit_context: str,
    conversation_history: list[dict],
    evidence_text: str,
    config: ServerConfig,
) -> str:
    timeout_seconds = max(1.0, config.outline_llm_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_agent_llm_api_key,
        base_url=config.resolved_agent_llm_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    payload = {
        "question": question,
        "rewritten_question": rewritten_question,
        "implicit_context": implicit_context,
        "history": _compact_history(conversation_history),
        "evidence": evidence_text[:12000],
    }
    response = await client.chat.completions.create(
        model=config.resolved_agent_llm_model,
        messages=[
            {"role": "system", "content": _OUTLINE_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=1500,
        extra_body={"enable_thinking": False},
    )
    return response.choices[0].message.content or ""


def _parse_decompose_payload(raw: str) -> dict[str, object]:
    cleaned = raw.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("decompose response must be a JSON object")
    return data


def _normalize_sub_queries(value: object, fallback: str) -> list[str]:
    if isinstance(value, list):
        queries = [_clean_text(item) for item in value]
    else:
        queries = []
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if not query or query in seen:
            continue
        seen.add(query)
        normalized.append(query)
        if len(normalized) >= 4:
            break
    return normalized or [fallback]


def _normalize_missing_queries(value: object, previous_queries: list[str]) -> list[str]:
    previous = {query.strip().lower() for query in previous_queries if query.strip()}
    if isinstance(value, list):
        queries = [_clean_text(item) for item in value]
    else:
        queries = []
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.lower()
        if not query or key in seen or key in previous:
            continue
        seen.add(key)
        normalized.append(query)
        if len(normalized) >= 4:
            break
    return normalized


def _normalize_outline_payload(payload: dict[str, object]) -> dict[str, object]:
    sections = payload.get("sections")
    calculation_steps = payload.get("calculation_steps")
    self_check = payload.get("self_check")
    return {
        "narrative_angle": _clean_text(payload.get("narrative_angle")),
        "sections": sections if isinstance(sections, list) else [],
        "calculation_steps": calculation_steps if isinstance(calculation_steps, list) else [],
        "self_check": self_check if isinstance(self_check, list) else [],
    }


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _compact_history(history: list[dict]) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for turn in history[-4:]:
        question = str(turn.get("question") or "").strip()
        answer = str(turn.get("answer") or "").strip()
        if question or answer:
            compact.append(
                {
                    "question": question[:500],
                    "answer": answer[:500],
                }
            )
    return compact


def _matching_glossary_terms(question: str, glossary: dict[str, str]) -> dict[str, str]:
    return {
        zh: en
        for zh, en in glossary.items()
        if zh and (zh in question or en.lower() in question.lower())
    }
