"""Generation layer: prompt assembly + LLM call + structured output parsing."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.core.generation.citations import _extract_json_text, postprocess_citations
from server.core.generation.confidence import (
    _build_related_refs_from_chunks,
    _infer_answer_confidence,
    parse_llm_response,
)
from server.core.generation.context import (
    _build_retrieval_context,
    _dedupe_chunks_and_scores,
    _dedupe_chunks_by_id,
)
from server.core.generation.sources import (
    _build_prioritized_source_chunks,
    _build_sources_from_chunks,
    _collect_pending_source_indexes,
    _normalize_sources,
    _resolve_chunk_display_title,
)
from server.core.generation.tokens import _count_tokens
from shared.llm_clients import get_async_openai_client
from shared.spot_check import record_spot_check
from server.models.schemas import (
    Chunk,
    Confidence,
    EngineeringContext,
    QueryResponse,
    QuestionType,
    Source,
)

logger = structlog.get_logger()


def _current_async_openai_factory():
    """Resolve package-level AsyncOpenAI so legacy patch paths still work."""
    from server.core import generation as generation_package

    return getattr(generation_package, "AsyncOpenAI", AsyncOpenAI)


# 系统提示词：指导 LLM 以 Eurocode 专家身份回答问题
_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师理解和查询规范内容。

规则：
1. 所有回答必须基于提供的规范原文，不要编造规范中不存在的内容。但利用规范中的公式、表格数据和已知参数进行代入计算、演示计算步骤属于合理应用，不属于编造。
2. 回答用中文，但保留原文中的关键术语（如条款编号、表格编号、公式编号）。
3. 必须标注出处。每个检索片段以 [Ref-N] 标签开头，回答正文中凡涉及条文、表格、公式、数值、结论的句子，必须在句末写 [Ref-N] 标注出处，N 必须对应检索证据的编号，不得编造不存在的编号。不确定来源时不标注，宁可漏标也不错标。不要用自然语言引用（如"依据：《文档名》…"）替代 [Ref-N]。不要编造不存在的条款号或页码。
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
            "必须在第一行直接给出用户查询的数值，格式为「参数名 = 数值 单位；依据：《文档名》，条款/章节：X，页码：Y」。"
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
            "然后引用原文中最关键的表述，并用对应证据元数据写明依据位置。"
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
            "最后一步给出最终结果，格式为「参数名 = 数值 单位（公式 X.X；依据：《文档名》，条款/章节：X，页码：Y）」。\n"
            "如果输入条件不完整，推导到数据支持的步骤为止，说明缺什么参数才能继续。"
        ),
        "inputs": (
            "用 Markdown 表格列出所有参与计算的参数：\n"
            "| 符号 | 含义 | 单位 | 取值来源 | 当前取值 |\n"
            "对于缺失的参数，在「当前取值」列标注「缺失 — 需查 XX」。"
        ),
        "result_summary": (
            "用 1-3 行总结最终计算结果，格式为「参数名 = 数值 单位；依据：《文档名》，条款/章节：X，页码：Y」。"
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
            "用 1-3 句话直接回答用户的「为什么」问题，并写明对应依据位置。"
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
    "检索片段开头的 [Ref-N] 是证据编号。回答正文中凡涉及条文、表格、公式、数值、结论的句子，"
    "必须在句末写 [Ref-N] 标注出处，N 必须对应检索证据的编号，不得编造不存在的编号。"
    "不确定来源时不标注，宁可漏标也不错标。不要用自然语言引用（如「依据：《文档名》…」）替代 [Ref-N]。",
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
    "每个段落必须包含至少一种实质内容：具体数值（带单位和依据位置）、具体条款号、具体操作步骤、或具体判断条件。"
    "如果某段无法提供任何实质内容，则该段不输出。",
    # 极度保守规则
    "检索片段中没有直接提及的数值，不能在回答中出现。"
    "检索片段中没有直接支持的结论，不能写成「规范要求」。"
    "如果证据只能支持部分回答，必须明确说明「当前证据可确认 X，但 Y 仍需查阅 Z 条款」。"
    "宁可回答不完整，也不能回答不正确。",
]


def decide_generation_mode(
    groundedness: str | None,
) -> str:
    """Normalize retrieval groundedness into the generation mode."""
    normalized_groundedness = (groundedness or "").strip().lower()

    if normalized_groundedness in {"grounded", "partial", "not_grounded"}:
        return normalized_groundedness
    return "partial"


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


def _build_question_type_guidance(
    question_type: str | QuestionType | None,
) -> list[str]:
    qt = _normalize_question_type(question_type) or "rule"
    if qt == "calculation":
        return [
            "若问题是“如何计算 / 怎么求 / 步骤是什么”类：优先输出可直接使用的计算说明，顺序尽量为：",
            "1. 计算目标是什么",
            "2. 适用条款/公式",
            "3. 公式中各参数含义",
            "4. 参数应从哪里取值",
            "5. 计算步骤如何展开",
            "6. 结果应如何理解或校核",
            "如果指南证据中存在明显相关的算例或演算过程，应增加“指南参考案例”小节。",
            "“指南参考案例”只用于帮助理解计算路径，应说明案例在算什么、核心步骤是什么，以及它与当前问题对应在哪一步；不能用指南案例替代规范条文结论。",
        ]
    if qt == "parameter":
        return [
            "若问题是“参数取值 / 条款要求 / 限值”类：先给出明确数值或规则，再说明适用条件、前提和限制。",
            "如数值、条件、例外分别来自不同证据，应综合说明，不要分散堆砌。",
        ]
    if qt == "mechanism":
        return [
            "若问题是“定义 / 概念 / 分类 / 总结”类：先直接回答核心结论，再按需要补充边界和归纳。",
        ]
    return [
        "若问题需要跨多个条款或多个文档综合回答：先给出整合后的直接结论，再说明各证据分别支撑哪一部分。",
    ]


def _build_engineering_context_guidance(
    engineering_context: EngineeringContext | dict[str, Any] | None,
) -> str:
    ctx = _normalize_engineering_context(engineering_context)
    if not ctx:
        return "工程上下文未识别。请根据输入证据直接组织回答，并在必要时提醒用户仍需补充的项目条件。"

    known = {
        key: value
        for key, value in ctx.model_dump().items()
        if value is not None and not (isinstance(value, str) and not value.strip())
    }
    if not known:
        return "工程上下文未识别。请根据输入证据直接组织回答，并在必要时提醒用户仍需补充的项目条件。"

    items = ", ".join(
        f"{key}={'是' if value is True else '否' if value is False else value}"
        for key, value in known.items()
    )
    return f"已识别工程上下文：{items}"


def _build_evidence_organizer_system_prompt(
    groundedness: str,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
) -> str:
    lines: list[str] = [
        "你是“欧洲工程规范智能问答系统”的回答整理助手，服务对象是使用中文提问的工程师。",
        "你的任务不是自由聊天，而是：基于系统已经检索到的规范原文证据，整理出一份可供工程师直接使用、且可核查的中文回答。",
        "",
        "核心要求：",
        "1. 只能依据输入证据作答，不得凭常识补充规范中未出现的结论，不得编造条款号、页码、公式、参数或案例。",
        "2. 每一个关键结论都要尽量绑定出处，至少给出文档名、条款号/章节号、页码（若有）。",
        "3. 若现有证据不足，必须明确写出“根据当前检索结果无法确定”或“现有证据不足”，不要输出猜测性内容，不得强行补全。",
        "4. 若存在适用条件、前提假设、国家附录可选值或适用范围限制，必须明确提醒用户。",
        "5. 指南文档只能作为帮助理解或参考计算过程的补充，不能替代规范条文本身。",
        "",
        "多证据整合原则：",
        "1. 先识别问题包含的子问题，再从多个证据中分别提取对应信息，最后整合成一份面向工程师可直接使用的答案。",
        "2. 只能整合彼此一致、互补的内容；若证据之间有适用范围或前提差异，必须明确指出。",
        "",
        "回答组织原则：",
        "1. 优先采用以下结构：直接结论、依据与说明、计算步骤（如适用）、指南参考案例（如找到）、依据位置。",
        "2. 不要机械套模板，但输出必须体现整合后的业务逻辑，而不是简单摘录多个片段。",
        "3. 依据位置格式要求：回答正文中凡涉及条文、表格、公式、数值、结论的句子，必须在句末写 [Ref-N] 标注出处，N 对应检索片段的编号。不确定来源时不标注，宁可漏标也不错标。",
        "4. 不要用自然语言引用（如「依据：《文档名》…」）替代 [Ref-N]；缺少条款号或页码时如实省略，不得补造。",
        "",
        "模式补充：",
    ]
    if groundedness == "not_grounded":
        lines.append(
            "当前检索证据与问题相关性不足。必须明确说明现有证据不足，不要输出猜测性结论。"
        )
        lines.append(
            "如果能从证据中确认很少量事实，只能作为有限事实列出，并说明缺少哪类依据。"
        )
    elif groundedness == "grounded":
        lines.append(
            "当前检索证据相关性较强。可以直接给出结论，但所有关键结论仍必须绑定证据位置。"
        )
    else:
        lines.append(
            "当前检索证据只能支持部分回答。先写可由证据确认的内容，再说明仍需补充的信息。"
        )

    lines.extend(
        [
            "",
            *_build_question_type_guidance(question_type),
            "",
            _build_engineering_context_guidance(engineering_context),
            "",
            "输出风格要求：使用中文，语言清晰、专业、简洁；不要大段照抄原文；不要输出与问题无关的背景知识。",
        ]
    )
    return "\n".join(lines)


def build_open_system_prompt(
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
) -> str:
    """构建默认整理回答的统一系统提示词。"""
    return _build_evidence_organizer_system_prompt(
        "partial",
        question_type=question_type,
        engineering_context=engineering_context,
    )


def _build_json_system_prompt(
    mode: str,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    intent_label: str | None = None,
) -> str:
    """为非流式 JSON 回答选择 system prompt。"""
    del intent_label
    return (
        _build_evidence_organizer_system_prompt(
            mode,
            question_type=question_type,
            engineering_context=engineering_context,
        )
        + "\n\n输出格式：严格 json，包含 answer/sources/related_refs/confidence。"
    )


def _build_stream_mode_system_prompt(
    mode: str,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    intent_label: str | None = None,
) -> str:
    """为流式 Markdown 回答选择 system prompt。"""
    del intent_label
    return _build_evidence_organizer_system_prompt(
        mode,
        question_type=question_type,
        engineering_context=engineering_context,
    )


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
6. 只输出严格 json，格式如下：
{
  "translations": [
    {"index": 0, "translation": "中文解释"}
  ]
}"""


