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
import httpx

from server.config import ServerConfig
from server.models.schemas import (
    Chunk,
    Confidence,
    ElementType,
    EngineeringContext,
    QueryResponse,
    QuestionType,
    RetrievalContext,
    Source,
)

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
    normalized = re.sub(r"[^A-Za-z0-9\-]+", "_", normalized)
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
    # 剥离 LaTeX 公式（$...$, $$...$$）
    normalized = re.sub(r"\$\$.*?\$\$", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\$[^$\n]+?\$", " ", normalized)
    # 剥离 Markdown 强调标记（**...**、*...*、__...__、_..._）
    normalized = re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"\1", normalized)
    normalized = re.sub(r"_{1,2}([^_\n]+?)_{1,2}", r"\1", normalized)
    if normalized == content:
        return content.strip()
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
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


def _build_retrieval_context_entry(
    chunk: Chunk, score: float | None = None
) -> dict[str, Any]:
    """Build a frontend-exportable retrieval snapshot item from a chunk."""
    meta = chunk.metadata
    entry: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "document_id": _build_document_id(meta.source),
        "file": meta.source,
        "title": meta.source_title,
        "section": " > ".join(meta.section_path),
        "page": str(meta.page_numbers[0]) if meta.page_numbers else "",
        "clause": ", ".join(meta.clause_ids[:2]) if meta.clause_ids else "",
        "content": chunk.content,
    }
    if score is not None:
        entry["score"] = score
    return entry


def _build_retrieval_context(
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk] | None = None,
    scores: list[float] | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
) -> RetrievalContext:
    """Build the export-ready retrieval context snapshot for one answer turn."""
    chunk_items = [
        _build_retrieval_context_entry(
            chunk,
            score=scores[index] if scores and index < len(scores) else None,
        )
        for index, chunk in enumerate(chunks)
    ]
    parent_chunk_items = [
        _build_retrieval_context_entry(chunk) for chunk in parent_chunks
    ]
    ref_chunk_items = [
        _build_retrieval_context_entry(chunk) for chunk in (ref_chunks or [])
    ]
    return RetrievalContext(
        chunks=chunk_items,
        parent_chunks=parent_chunk_items,
        ref_chunks=ref_chunk_items,
        resolved_refs=list(resolved_refs or []),
        unresolved_refs=list(unresolved_refs or []),
    )


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
1. 所有回答必须基于提供的规范原文，不要编造规范中不存在的内容。但利用规范中的公式、表格数据和已知参数进行代入计算、演示计算步骤属于合理应用，不属于编造。
2. 回答用中文，但保留原文中的关键术语（如条款编号、表格编号、公式编号）。
3. 必须标注出处。每个检索片段以 [Ref-N] 标签开头，回答中引用时使用相同的 [Ref-N] 格式（如 [Ref-1]），不要使用文件名/条款号/页码格式的引用。不要编造不存在的引用编号。
4. sources 字段只返回原文定位信息，不要在 sources.translation 中填写中文翻译，统一返回空字符串。
5. 如果需要推理，说明推理过程。
6. 先给出基于当前片段可以直接确认的答案，不要先写空泛否定。
7. 如果当前片段只能支持部分答案，先明确写出"当前片段可确认"的内容，再单独说明"仍需补充"的信息或应参考的其他规范。
8. 只有在当前片段连部分答案都无法支持时，才说明"根据当前检索片段无法确认"，并解释具体缺口。
9. 当检索片段中包含表格（Table）且该表格与回答直接相关时，必须在回答中完整呈现整个表格的内容，不要只摘取部分行或列。表格是工程师查阅参数的核心依据，截断会导致信息缺失。
10. 当问题涉及计算方法、验算流程或公式应用时，你的核心任务是从检索到的公式和表格中合成一个完整的验算流程，让工程师知道"怎么算"。必须按以下结构组织：

   **第一部分：验算流程概述**
   用一句话说明该验算的目的（如"判断截面抗弯承载力是否满足 M_Ed ≤ M_Rd"），然后列出计算步骤的总体流程图：Step 1 → Step 2 → … → 结论。

   **第二部分：分步详解**
   每一步必须包含：
   - 所用公式及编号（如 Expression (6.1)）
   - 每个参数的含义、单位、取值方法（注明"查 Table 3.1"或"由 Step X 得到"或"由国家附录规定"等）
   - 代入数值的演算过程（选一个典型参数，如 C30/37 混凝土、B500 钢筋、截面 300×500mm）

   **第三部分：数值算例**
   必须给出一个完整的数值算例。选取常见的典型参数，从头到尾演示每一步的代入和计算结果。格式示例：
   > Step 1：确定材料设计值
   > f_cd = f_ck / γ_c = 30 / 1.5 = 20.0 MPa（依据 Expression (3.15)，γ_c 见 Table 2.1N）
   > f_yd = f_yk / γ_s = 500 / 1.15 = 434.8 MPa
   >
   > Step 2：计算受压区高度 ...
   如果片段中的公式或表格数据不足以完成完整算例，则演算到片段数据所能支持的步骤为止，并明确指出缺失的数据需查阅哪个条款或表格。

   **第四部分：参数关系与查表**（如适用）
   - 多参数之间的依赖关系用表格或流程图说明
   - 查表时给出具体示例：如"以 C30/37 为例，查 Table 3.1 得 f_cm = 38 MPa, E_cm = 33 GPa, f_ctm = 2.9 MPa"

