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

import httpx
import structlog
from openai import AsyncOpenAI

from shared.llm_clients import get_async_openai_client
from shared.reference_graph import classify_reference_label, normalize_reference_label
from server.config import ServerConfig
from server.models.schemas import (
    EngineeringContext,
    GuideHint,
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
    re.compile(
        r"ignore.{0,20}(previous|above|prior).{0,20}(instructions?|rules?|prompts?)",
        re.IGNORECASE,
    ),
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
    r"(?:\btable\b|表格?|表)\s*([A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?)",
    re.IGNORECASE,
)
_REQUESTED_FIGURE_RE = re.compile(
    r"(?:\bfigure\b|图)\s*([A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?)",
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
_QUERY_EXPANSION_SYSTEM_PROMPT = (
    "你是 Eurocode 规范检索专家。将以下中文工程问题扩展为三条英文检索查询，"
    "同时判断问题类型、提取工程上下文，并判断是否需要去 Designers' Guide 中找算例。\n\n"
    "如果当前问题包含代词（它、这个、那个、该参数、上面的表格等）或省略了关键语境"
    "（如文档号、条款号、构件类型），你必须先根据对话历史还原为完整的自包含问题，"
    '然后再进行查询扩展。还原后的完整问题输出在 "rewritten_question" 字段中。'
    '如果当前问题已经是完整的自包含问题，"rewritten_question" 填原问题即可。\n\n'
    "三条查询的视角：\n"
    "1. semantic: 一句自然语言英文短句，忠实表达问题核心含义\n"
    "2. concepts: 相关概念、同义词、上下位术语（空格分隔）\n"
    "3. terms: 规范中会出现的变量名、缩写、公式符号（空格分隔）\n\n"
    "问题类型（question_type），从以下四类中选一个：\n"
    '- "rule": 规则/假设类 — 问"采用什么模型/假定"\n'
    '- "parameter": 参数/限值类 — 问"约束条件/限值是什么"\n'
    '- "calculation": 计算类 — 问"从已知量到设计值怎么走"\n'
    '- "mechanism": 机理/影响因素类 — 问"哪些变量会改变结果"\n\n'
    "目标线索字段：\n"
    '- "intent_label": definition|assumption|applicability|formula|limit|clause_lookup|'
    "explanation|mechanism|calculation\n"
    '- "target_hint": {"document": str|null, "clause": str|null, "object": str|null}\n'
    '- "reason_short": 一句简短英文原因\n\n'
    "工程上下文（context），从问题中提取（缺失填 null）：\n"
    "country, structure_type (beam/slab/column/wall/foundation), "
    "limit_state (ULS/SLS), load_combination (bool), "
    "concrete_class, rebar_grade, prestressed (bool), "
    "discontinuity_region (bool)\n\n"
    "指南算例提示（guide_hint）：\n"
    '- "need_example": true/false，只有当用户明显在问计算步骤、如何取值，或提供一个算例能显著帮助理解时才设为 true\n'
    '- "example_query": 一句简短英文检索短语，用于在 Designers\' Guide 中检索相关算例；没有明确算例需求时填 null\n'
    '- "example_kind": worked_example|procedure|commentary|null\n\n'
    "要求：\n"
    "- 不要猜测问题中未提及的条款号或表格号\n"
    "- semantic/concepts/terms 只输出英文\n"
    "- question_type 必须基于问题意图判断\n"
    "- 是否需要指南算例主要由 question_type 和问题意图共同决定，不要机械地对所有问题都要求算例\n"
    "- context 中未明确出现的信息必须保留为 null，不要臆测\n"
    "- target_hint 只能填问题中明确出现或可由目标对象稳定推出的信息，不确定时填 null\n"
    "- 严格按 JSON 格式输出：\n"
    '{"rewritten_question":"...","semantic":"...","concepts":"...","terms":"...",'
    '"question_type":"rule|parameter|calculation|mechanism",'
    '"guide_hint":{"need_example":false,"example_query":null,"example_kind":null},'
    '"intent_label":"...",'
    '"target_hint":{"document":null,"clause":null,"object":null},'
    '"reason_short":"...",'
    '"context":{"country":null,"structure_type":null,'
    '"limit_state":null,"load_combination":null,'
    '"concrete_class":null,"rebar_grade":null,'
    '"prestressed":null,"discontinuity_region":null}}'
)


@dataclass
class ExpansionResult:
    """查询扩展结果，包含检索查询和问题类型。"""

    queries: list[str]
    question_type: QuestionType | None = None
    intent_label: str | None = None
    target_hint: RoutingTargetHint | None = None
    engineering_context: EngineeringContext | None = None
    guide_hint: GuideHint | None = None
    rewritten_question: str | None = None

    @property
    def routing(self) -> RoutingDecision | None:
        """Backward-compatible routing view for older callers/tests."""
        if not self.intent_label or self.target_hint is None:
            return None
        return RoutingDecision(
            intent_label=self.intent_label,
            target_hint=self.target_hint,
            reason_short=self.intent_label,
        )


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
    guide_hint: GuideHint | None = None
    intent_label: str | None = None
    target_hint: RoutingTargetHint | None = None
    reason_short: str | None = None
    preferred_element_type: str | None = None
    rewritten_question: str | None = None

    @property
    def rewritten_query(self) -> str:
        """向后兼容：返回第一条扩展查询（语义查询）。"""
        return (
            self.expanded_queries[0]
            if self.expanded_queries
            else self.original_question
        )


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
        return any(
            not (span[1] <= left or span[0] >= right) for left, right in occupied_spans
        )

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
                value
                for key, value in target_hint.items()
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


def _should_enable_prompt_cache(
    cfg: ServerConfig,
    *,
    base_url: str,
    model: str,
) -> bool:
    """Return whether this concrete LLM endpoint should receive cache markers."""
    if not cfg.llm_prompt_cache_enabled:
        return False
    return "qwen" in model.lower() or "dashscope.aliyuncs.com" in base_url.lower()


def _build_cacheable_system_message(system_prompt: str) -> dict[str, object]:
    return {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


async def expand_queries(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
    history: list[dict[str, str]] | None = None,
    source_question: str | None = None,
) -> ExpansionResult:
    """将中文问题扩展为三路英文检索查询，并提取问题类型与工程上下文。

    一次 LLM 调用只完成：
    1. semantic  — 自然语言语义查询（适合向量检索）
    2. concepts  — 相关概念、同义词、上下位词（拓宽召回面）
    3. terms     — 变量名、缩写、公式符号（命中公式和符号定义片段）
    4. question_type — 问题分型（rule/parameter/calculation/mechanism）

    失败时降级为仅返回原始问题。
    """
    _ = history
    matched_terms: dict[str, str] = {}
    for zh, en in glossary.items():
        if zh in question:
            matched_terms[zh] = en

    term_hint = ""
    if matched_terms:
        pairs = ", ".join(f"{zh}={en}" for zh, en in matched_terms.items())
        term_hint = f"已知术语对照：{pairs}\n"

    user_prompt = f"{term_hint}问题：{question}"

    try:
        raw = await _call_llm(
            user_prompt,
            config,
            system_prompt=_QUERY_EXPANSION_SYSTEM_PROMPT,
        )
        result = _parse_expansion_result(raw)
        if result and result.queries:
            result.question_type = _refine_question_type(question, result.question_type)
            result.target_hint = _validate_target_hint(
                result.target_hint,
                " ".join(part for part in [source_question, question] if part),
            )
            return result
        logger.warning(
            "query_expansion_failed_falling_back_to_original",
            reason="empty_or_invalid_expansion_result",
        )
    except Exception as exc:
        logger.warning(
            "query_expansion_failed_falling_back_to_original",
            reason="llm_call_or_parse_exception",
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )

    return ExpansionResult(queries=[question])


def _parse_expansion_result(raw: str) -> ExpansionResult | None:
    """从 LLM 响应中解析查询扩展和低信任目标线索。"""
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

    intent_label = _clean_str(data.get("intent_label"))
    target_hint = _parse_target_hint(data.get("target_hint"))

    return ExpansionResult(
        queries=queries,
        question_type=parsed_type,
        intent_label=intent_label,
        target_hint=target_hint,
    )


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _parse_target_hint(payload: object) -> RoutingTargetHint | None:
    """Parse LLM target hints as untrusted candidates."""
    if not isinstance(payload, dict):
        return None

    normalized: dict[str, str | None] = {}
    for key in RoutingTargetHint.model_fields:
        normalized[key] = _clean_str(payload.get(key))
    try:
        target_hint = RoutingTargetHint.model_validate(normalized)
    except Exception:
        logger.warning("routing_target_hint_parse_failed", exc_info=True)
        return None
    if not any((target_hint.document, target_hint.clause, target_hint.object)):
        return None
    return target_hint


def _validate_target_hint(
    target_hint: RoutingTargetHint | None,
    evidence_text: str,
) -> RoutingTargetHint | None:
    """Drop target hints that cannot be traced to the input text."""
    if target_hint is None:
        return None

    document = target_hint.document if _contains_hint(evidence_text, target_hint.document) else None
    clause = target_hint.clause if _contains_hint(evidence_text, target_hint.clause) else None
    obj = target_hint.object if _contains_hint(evidence_text, target_hint.object) else None
    if not any((document, clause, obj)):
        return None
    return RoutingTargetHint(
        document=document,
        clause=clause,
        object=obj,
    )


def _contains_hint(text: str, hint: str | None) -> bool:
    if not hint:
        return False
    compact_text = re.sub(r"\s+", "", text).casefold()
    compact_hint = re.sub(r"\s+", "", hint).casefold()
    return compact_hint in compact_text


def _extract_engineering_context(question: str) -> EngineeringContext:
    lower = question.casefold()
    structure_type = None
    for value, pattern in {
        "beam": r"梁|\bbeams?\b",
        "slab": r"板|\bslabs?\b",
        "column": r"柱|\bcolumns?\b",
        "wall": r"墙|\bwalls?\b",
        "foundation": r"基础|\bfoundations?\b",
    }.items():
        if re.search(pattern, lower, re.IGNORECASE):
            structure_type = value
            break

    limit_state = None
    if re.search(r"\bULS\b|承载", question, re.IGNORECASE):
        limit_state = "ULS"
    elif re.search(r"\bSLS\b|正常使用", question, re.IGNORECASE):
        limit_state = "SLS"

    concrete_match = re.search(r"\bC\d{2}(?:/\d{2})?\b", question, re.IGNORECASE)
    rebar_match = re.search(r"\bB\d{3}[A-Z]?\b", question, re.IGNORECASE)
    return EngineeringContext(
        structure_type=structure_type,
        limit_state=limit_state,
        load_combination=bool(re.search(r"组合|combination", question, re.IGNORECASE))
        or None,
        concrete_class=concrete_match.group(0).upper() if concrete_match else None,
        rebar_grade=rebar_match.group(0).upper() if rebar_match else None,
        prestressed=True
        if re.search(r"预应力|prestress", question, re.IGNORECASE)
        else None,
        discontinuity_region=True
        if re.search(r"不连续区|D[- ]?region", question, re.IGNORECASE)
        else None,
    )


def _derive_guide_hint(
    question: str,
    question_type: QuestionType | None,
) -> GuideHint | None:
    if question_type is None:
        return None
    wants_example = bool(
        re.search(r"算例|例子|示例|example|worked example", question, re.IGNORECASE)
    )
    need_example = question_type == QuestionType.CALCULATION or wants_example
    return GuideHint(
        need_example=need_example,
        example_query=question if need_example else None,
        example_kind="worked_example" if wants_example else None,
    )


def _refine_question_type(
    question: str,
    parsed_type: QuestionType | None,
) -> QuestionType | None:
    if re.search(r"有什么作用|为什么|why\b", question, re.IGNORECASE):
        return parsed_type
    if re.search(
        r"分项系数|partial\s+factors?|gamma|γ[GCQSM]",
        question,
        re.IGNORECASE,
    ):
        return QuestionType.PARAMETER
    return parsed_type


def _derive_intent_label(question_type: QuestionType | None) -> str | None:
    if question_type is None:
        return None
    return {
        QuestionType.RULE: "assumption",
        QuestionType.PARAMETER: "limit",
        QuestionType.CALCULATION: "formula",
        QuestionType.MECHANISM: "mechanism",
    }[question_type]


async def analyze_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
    history: list[dict[str, str]] | None = None,
    source_question: str | None = None,
) -> QueryAnalysis:
    """组合过滤提取与多角度查询扩展，返回完整分析结果."""
    _ = history
    question = sanitize_input(question)
    filters = extract_filters(question)
    preferred_element_type = extract_preferred_element_type(question)
    expansion = await expand_queries(
        question,
        glossary,
        config,
        source_question=source_question,
    )
    matched_terms = {zh: en for zh, en in glossary.items() if zh in question}
    requested_objects = extract_requested_objects(
        question,
        expansion.target_hint,
    )
    intent_label = expansion.intent_label or _derive_intent_label(expansion.question_type)

    return QueryAnalysis(
        original_question=question,
        expanded_queries=expansion.queries,
        filters=filters,
        matched_terms=matched_terms,
        requested_objects=requested_objects,
        question_type=expansion.question_type,
        engineering_context=_extract_engineering_context(question),
        guide_hint=_derive_guide_hint(question, expansion.question_type),
        intent_label=intent_label,
        target_hint=expansion.target_hint,
        reason_short=intent_label,
        preferred_element_type=preferred_element_type,
        rewritten_question=None,
    )


# ===== 内部辅助 =====


async def _call_llm(
    prompt: str,
    config: ServerConfig | None = None,
    *,
    system_prompt: str | None = None,
) -> str:
    """调用 LLM 获取文本回复（内部使用，可被测试 mock）."""
    cfg = config or ServerConfig()
    api_key = cfg.query_expansion_llm_api_key or cfg.llm_api_key
    base_url = cfg.query_expansion_llm_base_url or cfg.llm_base_url
    model = cfg.query_expansion_llm_model or cfg.llm_model
    client = await get_async_openai_client(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(timeout=30.0, connect=5.0),
        client_factory=AsyncOpenAI,
    )
    messages: list[dict[str, object]]
    if system_prompt is not None:
        if _should_enable_prompt_cache(cfg, base_url=base_url, model=model):
            system_message = _build_cacheable_system_message(system_prompt)
        else:
            system_message = {"role": "system", "content": system_prompt}
        messages = [system_message, {"role": "user", "content": prompt}]
    else:
        messages = [{"role": "user", "content": prompt}]
    logger.info("query_expansion_llm_start model=%s", model)
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
    )
    logger.info("query_expansion_llm_end")
    return resp.choices[0].message.content.strip()
