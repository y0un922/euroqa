"""Query understanding: intent classification + query rewrite + filter extraction.

This module provides the query analysis pipeline for the Eurocode QA system:
1. classify_intent  - 基于正则模式将用户问题分类为 EXACT/CONCEPT/REASONING
2. extract_filters  - 从问题中提取结构化过滤条件（来源文档、元素类型等）
3. rewrite_query    - 借助 LLM 将中文问题改写为英文检索关键词
4. analyze_query    - 组合以上三步，返回完整的 QueryAnalysis 结果
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from server.config import ServerConfig
from server.models.schemas import IntentType

# ---------------------------------------------------------------------------
# 精确引用识别模式 —— 命中任一即判定为 EXACT intent
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
# 精确引用识别模式 —— 命中任一即判定为 EXACT intent
# ---------------------------------------------------------------------------
_EXACT_PATTERNS: list[re.Pattern[str]] = [
    # 公式 / Formula / Eq. + 编号
    re.compile(r"(?:公式|formula|eq\.?)\s*[\d.]+", re.IGNORECASE),
    # 表格 / Table + 编号（如 Table A1.2、表3.1）
    re.compile(r"(?:表格?|table)\s*[A-Z]?\d+[\d.]*", re.IGNORECASE),
    # § 符号 + 节号
    re.compile(r"§\s*\d+", re.IGNORECASE),
    # 三级以上条款编号（如 6.3.5）
    re.compile(r"\d+\.\d+\.\d+"),
]

# ---------------------------------------------------------------------------
# 过滤条件提取用正则
# ---------------------------------------------------------------------------
_SOURCE_RE = re.compile(r"EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_TABLE_RE = re.compile(r"表格?|table", re.IGNORECASE)
_FORMULA_RE = re.compile(r"公式|formula|eq", re.IGNORECASE)


@dataclass
class QueryAnalysis:
    """完整的查询分析结果."""

    intent: IntentType
    original_question: str
    rewritten_query: str
    filters: dict[str, str]
    matched_terms: dict[str, str] = field(default_factory=dict)


# ===== 公开 API =====


def classify_intent(question: str) -> IntentType:
    """根据问题文本判断查询意图类型.

    优先匹配精确引用模式（公式/表格/条款编号），
    其次匹配概念类关键词，
    兜底归为推理类。
    """
    for pattern in _EXACT_PATTERNS:
        if pattern.search(question):
            return IntentType.EXACT

    concept_keywords = [
        "什么是", "定义", "含义", "概念", "区别",
        "what is", "definition",
    ]
    if any(kw in question.lower() for kw in concept_keywords):
        return IntentType.CONCEPT

    return IntentType.REASONING


def extract_filters(question: str) -> dict[str, str]:
    """从问题文本中提取结构化过滤条件.

    当前支持：
    - source:       匹配 "EN xxxx" 系列标准编号
    - element_type: 匹配 表格/公式 关键词
    """
    filters: dict[str, str] = {}

    source_match = _SOURCE_RE.search(question)
    if source_match:
        filters["source"] = f"EN {source_match.group(1)}"

    if _TABLE_RE.search(question):
        filters["element_type"] = "table"
    elif _FORMULA_RE.search(question):
        filters["element_type"] = "formula"

    return filters


async def rewrite_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> str:
    """将中文问题改写为英文检索关键词.

    先用 glossary 做术语对齐，再调用 LLM 生成面向 Eurocode 文档的检索词。
    """
    # 术语匹配
    matched_terms: dict[str, str] = {}
    for zh, en in glossary.items():
        if zh in question:
            matched_terms[zh] = en

    # 构造 prompt
    term_hint = ""
    if matched_terms:
        pairs = ", ".join(f"{zh}={en}" for zh, en in matched_terms.items())
        term_hint = f"已知术语对照：{pairs}\n"

    prompt = (
        "将以下中文工程问题改写为英文检索关键词（用于在 Eurocode 规范文档中搜索）。\n"
        "只输出英文关键词，用空格分隔，不要输出句子。\n"
        f"{term_hint}"
        f"问题：{question}"
    )
    return await _call_llm(prompt, config)


async def analyze_query(
    question: str,
    glossary: dict[str, str],
    config: ServerConfig | None = None,
) -> QueryAnalysis:
    """组合 intent 分类、过滤提取、查询改写，返回完整分析结果."""
    question = sanitize_input(question)
    intent = classify_intent(question)
    filters = extract_filters(question)
    rewritten = await rewrite_query(question, glossary, config)
    matched_terms = {zh: en for zh, en in glossary.items() if zh in question}

    return QueryAnalysis(
        intent=intent,
        original_question=question,
        rewritten_query=rewritten,
        filters=filters,
        matched_terms=matched_terms,
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
        max_tokens=200,
    )
    return resp.choices[0].message.content.strip()