输出格式：严格 JSON，结构如下：
{
  "answer": "中文回答",
  "sources": [{"file": "EN 1990:2002", "title": "...", "section": "...", "page": 28, "clause": "...", "original_text": "...", "translation": ""}],
  "related_refs": ["相关的其他规范引用"],
  "confidence": "high|medium|low"
}"""

# ---------------------------------------------------------------------------
# 问题类型专属模板系统（替代旧 7 段统一模板）
# ---------------------------------------------------------------------------

_PARAMETER_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("result", "直接结果"),
        ("lookup_path", "怎么查到的"),
        ("limitations", "使用限制"),
    ],
    "guidance": {
        "result": (
            "必须在第一行直接给出用户查询的数值，格式为「参数名 = 数值 单位 [Ref-N]」。"
            "如果检索到了表格数据，直接提取具体数值，绝不能只说「请查阅表格」或「需参见表 X」。"
            "如果该数值取决于特定条件（如环境类别、材料等级、结构类型），必须说明当前给出的值对应什么条件。"
            "如有多个相关数值，用列表或 Markdown 表格呈现。"
        ),
        "lookup_path": (
            "给出完整的查表路径：告诉用户从哪个表格出发，沿着哪个行和列条件定位到数值。"
            "格式示例：「查 Table X → 行条件：Y → 列条件：Z → 得到 结果」。"
            "如有多个参数互相依赖，用 Markdown 表格列出参数之间的关系。"
        ),
        "limitations": (
            "列出影响这个数值成立的关键前提条件，包括：适用的构件类型或材料；"
            "是否需要查 National Annex 确认最终值；哪些工况下此值可能不适用。"
            "不要写「建议结合实际情况」之类的空话，必须说明具体是什么情况。"
        ),
    },
}

_RULE_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("rule_content", "规定内容"),
        ("scope", "适用范围与限制"),
        ("engineering_action", "工程上怎么做"),
    ],
    "guidance": {
        "rule_content": (
            "先用 1-3 句中文概括这条规则在说什么，它要控制什么工程问题。"
            "然后引用原文中最关键的表述，标注 [Ref-N]。"
            "对中国工程师不直观的术语（如 accidental design situation、serviceability limit state）"
            "必须给出中文工程含义。"
        ),
        "scope": (
            "明确列出适用对象：什么类型的构件、什么工况、什么材料。"
            "明确指出不适用情况：什么条件下此规则不成立。"
            "指出边界因素：是否受 National Annex、项目参数或构件分类影响。"
        ),
        "engineering_action": (
            "把这条规则转化成具体工程动作。例如：设计阶段需要校核什么；"
            "施工审查时重点关注什么；出图标注时需要体现什么。"
            "不要只说「应按规范执行」，必须说明具体执行什么。"
        ),
    },
}

_CALCULATION_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("steps", "逐步计算"),
        ("inputs", "输入条件"),
        ("result_summary", "计算结果摘要"),
        ("limitations", "使用限制"),
    ],
    "guidance": {
        "steps": (
            "按 Step 1 → Step 2 → … → 最终结果 的结构组织。每步必须包含：\n"
            "1. 公式编号和 LaTeX 表达式\n"
            "2. 参数含义、单位、取值来源\n"
            "3. 代入具体数值的计算过程\n"
            "选取典型参数（如 C30/37、B500、300×500mm 截面）完成数值算例。\n"
            "严格区分：规范表达式、推荐值（recommended）、本国最终值（标注 NA 待确认）、项目计算值。\n"
            "最后一步给出最终结果，格式为「参数名 = 数值 单位（公式 X.X [Ref-N]）」。\n"
            "如果输入条件不完整，推导到数据支持的步骤为止，说明缺什么参数才能继续。"
        ),
        "inputs": (
            "用 Markdown 表格列出所有参与计算的参数：\n"
            "| 符号 | 含义 | 单位 | 取值来源 | 当前取值 |\n"
            "对于缺失的参数，在「当前取值」列标注「缺失 — 需查 XX」。"
        ),
        "result_summary": (
            "用 1-3 行总结最终计算结果，格式为「参数名 = 数值 单位 [Ref-N]」。"
            "如果计算未能完成，说明「当前推导到 Step X，结果为 Y；最终结论还需 Z 参数」。"
        ),
        "limitations": (
            "列出这个计算方法适用的范围和限制条件，包括：公式适用于什么类型的构件和工况；"
            "哪些参数需要查 National Annex 确认；哪些输入需要用户根据项目条件补充。"
        ),
    },
}

_MECHANISM_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("conclusion", "结论"),
        ("explanation", "原理解释"),
        ("impact", "工程影响"),
    ],
    "guidance": {
        "conclusion": (
            "用 1-3 句话直接回答用户的「为什么」问题，标注 [Ref-N]。"
            "如果检索到的条文没有直接解释原因，必须说明「当前片段未直接给出原因」，"
            "然后基于条文内容做有限分析。"
        ),
        "explanation": (
            "基于检索到的条文或注释解释这条规则的设计原理。"
            "只能使用检索片段中的内容，不能凭自身知识编造规范意图。"
            "如果检索到了 Designers' Guide 的解释性内容，可以引用。"
        ),
        "impact": (
            "说明这条规则的原理对实际工程意味着什么：对设计有什么影响；"
            "对施工有什么影响；违反时会有什么后果（仅当检索内容提及时）。"
        ),
    },
}

_OPEN_TEMPLATES: dict[str, dict[str, Any]] = {
    "parameter": _PARAMETER_TEMPLATE,
    "rule": _RULE_TEMPLATE,
    "calculation": _CALCULATION_TEMPLATE,
    "mechanism": _MECHANISM_TEMPLATE,
}

# 基础规则（所有问题类型通用）
_STREAM_BASE_RULES = [
    "所有回答必须严格基于提供的规范片段，不得编造规范中不存在的要求、数值或例外。"
    "但利用规范中的公式、表格数据和已知参数进行代入计算、演示计算步骤属于合理应用，不属于编造。",
    "直接输出 Markdown 正文，不要输出 JSON，不要输出 ```json 代码块，"
    "也不要输出 answer/sources/confidence 等键名。",
    "回答必须使用中文，并保留关键英文术语、条款编号、表格编号、公式编号。",
    "引用时只能使用检索片段中实际出现的 [Ref-N] 标签；不要编造引用编号；"
    "不要用文件名/条款号/页码格式替代 [Ref-N]；"
    "正文中若需提及其他条款号，直接写正文即可。",
    "如果当前片段只能支持部分答案，先写当前片段可确认的部分，"
    "再写仍需补充或需参考其他规范的部分。",
    "不要把「根据当前检索片段无法确认」作为开头；"
    "只有在当前片段连部分答案都无法支持时，才可以使用这类表述。",
    "可以解释或翻译原文，但不要虚构来源。",
    "当检索片段中包含与问题直接相关的表格时，必须完整呈现整个表格内容，"
    "并转换为 Markdown 表格语法，不要直接输出 HTML 标签。",
    # 反空话规则
    "禁止输出以下模式的空话："
    "「根据规范要求，应…」→ 必须指出哪条规范的哪条具体要求；"
    "「建议参考相关标准」→ 必须指出具体哪个标准的哪个条款；"
    "「具体数值需查阅表 X」→ 如果检索到了表 X，必须直接给出数值；"
    "「在实际工程中应注意…」→ 必须说明具体注意什么、为什么；"
    "「需结合项目实际情况」→ 必须说明哪些具体的项目参数会影响结论；"
    "「应符合相关规定」→ 必须说明是哪条规定。"
    "每个段落必须包含至少一种实质内容：具体数值（带单位和 [Ref-N]）、具体条款号、具体操作步骤、或具体判断条件。"
    "如果某段无法提供任何实质内容，则该段不输出。",
    # 极度保守规则
    "检索片段中没有直接提及的数值，不能在回答中出现。"
    "检索片段中没有直接支持的结论，不能写成「规范要求」。"
    "如果证据只能支持部分回答，必须明确说明「当前证据可确认 X，但 Y 仍需查阅 Z 条款」。"
    "宁可回答不完整，也不能回答不正确。",
]


def decide_generation_mode(
    answer_mode: str | None,
    groundedness: str | None,
) -> str:
    """根据路由意图和 groundedness 决定最终回答模板。"""
    normalized_answer_mode = (answer_mode or "").strip().lower()
    normalized_groundedness = (groundedness or "").strip().lower()

    if normalized_answer_mode == "exact" and normalized_groundedness == "grounded":
        return "exact"
    if normalized_answer_mode == "exact" and normalized_groundedness == "exact_not_grounded":
        return "exact_not_grounded"
    return "open"


def _normalize_question_type(question_type: str | QuestionType | None) -> str | None:
    """将各种形式的 question_type 统一为小写字符串或 None。"""
    if isinstance(question_type, QuestionType):
        return question_type.value
    if isinstance(question_type, str):
        try:
            return QuestionType(question_type.strip().lower()).value
        except ValueError:
            return None
    return None


def _normalize_intent_label(intent_label: str | None) -> str | None:
    """Normalize routed exact intent labels to a known small set."""
    if not isinstance(intent_label, str):
        return None
    normalized = intent_label.strip().lower()
    if normalized in {
        "definition",
        "assumption",
        "applicability",
        "formula",
        "limit",
        "clause_lookup",
    }:
        return normalized
    return None


_CLAUSE_FAMILY_RE = re.compile(r"\d+(?:\.\d+)*")
_VISUAL_QUERY_RE = re.compile(
    r"(?:表格?|图示?|图表|公式|方程|表达式|table|figure|fig\.?|equation|formula)",
    re.IGNORECASE,
)


def _extract_clause_families(chunk: Chunk) -> set[str]:
    """Extract coarse clause families from a chunk's clause IDs and headings."""
    families: set[str] = set()
    for value in [*chunk.metadata.clause_ids, *chunk.metadata.section_path]:
        if not value:
            continue
        matches = _CLAUSE_FAMILY_RE.findall(value)
        if matches:
            families.add(matches[0])
    return families