def _is_qwen_provider(config: ServerConfig) -> bool:
    model_name = config.llm_model.lower()
    base_url = config.llm_base_url.lower()
    return "qwen" in model_name or "dashscope.aliyuncs.com" in base_url


def _should_enable_reasoning(config: ServerConfig) -> bool:
    """Return whether the current model/provider should request thinking tokens."""
    if not config.llm_enable_thinking:
        return False
    return _is_qwen_provider(config)


def _build_stream_completion_kwargs(config: ServerConfig) -> dict[str, Any]:
    """Build optional kwargs for reasoning-capable streaming models."""
    kwargs: dict[str, Any] = {}
    if _should_enable_reasoning(config):
        kwargs["extra_body"] = {"enable_thinking": True}
    elif _is_qwen_provider(config):
        kwargs["extra_body"] = {"enable_thinking": False}
    return kwargs


def _format_prompt_chunk_block(
    chunk: Chunk,
    label: str,
    config: ServerConfig | None = None,
) -> str:
    """Format one chunk as a prompt evidence block."""
    meta = chunk.metadata
    page_str = ", ".join(map(str, meta.page_numbers)) if meta.page_numbers else "未提供"
    section_str = " > ".join(meta.section_path) if meta.section_path else "未提供"
    clause_str = ", ".join(meta.clause_ids[:3]) if meta.clause_ids else "未提供"
    display_name = _resolve_chunk_display_title(chunk, config)
    source_name = meta.source
    return (
        f"{label}\n"
        f"文档名: {display_name}\n"
        f"来源ID: {source_name}\n"
        f"章节: {section_str}\n"
        f"条款: {clause_str}\n"
        f"页码: {page_str}\n"
        f"内容:\n{chunk.content}\n"
    )


