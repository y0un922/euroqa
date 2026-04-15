"""Query understanding: multi-angle query expansion + filter extraction.

This module provides the query analysis pipeline for the Eurocode QA system:
1. extract_filters   - 从问题中提取结构化过滤条件（来源文档、元素类型等）
2. expand_queries    - 借助 LLM 将中文问题扩展为三路英文检索查询（语义/概念/术语）
3. analyze_query     - 组合以上两步，返回完整的 QueryAnalysis 结果
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI

from shared.reference_graph import classify_reference_label, normalize_reference_label
from server.config import ServerConfig
from server.models.schemas import (
    AnswerMode,
    EngineeringContext,
    QuestionType,
    RoutingDecision,
    RoutingTargetHint,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 输入安全过滤
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = [
    re.compile(r"忽略.{0,10}(之前|以上|前面).{0,10}(指令|规则|提示)", re.IGNORECASE),
    re.compile(r"ignore.{0,20}(previous|above|prior).{0,20}(instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"disregard.{0,20}(previous|above|prior)", re.IGNORECASE),
    re.compile(r"你(现在)?是.{0,10}(一个|一名)", re.IGNORECASE),
    re.compile(r"pretend.{0,10}(you are|to be)", re.IGNORECASE),
]


def sanitize_input(question: str) -> str:
    """Filter common prompt injection patterns. Returns cleaned question."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(question):
            # 移除注入尝试，保留其余内容
            question = pattern.sub("", question).strip()
    return question