def _question_requests_visual_support(question: str) -> bool:
    """Detect whether the user explicitly asks about tables, figures, or formulas."""
    return bool(_VISUAL_QUERY_RE.search(question or ""))


def _chunks_share_exact_neighborhood(primary_clause: Chunk, candidate: Chunk) -> bool:
    """Check whether a candidate chunk is in the same local clause neighborhood."""
    if candidate.metadata.source != primary_clause.metadata.source:
        return False
    if candidate.metadata.parent_text_chunk_id == primary_clause.chunk_id:
        return True
    if primary_clause.metadata.parent_text_chunk_id == candidate.chunk_id:
        return True
    if (
        candidate.metadata.section_path
        and candidate.metadata.section_path == primary_clause.metadata.section_path
    ):
        return True
    return bool(_extract_clause_families(primary_clause) & _extract_clause_families(candidate))


def _chunk_matches_primary_cross_refs(primary_clause: Chunk, candidate: Chunk) -> bool:
    """Check whether a candidate matches explicit cross references mentioned by primary."""
    refs = {ref.strip().lower() for ref in primary_clause.metadata.cross_refs if ref.strip()}
    if not refs:
        return False
    labels = {
        label.strip().lower()
        for label in (
            [candidate.metadata.object_label]
            + candidate.metadata.object_aliases
            + candidate.metadata.clause_ids
        )
        if label and label.strip()
    }
    return bool(refs & labels)