def _format_prompt_metadata_line(
    chunk: Chunk,
    label: str,
    config: ServerConfig | None = None,
) -> str:
    """Format one chunk as a compact metadata row."""
    meta = chunk.metadata
    section_str = " > ".join(meta.section_path) if meta.section_path else "未提供"
    clause_str = ", ".join(meta.clause_ids[:3]) if meta.clause_ids else "未提供"
    page_str = ", ".join(map(str, meta.page_numbers)) if meta.page_numbers else "未提供"
    display_name = _resolve_chunk_display_title(chunk, config)
    return (
        f"- {label} 文档名: {display_name}; 来源ID: {meta.source}; "
        f"条款/章节: {clause_str} / {section_str}; "
        f"页码: {page_str}; 元素类型: {meta.element_type.value}"
    )


def build_prompt(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    generation_mode: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    intent_label: str | None = None,
    config: ServerConfig | None = None,
) -> str:
    """将检索结果组装为发送给 LLM 的用户提示词。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段（已排序）
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录（多轮会话场景）
        ref_chunks: 交叉引用补充片段（主检索片段中提到但未检索到的 Table/Figure 等）
        guide_chunks: 指南文档补充片段（仅相关问题时提供）
        guide_example_chunks: 指南中的算例/演算过程片段（仅命中时提供）

    Returns:
        组装完成的提示词字符串
    """
    parts: list[str] = []
    # 术语对照（帮助 LLM 理解中英对应关系）
    if glossary_terms:
        terms = ", ".join(f"{zh}={en}" for zh, en in glossary_terms.items())
        parts.append(f"相关术语对照：{terms}\n")

    if conversation_history:
        parts.append("历史对话摘要：\n")
        for history in conversation_history[-2:]:
            parts.append(
                f"- Q: {history['question']}\n  A: {history['answer'][:500]}\n"
            )

    parts.append(f"用户问题：\n{question}\n")

    if generation_mode:
        parts.append(f"证据相关性状态：{generation_mode}\n")
    if resolved_refs:
        parts.append("已补齐的直接引用：\n")
        for ref in resolved_refs:
            parts.append(f"- {ref}\n")
    if unresolved_refs:
        parts.append("尚未补齐的直接引用：\n")
        for ref in unresolved_refs:
            parts.append(f"- {ref}\n")

    ordered_citable = _build_prioritized_source_chunks(
        chunks,
        parent_chunks,
        ref_chunks=ref_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
    )
    parts.append("已检索到的可引用证据片段：\n")
    for i, chunk in enumerate(ordered_citable, 1):
        parts.append(_format_prompt_chunk_block(chunk, f"[Ref-{i}]", config))

    parts.append("证据元数据：\n")
    for i, chunk in enumerate(ordered_citable, 1):
        parts.append(f"{_format_prompt_metadata_line(chunk, f'[Ref-{i}]', config)}\n")
    citable_ids = {chunk.chunk_id for chunk in ordered_citable}
    if guide_chunks:
        parts.append("指南文档补充说明：\n")
        appended = False
        for index, guide_chunk in enumerate(guide_chunks, 1):
            if guide_chunk.chunk_id not in citable_ids:
                parts.append(
                    _format_prompt_chunk_block(
                        guide_chunk,
                        f"[GuideContext-{index}]",
                        config,
                    )
                )
                appended = True
        if not appended:
            parts.append("（相关指南已纳入上方 [Ref-N] 可引用证据）\n")
    else:
        parts.append("指南文档补充说明：\n（当前无相关指南证据）\n")

    if guide_example_chunks:
        parts.append("指南算例补充说明：\n")
        appended = False
        for index, guide_example_chunk in enumerate(guide_example_chunks, 1):
            if guide_example_chunk.chunk_id not in citable_ids:
                parts.append(
                    _format_prompt_chunk_block(
                        guide_example_chunk,
                        f"[GuideExampleContext-{index}]",
                        config,
                    )
                )
                appended = True
        if not appended:
            parts.append("（相关算例已纳入上方 [Ref-N] 可引用证据）\n")
    else:
        parts.append("指南算例补充说明：\n（当前无相关指南算例证据）\n")

    return "\n".join(parts)






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
        "返回严格 json，不要输出额外文字。\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


