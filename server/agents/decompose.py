from __future__ import annotations

import json
import re
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

# Hard filter for invented standard codes in retrieval queries.
_EN_MENTION_RE = re.compile(
    r"\b(?:BS[\s-]*)?(?:DG\s+)?EN\s*[-_]?\s*(199\d)"
    r"(?:\s*[-_]\s*\d+(?:\s*[-_]\s*\d+)?)?"
    r"(?:\s*:\s*\d{4})?\b",
    re.IGNORECASE,
)
_EUROCODE_N_RE = re.compile(r"\bEurocode\s*([0-9])\b", re.IGNORECASE)
_EC_N_RE = re.compile(r"\bEC\s*([0-9])\b", re.IGNORECASE)
_YEAR_199X_RE = re.compile(r"\b(199\d)\b")
_WHITESPACE_RE = re.compile(r"\s{2,}")

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
- Prefer concept/object/parameter wording over guessing a Eurocode number.
- Good example for "什么是单向板？":
  [
    "one-way spanning slab definition",
    "one-way slab versus two-way slab criteria",
    "slab spanning classification design principles"
  ]
- Good example when the user explicitly mentions a standard
  ("EN 1990 设计使用年限如何确定"):
  [
    "EN 1990 design working life definition and categories",
    "EN 1990 design working life determination and classification table"
  ]

Standard-code rules (critical):
- Do NOT invent EN/BS/DG document numbers, Eurocode N / EC N labels, clauses,
  tables, formulas, or object labels that the user question, conversation
  history, or retrieval_scope did not mention.
- If the user did not name a standard, write concept-level English queries
  without any EN/Eurocode prefix (no guessed codes).
- If retrieval_scope is provided, you may only use standard/document labels that
  appear in that scope (or in the user/history). Never introduce out-of-scope
  codes (e.g. EN 1992 / Eurocode 2 when scope is only EN 1990 / EN 1997).
- Server-side hard filtering will strip disallowed codes; still avoid inventing
  them so queries stay clean.

Set needs_retrieval=false only for greetings, small talk, or questions that do
not require Eurocode evidence. For Eurocode, engineering, formula, table, clause,
or design questions, set needs_retrieval=true.