def _should_surface_exact_visual_support(
    primary_clause: Chunk,
    candidate: Chunk,
    question: str,
    intent_label: str | None,
) -> bool:
    """Decide whether a non-text chunk should be surfaced as exact supporting evidence."""
    normalized_intent = _normalize_intent_label(intent_label)
    if _question_requests_visual_support(question):
        return True
    if normalized_intent in {"assumption", "definition", "applicability", "clause_lookup"}:
        return False
    return (
        _chunks_share_exact_neighborhood(primary_clause, candidate)
        or _chunk_matches_primary_cross_refs(primary_clause, candidate)
    )


def _should_surface_exact_text_support(
    primary_clause: Chunk,
    candidate: Chunk,
) -> bool:
    """Decide whether a text chunk is close enough to support the primary clause."""
    return _chunks_share_exact_neighborhood(primary_clause, candidate)


def _normalize_engineering_context(
    engineering_context: EngineeringContext | dict[str, Any] | None,
) -> EngineeringContext | None:
    """将 dict 或 EngineeringContext 统一为 EngineeringContext 实例。"""
    if isinstance(engineering_context, EngineeringContext):
        return engineering_context
    if isinstance(engineering_context, dict):
        try:
            return EngineeringContext.model_validate(engineering_context)
        except Exception:
            logger.warning("engineering_context_validation_failed", exc_info=True)
    return None


def build_open_system_prompt(
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
) -> str:
    """根据问题类型路由到专属模板，构建流式系统提示词。"""
    qt = _normalize_question_type(question_type) or "rule"
    ctx = _normalize_engineering_context(engineering_context)
    template = _OPEN_TEMPLATES[qt]

    # Part A: 角色 + 基础规则（含反空话和极度保守规则）
    lines: list[str] = [
        "你是一位精通欧洲建筑规范（Eurocode）的专家，"
        "正在帮助不熟悉 Eurocode 的中国工程师理解规范要求，并把结论安全地用于真实工程项目。",
        "",
        "基础规则：",
    ]
    for i, rule in enumerate(_STREAM_BASE_RULES, 1):
        lines.append(f"{i}. {rule}")

    # Part B: 问题类型专属模板
    section_count = len(template["sections"])
    section_names = "、".join(name for _, name in template["sections"])
    lines.extend([
        "",
        f"问题类型：{qt}。",
        f"回答结构要求：严格使用以下 {section_count} 个三级标题（### ）并按顺序输出（{section_names}）。",
    ])
    for key, zh_name in template["sections"]:
        guidance = template["guidance"][key]
        lines.append(f"### {zh_name}")
        lines.append(f"   {guidance}")

    # Part C: 工程上下文与条件化答案
    lines.append("")
    if ctx:
        known = {
            k: v for k, v in ctx.model_dump().items()
            if v is not None and not (isinstance(v, str) and not v.strip())
        }
        missing = ctx.missing_fields
        if known:
            items = ", ".join(
                f"{k}={'是' if v is True else '否' if v is False else v}"
                for k, v in known.items()
            )
            lines.append(f"已识别工程上下文：{items}")
        if missing:
            lines.append(
                "以下工程背景未提供：" + "、".join(missing) + "。"
                "请先给出一般原则下的回答，然后在最后一个段落末尾列出"
                "「若需确定性答案，还需提供：……」。"
            )
    else:
        lines.append(
            "工程上下文未识别。请给出通用原则回答，"
            "并在最后一个段落末尾提示工程师需要补充哪些项目信息。"
        )

    lines.extend(["", "目标：输出适合前端直接渲染的高质量 Markdown 中文答案。"])
    return "\n".join(lines)


def _build_exact_intent_guidance(intent_label: str | None) -> str:
    """Provide extra exact-answering guardrails for routed exact intents."""
    normalized = _normalize_intent_label(intent_label)
    if normalized in {"assumption", "definition", "applicability"}:
        return (
            "意图补充：当前问题属于 assumption / definition / applicability 类精确问法。\n"
            "优先直接枚举主依据条款中的结论，不要先绕去支持性表格、图示或辅助条文。\n"
            "只有当主依据条款本身明确依赖某个表格、图示或辅助条文，且这些内容对当前问题直接必要时，才补充展开。\n"
            "不要因为检索里顺带包含表格、图示或相关条文，就把答案重心转移到这些支持材料上。"
        )
    if normalized == "limit":
        return (
            "意图补充：当前问题属于 limit 类精确问法。\n"
            "如果问题在问限值，必须直接提取并引用这些数值。\n"
            "如果主依据或直接引用中给出了限值、阈值、范围或取值条件，必须直接提取并引用这些数值，不要只描述原则。"
        )
    if normalized == "formula":
        return (
            "意图补充：当前问题属于 formula 类精确问法。\n"
            "优先给出主依据中的公式表达式、变量含义和适用条件；只有在公式求值直接需要时，才补充相关参数表。"
        )
    if normalized == "clause_lookup":
        return (
            "意图补充：当前问题属于 clause_lookup 类精确问法。\n"
            "先明确回答具体文档、条款号或标题定位，再给出该条款的核心内容，不要展开无关推导。"
        )
    return ""