async def _call_source_translation_llm(
    prompt: str,
    config: ServerConfig | None = None,
) -> str:
    """调用 LLM 生成 source 中文翻译。"""
    cfg = config or ServerConfig()
    api_key = cfg.translation_llm_api_key or cfg.llm_api_key
    base_url = cfg.translation_llm_base_url or cfg.llm_base_url
    model = cfg.translation_llm_model or cfg.llm_model
    client = await get_async_openai_client(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(timeout=30.0, connect=5.0),
        client_factory=_current_async_openai_factory(),
    )
    response = await client.chat.completions.create(
        model=model,
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

    from server.core import generation as generation_package

    translator = getattr(
        generation_package,
        "_call_source_translation_llm",
        _call_source_translation_llm,
    )
    raw = await translator(prompt, config)
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
        translation_map = await _translate_source_batch(
            sources, pending_indexes, config
        )
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








async def generate_answer_stream(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
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
    chunks, scores = _dedupe_chunks_and_scores(chunks, scores)
    parent_chunks = _dedupe_chunks_by_id(parent_chunks)
    ref_chunks = _dedupe_chunks_by_id(ref_chunks)
    guide_chunks = _dedupe_chunks_by_id(guide_chunks)
    guide_example_chunks = _dedupe_chunks_by_id(guide_example_chunks)
    qt_normalized = _normalize_question_type(question_type)
    ctx_normalized = _normalize_engineering_context(engineering_context)
    generation_mode = decide_generation_mode(groundedness)
    prepare_started = time.perf_counter()
    prompt_started = time.perf_counter()
    prompt = build_prompt(
        question,
        chunks,
        parent_chunks,
        glossary_terms,
        conversation_history,
        ref_chunks=ref_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        intent_label=intent_label,
        config=cfg,
    )
    prompt_duration_ms = (time.perf_counter() - prompt_started) * 1000
    system_prompt_started = time.perf_counter()
    system_prompt = _build_stream_mode_system_prompt(
        generation_mode,
        qt_normalized,
        ctx_normalized,
        intent_label=intent_label,
    )
    system_prompt_duration_ms = (time.perf_counter() - system_prompt_started) * 1000

    client_started = time.perf_counter()
    client = await get_async_openai_client(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        timeout=httpx.Timeout(timeout=600.0),
        client_factory=_current_async_openai_factory(),
    )
    client_duration_ms = (time.perf_counter() - client_started) * 1000
    token_count_started = time.perf_counter()
    prompt_tokens, prompt_tokens_estimate = _count_tokens(prompt, cfg)
    token_count_duration_ms = (time.perf_counter() - token_count_started) * 1000
    prepare_duration_ms = (time.perf_counter() - prepare_started) * 1000
    record_spot_check(
        "final_prompt_tokens",
        {
            "value": prompt_tokens,
            "is_estimate": prompt_tokens_estimate,
            "model": cfg.llm_model,
        },
    )
    logger.info(
        "llm_stream_prepare_timing",
        duration_ms=round(prepare_duration_ms, 2),
        prompt_build_ms=round(prompt_duration_ms, 2),
        system_prompt_build_ms=round(system_prompt_duration_ms, 2),
        client_ready_ms=round(client_duration_ms, 2),
        token_count_ms=round(token_count_duration_ms, 2),
        prompt_len=len(prompt),
        system_prompt_len=len(system_prompt),
        prompt_tokens=prompt_tokens,
        prompt_tokens_estimate=prompt_tokens_estimate,
        chunks=len(chunks),
        parent_chunks=len(parent_chunks),
        ref_chunks=len(ref_chunks or []),
        guide_chunks=len(guide_chunks or []),
        guide_example_chunks=len(guide_example_chunks or []),
        question_type=qt_normalized,
        generation_mode=generation_mode,
    )
    try:
        logger.info(
            "llm_stream_start model=%s max_tokens=%d prompt_len=%d prompt_tokens=%d "
            "prompt_tokens_estimate=%s question_type=%s",
            cfg.llm_model,
            8192,
            len(prompt),
            prompt_tokens,
            prompt_tokens_estimate,
            qt_normalized,
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
            if not getattr(token, "choices", None):
                continue

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
            chunk_count,
            total_content_len,
            finish_reason,
        )

        # 从检索结果直接构建结构化元数据，不依赖 LLM 输出
        # 主 chunk、父片段、交叉引用和 guide/example chunk 统一编号，
        # 与 prompt 中的 [Ref-N] 一一对应。
        all_citable = (
            list(chunks)
            + list(parent_chunks)
            + list(ref_chunks or [])
            + list(guide_chunks or [])
            + list(guide_example_chunks or [])
        )
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
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
        confidence = _infer_answer_confidence(
            scores,
            has_sources=bool(sources),
            groundedness=groundedness,
        )
        retrieval_context = _build_retrieval_context(
            chunks,
            parent_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            ref_chunks=ref_chunks,
            scores=scores,
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
            config=cfg,
        )
        yield (
            "done",
            {
                "sources": [s.model_dump() for s in sources],
                "related_refs": related_refs,
                "confidence": confidence.value,
                "retrieval_context": retrieval_context.model_dump(),
                "question_type": qt_normalized,
                "engineering_context": ctx_normalized.model_dump()
                if ctx_normalized
                else None,
            },
        )
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
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
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
    chunks, scores = _dedupe_chunks_and_scores(chunks, scores)
    parent_chunks = _dedupe_chunks_by_id(parent_chunks)
    ref_chunks = _dedupe_chunks_by_id(ref_chunks)
    guide_chunks = _dedupe_chunks_by_id(guide_chunks)
    guide_example_chunks = _dedupe_chunks_by_id(guide_example_chunks)
    retrieval_context = _build_retrieval_context(
        chunks,
        parent_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        ref_chunks=ref_chunks,
        scores=scores,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        config=cfg,
    )
    qt_normalized = _normalize_question_type(question_type)
    ctx_normalized = _normalize_engineering_context(engineering_context)
    generation_mode = decide_generation_mode(groundedness)
    prompt = build_prompt(
        question,
        chunks,
        parent_chunks,
        glossary_terms,
        conversation_history,
        ref_chunks=ref_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        intent_label=intent_label,
        config=cfg,
    )

    client = await get_async_openai_client(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        client_factory=_current_async_openai_factory(),
    )
    prompt_tokens, prompt_tokens_estimate = _count_tokens(prompt, cfg)
    record_spot_check(
        "final_prompt_tokens",
        {
            "value": prompt_tokens,
            "is_estimate": prompt_tokens_estimate,
            "model": cfg.llm_model,
        },
    )
    try:
        logger.info(
            "llm_call_start model=%s max_tokens=%d prompt_len=%d prompt_tokens=%d "
            "prompt_tokens_estimate=%s",
            cfg.llm_model,
            8192,
            len(prompt),
            prompt_tokens,
            prompt_tokens_estimate,
        )
        resp = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": _build_json_system_prompt(
                        generation_mode,
                        question_type=qt_normalized,
                        engineering_context=ctx_normalized,
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
        all_citable = (
            list(chunks)
            + list(parent_chunks)
            + list(ref_chunks or [])
            + list(guide_chunks or [])
            + list(guide_example_chunks or [])
        )
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
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
        # Citation 后处理：归一化格式变体、剔除越界编号、句内去重
        normalized_answer = postprocess_citations(
            response.answer, len(canonical_sources)
        )
        confidence = _infer_answer_confidence(
            scores,
            has_sources=bool(canonical_sources),
            groundedness=groundedness,
        )
        return response.model_copy(
            update={
                "answer": normalized_answer,
                "sources": canonical_sources,
                "confidence": confidence,
                "retrieval_context": retrieval_context,
                "question_type": qt_normalized,
                "engineering_context": (
                    ctx_normalized.model_dump() if ctx_normalized else None
                ),
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
            question_type=qt_normalized,
            engineering_context=ctx_normalized.model_dump() if ctx_normalized else None,
        )