# ---------------------------------------------------------------------------
# 过滤条件提取用正则
# ---------------------------------------------------------------------------
_DG_SOURCE_RE = re.compile(r"DG\s*EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_SOURCE_RE = re.compile(r"EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_TABLE_RE = re.compile(r"表格?|table", re.IGNORECASE)
_FORMULA_RE = re.compile(r"公式|formula|eq", re.IGNORECASE)
_REQUESTED_TABLE_RE = re.compile(
    r"(?:\btable\b|表格?|表)\s*([A-Z]?\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
_REQUESTED_FIGURE_RE = re.compile(
    r"(?:\bfigure\b|图)\s*([A-Z]?\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
_REQUESTED_EXPR_RE = re.compile(
    r"(?:\bexpression\b|公式|式)\s*[\(\[]?\s*(\d+(?:\.\d+)*)\s*[\)\]]?",
    re.IGNORECASE,
)
_REQUESTED_ANNEX_RE = re.compile(r"(?:\bannex\b|附录)\s*([A-Z]\d*)", re.IGNORECASE)
_REQUESTED_CLAUSE_RE = re.compile(
    r"(?<![A-Za-z0-9/])([A-Z]?\d+(?:\.\d+)+[A-Z]?)(?![A-Za-z0-9/])",
    re.IGNORECASE,
)


@dataclass
class ExpansionResult:
    """查询扩展结果，包含检索查询、问题类型和工程上下文。"""

    queries: list[str]
    question_type: QuestionType | None = None
    engineering_context: EngineeringContext | None = None
    routing: RoutingDecision | None = None


@dataclass
class QueryAnalysis:
    """完整的查询分析结果."""

    original_question: str
    expanded_queries: list[str]
    filters: dict[str, str]
    matched_terms: dict[str, str] = field(default_factory=dict)
    requested_objects: list[str] = field(default_factory=list)
    question_type: QuestionType | None = None
    engineering_context: EngineeringContext | None = None
    answer_mode: AnswerMode | None = None
    intent_label: str | None = None
    intent_confidence: float | None = None
    target_hint: RoutingTargetHint | None = None
    reason_short: str | None = None
    preferred_element_type: str | None = None

    @property
    def rewritten_query(self) -> str:
        """向后兼容：返回第一条扩展查询（语义查询）。"""
        return self.expanded_queries[0] if self.expanded_queries else self.original_question


# ===== 公开 API =====


def extract_filters(question: str) -> dict[str, str]:
    """从问题文本中提取结构化过滤条件.

    当前支持：
    - source: 匹配 "DG ENxxxx" 指南或 "EN xxxx" 系列标准编号

    注意：element_type 不再作为硬过滤条件，改由 extract_preferred_element_type
    返回 boost 偏好，避免排除包含表格/公式交叉引用的文本 chunk。
    """
    filters: dict[str, str] = {}

    dg_source_match = _DG_SOURCE_RE.search(question)
    if dg_source_match:
        filters["source"] = f"DG EN{dg_source_match.group(1)}"
    else:
        source_match = _SOURCE_RE.search(question)
        if source_match:
            filters["source"] = f"EN {source_match.group(1)}"

    return filters


def extract_preferred_element_type(question: str) -> str | None:
    """从问题文本中提取偏好的 element_type（用于 BM25 boost，非硬过滤）。"""
    if _TABLE_RE.search(question):
        return "table"
    if _FORMULA_RE.search(question):
        return "formula"
    return None


def extract_requested_objects(
    question: str,
    target_hint: RoutingTargetHint | dict[str, str] | None = None,
) -> list[str]:
    """从问题和 target hint 中抽取显式规范对象目标。"""
    requested: list[str] = []
    seen: set[str] = set()
    candidates: list[tuple[int, str]] = []

    def add(value: str) -> None:
        normalized = normalize_reference_label(value)
        if not normalized:
            return
        if (
            classify_reference_label(normalized) != "clause"
            and classify_reference_label(normalized) is None
        ):
            return
        if normalized not in seen:
            seen.add(normalized)
            requested.append(normalized)

    occupied_spans: list[tuple[int, int]] = []

    def add_pattern(pattern: re.Pattern[str], builder) -> None:
        for match in pattern.finditer(question):
            occupied_spans.append(match.span())
            candidates.append((match.start(), builder(match.group(1))))

    add_pattern(_REQUESTED_TABLE_RE, lambda key: f"Table {key}")
    add_pattern(_REQUESTED_FIGURE_RE, lambda key: f"Figure {key}")
    add_pattern(_REQUESTED_EXPR_RE, lambda key: f"Expression ({key})")
    add_pattern(_REQUESTED_ANNEX_RE, lambda key: f"Annex {key}")

    def overlaps(span: tuple[int, int]) -> bool:
        return any(not (span[1] <= left or span[0] >= right) for left, right in occupied_spans)

    for match in _REQUESTED_CLAUSE_RE.finditer(question):
        if overlaps(match.span()):
            continue
        candidates.append((match.start(), match.group(1)))

    for _, value in sorted(candidates, key=lambda item: item[0]):
        add(value)

    raw_target_items: list[str] = []
    if isinstance(target_hint, dict):
        raw_target_items.extend(
            [
                value for key, value in target_hint.items()
                if key in {"clause", "object"} and isinstance(value, str)
            ]
        )
    elif target_hint is not None:
        for key in ("clause", "object"):
            value = getattr(target_hint, key, None)
            if isinstance(value, str):
                raw_target_items.append(value)

    for item in raw_target_items:
        add(item)

    return requested


async def expand_queries(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> ExpansionResult:
    """将中文问题扩展为三路英文检索查询，并提取问题类型与工程上下文。

    一次 LLM 调用同时完成：
    1. semantic  — 自然语言语义查询（适合向量检索）
    2. concepts  — 相关概念、同义词、上下位词（拓宽召回面）
    3. terms     — 变量名、缩写、公式符号（命中公式和符号定义片段）
    4. question_type — 问题分型（rule/parameter/calculation/mechanism）
    5. context   — 工程上下文字段，缺失置为 null
    6. routing   — exact/open 路由提示与目标线索

    失败时降级为仅返回原始问题。
    """
    matched_terms: dict[str, str] = {}
    for zh, en in glossary.items():
        if zh in question:
            matched_terms[zh] = en

    term_hint = ""
    if matched_terms:
        pairs = ", ".join(f"{zh}={en}" for zh, en in matched_terms.items())
        term_hint = f"已知术语对照：{pairs}\n"

    prompt = (
        "你是 Eurocode 规范检索专家。将以下中文工程问题扩展为三条英文检索查询，"
        "同时判断问题类型并提取工程上下文。\n\n"
        "三条查询的视角：\n"
        "1. semantic: 一句自然语言英文短句，忠实表达问题核心含义\n"
        "2. concepts: 相关概念、同义词、上下位术语（空格分隔）\n"
        "3. terms: 规范中会出现的变量名、缩写、公式符号（空格分隔）\n\n"
        "问题类型（question_type），从以下四类中选一个：\n"
        '- "rule": 规则/假设类 — 问"采用什么模型/假定"\n'
        '- "parameter": 参数/限值类 — 问"约束条件/限值是什么"\n'
        '- "calculation": 计算类 — 问"从已知量到设计值怎么走"\n'
        '- "mechanism": 机理/影响因素类 — 问"哪些变量会改变结果"\n\n'
        "路由字段：\n"
        '- "answer_mode": "exact" 或 "open"\n'
        '- "intent_label": definition|assumption|applicability|formula|limit|clause_lookup|'
        'explanation|mechanism|calculation\n'
        '- "confidence": 0 到 1 之间的小数\n'
        '- "target_hint": {"document": str|null, "clause": str|null, "object": str|null}\n'
        '- "reason_short": 一句简短英文原因\n\n'
        "工程上下文（context），从问题中提取（缺失填 null）：\n"
        "country, structure_type (beam/slab/column/wall/foundation), "
        "limit_state (ULS/SLS), load_combination (bool), "
        "concrete_class, rebar_grade, prestressed (bool), "
        "discontinuity_region (bool)\n\n"
        "要求：\n"
        "- 不要猜测问题中未提及的条款号或表格号\n"
        "- semantic/concepts/terms 只输出英文\n"
        "- question_type 必须基于问题意图判断\n"
        "- answer_mode 仅在明确属于直接条文/定义/假设/公式/限值/条款定位时填 exact，否则填 open\n"
        "- confidence 反映你对 routing 的把握；不确定时给低分，不要编造 target_hint\n"
        "- context 中未明确出现的信息必须保留为 null，不要臆测\n"
        "- 严格按 JSON 格式输出：\n"
        '{"semantic":"...","concepts":"...","terms":"...",'
        '"question_type":"rule|parameter|calculation|mechanism",'
        '"answer_mode":"exact|open","intent_label":"...",'
        '"confidence":0.0,"target_hint":{"document":null,"clause":null,"object":null},'
        '"reason_short":"...",'
        '"context":{"country":null,"structure_type":null,'
        '"limit_state":null,"load_combination":null,'
        '"concrete_class":null,"rebar_grade":null,'
        '"prestressed":null,"discontinuity_region":null}}\n\n'
        f"{term_hint}"
        f"问题：{question}"
    )

    try:
        raw = await _call_llm(prompt, config)
        result = _parse_expansion_result(raw)
        if result and result.queries:
            return result
    except Exception:
        logger.warning("query_expansion_failed_falling_back_to_original")

    return ExpansionResult(queries=[question])


def _parse_expansion_result(raw: str) -> ExpansionResult | None:
    """从 LLM 响应中解析查询扩展、问题类型和工程上下文。"""
    cleaned = raw.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # 解析三路查询
    queries: list[str] = []
    for key in ("semantic", "concepts", "terms"):
        value = data.get(key, "")
        if isinstance(value, str) and value.strip():
            queries.append(value.strip())
    if not queries:
        return None

    # 解析问题类型
    parsed_type: QuestionType | None = None
    raw_type = data.get("question_type")
    if isinstance(raw_type, str):
        try:
            parsed_type = QuestionType(raw_type.strip().lower())
        except ValueError:
            parsed_type = None

    # 解析工程上下文
    eng_context: EngineeringContext | None = None
    raw_context = data.get("context")
    if isinstance(raw_context, dict):
        normalized = {
            k: raw_context.get(k)
            for k in EngineeringContext.model_fields
        }
        try:
            eng_context = EngineeringContext.model_validate(normalized)
        except Exception:
            logger.warning("engineering_context_parse_failed", exc_info=True)

    routing = _parse_routing_decision(data)

    return ExpansionResult(
        queries=queries,
        question_type=parsed_type,
        engineering_context=eng_context,
        routing=routing,
    )


def _parse_routing_decision(data: dict[str, object]) -> RoutingDecision | None:
    """解析 routing 元数据；缺失、低置信度或格式异常时安全降级。"""
    raw_mode = data.get("answer_mode")
    raw_intent = data.get("intent_label")
    raw_confidence = data.get("confidence")
    raw_target = data.get("target_hint")
    raw_reason = data.get("reason_short")

    if not all(
        (
            isinstance(raw_mode, str),
            isinstance(raw_intent, str),
            isinstance(raw_target, dict),
            isinstance(raw_reason, str),
        )
    ):
        return None

    try:
        answer_mode = AnswerMode(raw_mode.strip().lower())
    except ValueError:
        return None

    # `exact_not_grounded` 由后续 retrieval / groundedness gate 决定，
    # query-understanding 阶段显式拒绝该状态，避免提前承诺证据充分性。
    if answer_mode == AnswerMode.EXACT_NOT_GROUNDED:
        return None

    intent_label = raw_intent.strip()
    reason_short = raw_reason.strip()
    if not intent_label or not reason_short:
        return None

    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, int | float):
        return None
    confidence = float(raw_confidence)
    if not 0.0 <= confidence <= 1.0 or confidence < 0.5:
        return None

    normalized_target: dict[str, str | None] = {}
    for key in RoutingTargetHint.model_fields:
        value = raw_target.get(key)
        if value is None:
            normalized_target[key] = None
            continue
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        normalized_target[key] = stripped or None

    try:
        target_hint = RoutingTargetHint.model_validate(normalized_target)
    except Exception:
        logger.warning("routing_target_hint_parse_failed", exc_info=True)
        return None

    return RoutingDecision(
        answer_mode=answer_mode,
        intent_label=intent_label,
        intent_confidence=confidence,
        target_hint=target_hint,
        reason_short=reason_short,
    )


async def analyze_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> QueryAnalysis:
    """组合过滤提取与多角度查询扩展，返回完整分析结果."""
    question = sanitize_input(question)
    filters = extract_filters(question)
    preferred_element_type = extract_preferred_element_type(question)
    expansion = await expand_queries(question, glossary, config)
    matched_terms = {zh: en for zh, en in glossary.items() if zh in question}
    requested_objects = extract_requested_objects(
        question,
        expansion.routing.target_hint if expansion.routing else None,
    )

    return QueryAnalysis(
        original_question=question,
        expanded_queries=expansion.queries,
        filters=filters,
        matched_terms=matched_terms,
        requested_objects=requested_objects,
        question_type=expansion.question_type,
        engineering_context=expansion.engineering_context,
        answer_mode=expansion.routing.answer_mode if expansion.routing else None,
        intent_label=expansion.routing.intent_label if expansion.routing else None,
        intent_confidence=expansion.routing.intent_confidence if expansion.routing else None,
        target_hint=expansion.routing.target_hint if expansion.routing else None,
        reason_short=expansion.routing.reason_short if expansion.routing else None,
        preferred_element_type=preferred_element_type,
    )


# ===== 内部辅助 =====


async def _call_llm(prompt: str, config: ServerConfig | None = None) -> str:
    """调用 LLM 获取文本回复（内部使用，可被测试 mock）."""
    cfg = config or ServerConfig()
    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    resp = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
    )
    return resp.choices[0].message.content.strip()