def _build_exact_answer_focus_note(intent_label: str | None) -> str:
    """Add a short focus note to the evidence pack for exact answers."""
    normalized = _normalize_intent_label(intent_label)
    if normalized in {"assumption", "definition", "applicability"}:
        return (
            "先用主依据条款直接回答问题；支持性表格、图示、辅助条文只在主条款明确需要时才补充，"
            "不要让支持材料取代主答案。"
        )
    if normalized == "limit":
        return "优先提取主依据中的限值、阈值、范围和适用条件，不要只给原则表述。"
    if normalized == "formula":
        return "优先给出公式本体、变量含义和适用条件，再补充求值所需参数。"
    if normalized == "clause_lookup":
        return "先回答文档与条款定位，再概括该条款的核心内容。"
    return ""


def build_exact_system_prompt(intent_label: str | None = None) -> str:
    """精确型 grounded 问题使用条款/表图优先模板。"""
    lines = [
        "你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师精确定位规范依据，并把精确结论安全地用于工程判断。",
        "",
        "规则：",
        "1. 仅基于已检索到的直接证据作答；如果证据不足，只能说明当前已确认到的范围，不要把未检索到的内容写成确定结论。",
        "2. 读者默认是不熟悉 Eurocode 的中国工程师，所以在精确回答后，仍需补一层必要解释，说明这条规定应如何理解和使用，但不要扩写成培训讲义。",
        "3. 引用时只能使用检索片段中实际出现的 [Ref-N] 标签。",
        "4. 保持四个小节结构，不要使用固定 8 段长模板，不要输出泛化的长篇工程建议，不要强行补充国家附录讨论。",
        "5. 如果检索片段中包含表格数据，且其中的数值与问题直接相关，你必须在答案中引用这些具体数值（如限值、系数、参数），绝不能只说\"请查阅表格\"或\"需参见表 X\"。将关键行/列提取为 Markdown 表格或列表呈现给用户。",
        "6. 如果问题涉及定义、假设、公式、限值或条款定位，应先直接回答该点，再补充必要的限定条件和交叉引用。",
        "7. 禁止输出不含实际信息的句子，包括但不限于：「请查阅表 X」— 如果检索到了表 X 的数据，必须直接提取数值；「需参见规范」— 必须指出具体哪条规范的哪个条款；「根据规范要求应…」— 必须说明是哪条规范的哪条具体要求；「建议结合项目实际情况」— 必须说明哪些具体的项目参数会影响结论。",
        "8. 回答中出现的每个具体数值（系数、限值、参数值、判断阈值）都必须标注 [Ref-N]。没有 [Ref-N] 支撑的数值不允许出现在回答中。",
    ]
    intent_guidance = _build_exact_intent_guidance(intent_label)
    if intent_guidance:
        lines.extend(["", intent_guidance])
    lines.extend([
        "",
        "请严格按以下四个小节输出：",
        "### 直接答案",
        "先直接回答用户的问题；如果片段中有具体数值、公式或判断条件，应在这里先说清楚。",
        "",
        "### 关键依据",
        "列出最关键的条款、表格、公式或 [Ref-N]，不要泛泛罗列无关内容。",
        "",
        "### 这条规定应如何理解和使用",
        "只做中度展开，解释这条规定在工程上意味着什么、应如何理解和使用；必要时解释术语，但不要扩写成长篇泛论。",
        "",
        "### 使用时要再核对的条件",
        "列出仍需核对的适用条件、项目参数、National Annex、构件类别或边界前提。",
        "",
        "目标：输出适合前端直接渲染的 Markdown 中文答案，篇幅以把证据链、关键参数和交叉引用说明清楚为准。",
    ])
    return "\n".join(lines)


def build_exact_not_grounded_system_prompt() -> str:
    """精确型但证据不足时，输出保守教学式 guardrail 模板。"""
    return """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师判断当前证据是否足以支持精确回答。

规则：
1. 当前模式是 exact_not_grounded：只能基于当前片段说明"已确认到哪里"，不能把相关材料包装成直接依据。
2. 读者是不熟悉 Eurocode 的中国工程师，所以你要把“不足以直接下结论”的原因讲清楚，但不要扩写成开放式讲解或替代证据下结论。
3. 只能使用检索片段中实际出现的 [Ref-N] 标签引用。
4. 明确区分"当前能确认的内容"和"为什么还不能直接下结论"。
5. 说明这种证据缺口会怎样影响工程决策，并给出下一步应优先补查什么。

请严格按以下四个小节输出：
### 当前能确认的内容
### 为什么还不能直接下结论
### 对工程决策的影响
### 下一步应优先补查什么
"""


def _build_json_system_prompt(mode: str, intent_label: str | None = None) -> str:
    """为非流式 JSON 回答选择 system prompt。"""
    if mode == "exact":
        return build_exact_system_prompt(intent_label=intent_label) + "\n\n输出格式：严格 JSON，包含 answer/sources/related_refs/confidence。"
    if mode == "exact_not_grounded":
        return build_exact_not_grounded_system_prompt() + "\n\n输出格式：严格 JSON，包含 answer/sources/related_refs/confidence。"
    return _SYSTEM_PROMPT