Do not infer source_type. Do not classify intent.
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
- missing_queries 不要编造用户/历史/retrieval_scope 未出现的规范号或 Eurocode N；
  优先用概念词（shear reinforcement omission criteria），不要默认加 EN/Eurocode 前缀。
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
    selected_sources: list[str] | None = None,
) -> DecomposedQuery:
    """Rewrite and split a user question before deterministic retrieval.

    ``selected_sources`` is an optional soft scope hint (KB/doc filter labels).
    Hard retrieval filtering is applied separately; this only steers query wording
    so the model does not invent out-of-scope standard codes.
    """
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

    allowed_years = _allowed_standard_years(
        sanitized,
        conversation_history,
        selected_sources,
    )
    try:
        raw = await _call_decompose_llm(
            sanitized,
            conversation_history=conversation_history,
            glossary=glossary,
            config=config,
            selected_sources=selected_sources,
        )
        payload = _parse_decompose_payload(raw)
        rewritten = _sanitize_query_text(
            _clean_text(payload.get("rewritten_question")) or sanitized,
            allowed_years,
        ) or sanitized
        sub_queries = _normalize_sub_queries(
            payload.get("sub_queries"),
            rewritten,
            allowed_years=allowed_years,
        )
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
    selected_sources: list[str] | None = None,
) -> str:
    timeout_seconds = max(1.0, config.decompose_llm_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_decompose_llm_api_key,
        base_url=config.resolved_decompose_llm_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    payload: dict[str, object] = {
        "question": question,
        "history": _compact_history(conversation_history),
        "glossary_terms": _matching_glossary_terms(question, glossary),
    }
    scope = _normalize_selected_sources(selected_sources)
    if scope:
        payload["retrieval_scope"] = scope
    response = await client.chat.completions.create(
        model=config.resolved_decompose_llm_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=500,
        response_format={"type": "json_object"},
        extra_body={"enable_thinking": False},
    )
    return response.choices[0].message.content or ""


def _normalize_selected_sources(selected_sources: list[str] | None) -> list[str]:
    """Deduplicate and cap soft scope labels for the decompose prompt."""
    if not selected_sources:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in selected_sources:
        label = str(raw or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        normalized.append(label)
        if len(normalized) >= 24:
            break
    return normalized


async def assess_evidence(
    *,
    question: str,
    rewritten_question: str,
    implicit_context: str = "",
    evidence_text: str,
    previous_queries: list[str],
    config: ServerConfig,
    selected_sources: list[str] | None = None,
    conversation_history: list[dict] | None = None,
) -> EvidenceAssessment:
    """Use the small planning model to decide if evidence covers the question."""
    allowed_years = _allowed_standard_years(
        question,
        conversation_history or [],
        selected_sources,
        extra_texts=[rewritten_question, implicit_context],
    )
    if not evidence_text.strip():
        fallback = _sanitize_query_text(
            rewritten_question or question,
            allowed_years,
        ) or (rewritten_question or question)
        return EvidenceAssessment(
            sufficient=False,
            missing_queries=[fallback],
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
            selected_sources=selected_sources,
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
                selected_sources=selected_sources,
            )
            payload = _parse_decompose_payload(raw)
        missing = _normalize_missing_queries(
            payload.get("missing_queries"),
            previous_queries,
            allowed_years=allowed_years,
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
    selected_sources: list[str] | None = None,
) -> str:
    timeout_seconds = max(1.0, config.decompose_llm_timeout_seconds)
    client = AsyncOpenAI(
        api_key=config.resolved_decompose_llm_api_key,
        base_url=config.resolved_decompose_llm_base_url,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(3.0, timeout_seconds)),
        max_retries=0,
    )
    payload: dict[str, object] = {
        "question": question,
        "rewritten_question": rewritten_question,
        "implicit_context": implicit_context,
        "previous_queries": previous_queries[-8:],
        "evidence": evidence_text[:12000],
    }
    scope = _normalize_selected_sources(selected_sources)
    if scope:
        payload["retrieval_scope"] = scope
    response = await client.chat.completions.create(
        model=config.resolved_decompose_llm_model,
        messages=[
            {"role": "system", "content": _ASSESSMENT_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=600,
        response_format={"type": "json_object"},
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
        api_key=config.resolved_planning_llm_api_key,
        base_url=config.resolved_planning_llm_base_url,
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
        model=config.resolved_planning_llm_model,
        messages=[
            {"role": "system", "content": _OUTLINE_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=1500,
        response_format={"type": "json_object"},
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


def _normalize_sub_queries(
    value: object,
    fallback: str,
    *,
    allowed_years: set[str] | None = None,
) -> list[str]:
    if isinstance(value, list):
        queries = [_clean_text(item) for item in value]
    else:
        queries = []
    years = allowed_years if allowed_years is not None else set()
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = _sanitize_query_text(query, years)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
        if len(normalized) >= 4:
            break
    if normalized:
        return normalized
    fallback_clean = _sanitize_query_text(fallback, years) or fallback
    return [fallback_clean]


def _normalize_missing_queries(
    value: object,
    previous_queries: list[str],
    *,
    allowed_years: set[str] | None = None,
) -> list[str]:
    previous = {query.strip().lower() for query in previous_queries if query.strip()}
    if isinstance(value, list):
        queries = [_clean_text(item) for item in value]
    else:
        queries = []
    years = allowed_years if allowed_years is not None else set()
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = _sanitize_query_text(query, years)
        key = cleaned.lower()
        if not cleaned or key in seen or key in previous:
            continue
        seen.add(key)
        normalized.append(cleaned)
        if len(normalized) >= 4:
            break
    return normalized


def _allowed_standard_years(
    question: str,
    conversation_history: list[dict],
    selected_sources: list[str] | None = None,
    *,
    extra_texts: list[str] | None = None,
) -> set[str]:
    """Years (199x) the model is allowed to mention in retrieval queries."""
    chunks: list[str] = [question or ""]
    for turn in conversation_history[-4:]:
        chunks.append(str(turn.get("question") or ""))
        chunks.append(str(turn.get("answer") or "")[:500])
    chunks.extend(_normalize_selected_sources(selected_sources))
    for text in extra_texts or []:
        chunks.append(str(text or ""))
    return _extract_standard_years("\n".join(chunks))


def _extract_standard_years(text: str) -> set[str]:
    years: set[str] = set(_YEAR_199X_RE.findall(text or ""))
    for match in _EUROCODE_N_RE.finditer(text or ""):
        years.add(f"199{match.group(1)}")
    for match in _EC_N_RE.finditer(text or ""):
        years.add(f"199{match.group(1)}")
    return years


def _sanitize_query_text(query: str, allowed_years: set[str]) -> str:
    """Strip EN/Eurocode mentions whose year is outside the allowed set."""
    text = _clean_text(query)
    if not text:
        return ""

    def _keep_en(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1) in allowed_years else " "

    def _keep_eurocode(match: re.Match[str]) -> str:
        year = f"199{match.group(1)}"
        return match.group(0) if year in allowed_years else " "

    text = _EN_MENTION_RE.sub(_keep_en, text)
    text = _EUROCODE_N_RE.sub(_keep_eurocode, text)
    text = _EC_N_RE.sub(_keep_eurocode, text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" \t\r\n-;:,|/\\")
    return text


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