def _build_stream_mode_system_prompt(
    mode: str,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    intent_label: str | None = None,
) -> str:
    """为流式 Markdown 回答选择 system prompt。"""
    if mode == "exact":
        return build_exact_system_prompt(intent_label=intent_label)
    if mode == "exact_not_grounded":
        return build_exact_not_grounded_system_prompt()
    return build_open_system_prompt(question_type, engineering_context)


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
    ref_chunks: list[Chunk] | None = None,
    generation_mode: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    intent_label: str | None = None,
) -> str:
    """将检索结果组装为发送给 LLM 的用户提示词。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段（已排序）
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录（多轮会话场景）
        ref_chunks: 交叉引用补充片段（主检索片段中提到但未检索到的 Table/Figure 等）

    Returns:
        组装完成的提示词字符串
    """
    parts: list[str] = []
    # 术语对照（帮助 LLM 理解中英对应关系）
    if glossary_terms:
        terms = ", ".join(f"{zh}={en}" for zh, en in glossary_terms.items())
        parts.append(f"相关术语对照：{terms}\n")

    if generation_mode in {"exact", "exact_not_grounded"}:
        exact_candidates = _collect_exact_evidence_candidates(
            chunks,
            parent_chunks,
            ref_chunks,
        )
        evidence = _build_exact_evidence_pack(
            exact_candidates,
            question,
            intent_label=intent_label,
        )
        primary_clause: Chunk | None = evidence["primary_clause"]
        supporting_visuals: list[Chunk] = evidence["supporting_visuals"]
        supporting_context: list[Chunk] = evidence["supporting_context"]
        parts.append("exact 证据包（回答时优先使用，不要遗漏）：\n")
        focus_note = _build_exact_answer_focus_note(intent_label)
        if focus_note:
            parts.append(f"回答重心提示：{focus_note}\n")
        if primary_clause is not None:
            meta = primary_clause.metadata
            parts.append(
                "主依据条款：\n"
                f"- 来源：{meta.source}\n"
                f"- 章节：{' > '.join(meta.section_path)}\n"
                f"- 条款：{', '.join(meta.clause_ids[:3]) if meta.clause_ids else '无'}\n"
                f"- 内容：{primary_clause.content}\n"
            )
        if supporting_visuals:
            parts.append("相关表/图/公式：\n")
            for item in supporting_visuals:
                meta = item.metadata
                parts.append(
                    f"- {meta.element_type.value}: {meta.source} | "
                    f"{' > '.join(meta.section_path)} | "
                    f"{', '.join(meta.clause_ids[:2]) if meta.clause_ids else '无编号'}\n"
                    f"  {item.content}\n"
                )
        if supporting_context:
            parts.append("辅助说明片段：\n")
            for item in supporting_context:
                meta = item.metadata
                parts.append(
                    f"- {meta.source} | {' > '.join(meta.section_path)} | "
                    f"{', '.join(meta.clause_ids[:2]) if meta.clause_ids else '无编号'}\n"
                    f"  {item.content}\n"
                )
        selected_chunk_ids = {
            chunk.chunk_id
            for chunk in [primary_clause, *supporting_visuals, *supporting_context]
            if chunk is not None
        }
        deferred_count = sum(
            1 for chunk in exact_candidates if chunk.chunk_id not in selected_chunk_ids
        )
        if deferred_count:
            parts.append(
                "其他相关片段："
                f"另有 {deferred_count} 个候选片段仅作背景参考；"
                "除非主依据条款明确需要，否则不要让这些片段主导答案。\n"
            )
        if resolved_refs:
            parts.append("已补齐的直接引用：\n")
            for ref in resolved_refs:
                parts.append(f"- {ref}\n")
        if unresolved_refs:
            parts.append("尚未补齐的直接引用：\n")
            for ref in unresolved_refs:
                parts.append(f"- {ref}\n")

    # 主要检索片段
    ordered_citable = _build_prioritized_source_chunks(
        chunks,
        parent_chunks,
        ref_chunks=ref_chunks,
        generation_mode=generation_mode,
        question=question,
        intent_label=intent_label,
    )
    if generation_mode in {"exact", "exact_not_grounded"}:
        parts.append("检索到的规范内容（按回答优先级排序）：\n")
    else:
        parts.append("检索到的规范内容：\n")
    for i, chunk in enumerate(ordered_citable, 1):
        meta = chunk.metadata
        page_str = ",".join(map(str, meta.page_numbers))
        section_str = " > ".join(meta.section_path)
        clause_str = ", ".join(meta.clause_ids[:3]) if meta.clause_ids else ""
        source_info = f"{meta.source}, Page {page_str}, {section_str}"
        if clause_str:
            source_info += f", Clause {clause_str}"
        parts.append(f"[Ref-{i}] {source_info}\n{chunk.content}\n")

    # 扩展上下文：去重后的父 chunk 全量纳入，不截断、不限数量
    if parent_chunks:
        seen_parent_ids: set[str] = set()
        deduped_parents: list[Chunk] = []
        for pc in parent_chunks:
            if pc.chunk_id not in seen_parent_ids:
                seen_parent_ids.add(pc.chunk_id)
                deduped_parents.append(pc)
        if deduped_parents:
            parts.append("\n扩展上下文（章节级）：\n")
            for pc in deduped_parents:
                section_str = " > ".join(pc.metadata.section_path)
                parts.append(f"[Parent] {section_str}\n{pc.content}\n")

    # 交叉引用补充内容（开放式模式下单独保留）
    if ref_chunks and generation_mode not in {"exact", "exact_not_grounded"}:
        ref_start = len(chunks) + 1
        parts.append("\n交叉引用补充（主检索片段中提及的表格/图表/公式的实际内容）：\n")
        for j, rc in enumerate(ref_chunks, ref_start):
            meta = rc.metadata
            page_str = ",".join(map(str, meta.page_numbers))
            section_str = " > ".join(meta.section_path)
            clause_str = ", ".join(meta.clause_ids[:3]) if meta.clause_ids else ""
            source_info = f"{meta.source}, Page {page_str}, {section_str}"
            if clause_str:
                source_info += f", Clause {clause_str}"
            parts.append(f"[Ref-{j}] {source_info}\n{rc.content}\n")

    # 历史对话（仅保留最近两轮，避免上下文膨胀）
    if conversation_history:
        parts.append("\n之前的对话：\n")
        for h in conversation_history[-2:]:
            parts.append(f"Q: {h['question']}\nA: {h['answer'][:500]}\n")

    parts.append(f"\n用户问题：{question}")
    return "\n".join(parts)


def _collect_exact_evidence_candidates(
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk] | None = None,
) -> list[Chunk]:
    """收集 exact 模式可用于组织回答的证据候选。

    主检索片段和交叉引用片段始终纳入；父级上下文仅吸收表/图/公式等视觉证据，
    避免把整段父级文本误当成直接引用源。
    """
    candidates: list[Chunk] = []
    seen_ids: set[str] = set()

    def append_unique(items: list[Chunk]) -> None:
        for item in items:
            if item.chunk_id not in seen_ids:
                seen_ids.add(item.chunk_id)
                candidates.append(item)

    append_unique(list(chunks))
    append_unique(list(ref_chunks or []))
    append_unique(
        [
            chunk for chunk in parent_chunks
            if chunk.metadata.element_type in (
                ElementType.TABLE,
                ElementType.FORMULA,
                ElementType.IMAGE,
            )
        ]
    )
    return candidates


def _build_exact_evidence_pack(
    chunks: list[Chunk],
    question: str,
    intent_label: str | None = None,
) -> dict[str, Any]:
    """为 exact 模式挑选主条款、相关表图和少量辅助上下文。"""
    if not chunks:
        return {
            "primary_clause": None,
            "supporting_visuals": [],
            "supporting_context": [],
        }

    primary_clause = next(
        (chunk for chunk in chunks if chunk.metadata.element_type == ElementType.TEXT),
        chunks[0],
    )
    supporting_visuals = [
        chunk for chunk in chunks
        if chunk.chunk_id != primary_clause.chunk_id
        and chunk.metadata.element_type in (
            ElementType.TABLE,
            ElementType.FORMULA,
            ElementType.IMAGE,
        )
        and _should_surface_exact_visual_support(
            primary_clause,
            chunk,
            question,
            intent_label,
        )
    ]
    supporting_context = [
        chunk for chunk in chunks
        if chunk.chunk_id != primary_clause.chunk_id
        and chunk.metadata.element_type == ElementType.TEXT
        and _should_surface_exact_text_support(primary_clause, chunk)
    ][:2]

    return {
        "primary_clause": primary_clause,
        "supporting_visuals": supporting_visuals,
        "supporting_context": supporting_context,
    }


def _build_prioritized_source_chunks(
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk] | None = None,
    generation_mode: str | None = None,
    question: str = "",
    intent_label: str | None = None,
) -> list[Chunk]:
    """Build source ordering that follows the exact evidence pack when needed."""
    if generation_mode not in {"exact", "exact_not_grounded"}:
        return list(chunks) + list(ref_chunks or [])

    evidence = _build_exact_evidence_pack(
        _collect_exact_evidence_candidates(chunks, parent_chunks, ref_chunks),
        question=question,
        intent_label=intent_label,
    )
    prioritized: list[Chunk] = []
    for key in ("primary_clause",):
        chunk = evidence.get(key)
        if chunk is not None:
            prioritized.append(chunk)
    prioritized.extend(evidence.get("supporting_visuals", []))
    prioritized.extend(evidence.get("supporting_context", []))
    ordered: list[Chunk] = []
    seen_ids: set[str] = set()
    for chunk in prioritized + list(chunks) + list(ref_chunks or []):
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered.append(chunk)
    return ordered


def _build_sources_from_chunks(
    chunks: list[Chunk],
    config: ServerConfig | None = None,
    prioritized_chunks: list[Chunk] | None = None,
) -> list[Source]:
    """从检索结果的 metadata 直接构建 Source，不依赖 LLM JSON 解析。"""
    sources: list[Source] = []
    cfg = config or ServerConfig()
    ordered_chunks: list[Chunk] = []
    seen_ids: set[str] = set()
    for chunk in prioritized_chunks or []:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered_chunks.append(chunk)
    for chunk in chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered_chunks.append(chunk)

    for chunk in ordered_chunks:
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
                page=resolved_page or (
                    str(meta.page_file_index[0] + 1) if meta.page_file_index
                    else str(meta.page_numbers[0]) if meta.page_numbers
                    else ""
                ),
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


async def generate_answer_stream(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
    ref_chunks: list[Chunk] | None = None,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    answer_mode: str | None = None,
    groundedness: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    intent_label: str | None = None,
):
    """流式生成 LLM 回答，通过异步生成器逐步输出。

    使用八段式模板动态构建 system prompt，直接输出可渲染 Markdown。
    done 事件的 sources 从检索结果的 metadata 直接构建，不依赖 LLM 解析。

    Yields:
        (event_type, data) 元组
    """
    cfg = config or ServerConfig()
    qt_normalized = _normalize_question_type(question_type)
    ctx_normalized = _normalize_engineering_context(engineering_context)
    generation_mode = decide_generation_mode(answer_mode, groundedness)
    prompt = build_prompt(
        question,
        chunks,
        parent_chunks,
        glossary_terms,
        conversation_history,
        ref_chunks=ref_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        intent_label=intent_label,
    )
    system_prompt = _build_stream_mode_system_prompt(
        generation_mode,
        qt_normalized,
        ctx_normalized,
        intent_label=intent_label,
    )

    client = AsyncOpenAI(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        timeout=httpx.Timeout(timeout=600.0),
    )
    try:
        logger.info(
            "llm_stream_start model=%s max_tokens=%d prompt_len=%d question_type=%s",
            cfg.llm_model, 8192, len(prompt), qt_normalized,
        )
        stream = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8192,
            stream=True,
            **_build_stream_completion_kwargs(cfg),
        )
        chunk_count = 0
        total_content_len = 0
        finish_reason = None
        async for token in stream:
            delta = token.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ("reasoning", {"text": reasoning})

            content = delta.content
            if content:
                chunk_count += 1
                total_content_len += len(content)
                yield ("chunk", {"text": content, "done": False})

            # 记录 finish_reason
            token_finish_reason = getattr(token.choices[0], "finish_reason", None)
            if token_finish_reason:
                finish_reason = token_finish_reason

        logger.info(
            "llm_stream_end chunks=%d content_chars=%d finish_reason=%s",
            chunk_count, total_content_len, finish_reason,
        )

        # 从检索结果直接构建结构化元数据，不依赖 LLM 输出
        # 主 chunk + 交叉引用 chunk 统一编号，与 prompt 中的 [Ref-N] 一一对应
        all_citable = list(chunks) + list(ref_chunks or [])
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            generation_mode=generation_mode,
            question=question,
            intent_label=intent_label,
        )
        # 注意：sources 顺序必须与 build_prompt 中 [Ref-N] 编号完全一致，
        # 前端通过 sources[N-1] 定位 [Ref-N] 对应的证据，不能重排。
        sources = _build_sources_from_chunks(
            all_citable,
            config=cfg,
            prioritized_chunks=prioritized_chunks,
        )
        related_refs = _build_related_refs_from_chunks(chunks)
        confidence = _infer_stream_confidence(scores, has_sources=bool(sources))
        retrieval_context = _build_retrieval_context(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            scores=scores,
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
        )
        yield ("done", {
            "sources": [s.model_dump() for s in sources],
            "related_refs": related_refs,
            "confidence": confidence.value,
            "retrieval_context": retrieval_context.model_dump(),
            "question_type": qt_normalized,
            "engineering_context": ctx_normalized.model_dump() if ctx_normalized else None,
        })
    except Exception:
        logger.exception("llm_stream_failed")
        yield ("error", {"message": "LLM 服务暂时不可用"})


async def generate_answer(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
    ref_chunks: list[Chunk] | None = None,
    answer_mode: str | None = None,
    groundedness: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    intent_label: str | None = None,
) -> QueryResponse:
    """调用 LLM 生成基于检索内容的回答。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录
        config: 服务器配置（为空时使用默认配置）
        ref_chunks: 交叉引用补充片段

    Returns:
        结构化的 QueryResponse；LLM 调用失败时返回降级响应
    """
    cfg = config or ServerConfig()
    retrieval_context = _build_retrieval_context(
        chunks,
        parent_chunks,
        ref_chunks=ref_chunks,
        scores=scores,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
    )
    generation_mode = decide_generation_mode(answer_mode, groundedness)
    prompt = build_prompt(
        question, chunks, parent_chunks, glossary_terms, conversation_history,
        ref_chunks=ref_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        intent_label=intent_label,
    )

    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    try:
        logger.info(
            "llm_call_start model=%s max_tokens=%d prompt_len=%d",
            cfg.llm_model, 8192, len(prompt),
        )
        resp = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": _build_json_system_prompt(
                        generation_mode,
                        intent_label=intent_label,
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        logger.info(
            "llm_call_end finish_reason=%s usage=%s content_len=%d",
            getattr(resp.choices[0], "finish_reason", None),
            getattr(resp, "usage", None),
            len(raw),
        )
        response = parse_llm_response(raw)
        all_citable = list(chunks) + list(ref_chunks or [])
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            generation_mode=generation_mode,
            question=question,
            intent_label=intent_label,
        )
        canonical_sources = _normalize_sources(
            _build_sources_from_chunks(
                all_citable,
                config=cfg,
                prioritized_chunks=prioritized_chunks,
            )
        )
        return response.model_copy(
            update={
                "sources": canonical_sources,
                "retrieval_context": retrieval_context,
            }
        )
    except Exception:
        logger.exception("llm_call_failed")
        return QueryResponse(
            answer="LLM 服务暂时不可用，以下是检索到的相关规范片段。",
            sources=[],
            confidence=Confidence.LOW,
            degraded=True,
            retrieval_context=retrieval_context,
        )
