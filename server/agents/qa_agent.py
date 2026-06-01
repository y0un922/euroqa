from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Literal

from agents import Agent, ModelSettings, RawResponsesStreamEvent, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.stream_events import RunItemStreamEvent
from openai import AsyncOpenAI

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tools.lookup_glossary import lookup_glossary
from server.agents.tools.retrieve import retrieve
from server.config import ServerConfig

_QA_AGENT_INSTRUCTIONS = """你是欧洲结构设计规范（Eurocode, EN 199x 系列）的专家问答助手。

## 工具
- retrieve(query, top_k=8): 搜索规范知识库。传入检索查询，系统自动进行查询扩展和混合检索。top_k 控制返回给回答生成的证据数量，允许范围 3-12。
- lookup_glossary(term): 查询术语表。传入术语，返回翻译和定义。

## 行为准则
- 用户问 Eurocode、EN 199x、结构设计规范、承载力、荷载组合、材料分项系数、构造限值等规范相关问题时，必须调用 retrieve 搜索证据。
- 用户寒暄、闲聊、或问与规范无关的问题时，直接自然语言回复，不调用工具。
- 用户追问且当前对话历史已经足够回答时，可以直接回复。
- 用户追问但需要新的规范证据、其他条文、表格、公式或参数时，再次调用 retrieve。
- 问题过于模糊且无法形成有效检索查询时，直接礼貌反问，请用户补充规范号、构件类型、参数名称或设计场景。
- retrieve 返回 0 条结果时，可以换查询角度重试 1 次；仍为 0 则直接告知暂未找到相关条文，并请用户补充信息。
- retrieve 已返回 groundedness=grounded 的结果时，不要再次调用 retrieve。已有证据充足，直接简要说明找到了什么即可。
- 对一个问题，最多调用 retrieve 2 次。不要为了"换角度多查"而反复检索。
- 根据问题复杂度设置 top_k：简单定义或单个参数问题用 4-6；一般规范解释用 6-8；复杂综合总结、对比或多要点问题用 8-12。不要超过 12。
- 调用 retrieve 时，query 必须是自包含的完整问题，不得包含代词或省略关键语境。如果用户当前问题包含代词（它、这个、该参数、上面的表格等）或省略了文档名/条款号，你必须在 query 中用明确的名词替代。例如：上文是关于保护层厚度的，用户问"它的限值是多少"，你应调用 retrieve("混凝土保护层厚度的限值")，而不是 retrieve("它的限值是多少")。

## 重要原则
- 不要编造规范内容
- 优先检索，但 retrieve 返回 grounded 结果后立即停止检索
- 如果调用 retrieve 且找到了相关证据，简要说明找到了什么即可；系统会基于证据生成详细回答。
- 如果没有调用 retrieve，你的回复就是最终回答，请直接、清晰地回复用户。
- 不要输出 JSON、action 字段或路由指令；只用自然语言回复。

## 常见错误（禁止）
- ❌ 用户问"EN 1992-1-1 表 2.1N 的材料分项系数是什么？" → 不调用 retrieve 直接回答。
- ❌ retrieve 返回 0 条 → 编造条文编号或参数值。
- ❌ 输出 {"action": "retrieve"} 或 {"action": "compose_rag"}。
"""

_CITATION_RE = re.compile(r"\[Ref-\d+\]")


@dataclass(frozen=True)
class AgentStreamEvent:
    """User-facing summary of one internal agent streaming event."""

    kind: Literal["thinking", "tool_calling", "tool_result", "commentary"]
    tool_name: str | None = None
    tool_args: dict[str, object] | None = None
    tool_result: str | None = None
    tool_trace: dict[str, object] | None = None
    summary: str = ""


def build_qa_agent(config: ServerConfig) -> Agent[QADeps]:
    client = AsyncOpenAI(
        api_key=config.resolved_agent_llm_api_key,
        base_url=config.resolved_agent_llm_base_url,
    )
    model = OpenAIChatCompletionsModel(
        model=config.resolved_agent_llm_model,
        openai_client=client,
    )
    return Agent[QADeps](
        name="eurocode-qa",
        model=model,
        tools=[retrieve, lookup_glossary],
        model_settings=ModelSettings(temperature=0.1),
        instructions=_QA_AGENT_INSTRUCTIONS,
    )


async def run_qa_agent(
    agent: Agent[QADeps],
    question: str,
    deps: QADeps,
    max_turns: int = 5,
) -> tuple[str, EvidenceBundle]:
    input_items = _build_input_items(question, deps)

    def on_max_turns(_handler_input: object) -> str:
        return _fallback_agent_reply(deps)

    result = await Runner.run(
        agent,
        input_items,
        context=deps,
        max_turns=max_turns,
        error_handlers={"max_turns": on_max_turns},
    )
    return str(result.final_output or ""), deps.bundle


async def run_qa_agent_streamed(
    agent: Agent[QADeps],
    question: str,
    deps: QADeps,
    max_turns: int = 5,
) -> AsyncIterator[AgentStreamEvent | tuple[str, EvidenceBundle]]:
    """Run the QA agent and yield internal progress events before final output."""
    input_items = _build_input_items(question, deps)

    def on_max_turns(_handler_input: object) -> str:
        return _fallback_agent_reply(deps)

    result = Runner.run_streamed(
        agent,
        input_items,
        context=deps,
        max_turns=max_turns,
        error_handlers={"max_turns": on_max_turns},
    )

    thinking_emitted = False
    tool_names_by_call_id: dict[str, str] = {}
    tool_args_by_call_id: dict[str, dict[str, object]] = {}
    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            if not thinking_emitted:
                thinking_emitted = True
                yield AgentStreamEvent(
                    kind="thinking",
                    summary="Agent 正在推理...",
                )
            continue

        if not isinstance(event, RunItemStreamEvent):
            continue

        item_type = getattr(event.item, "type", "")
        if event.name == "tool_called" or item_type == "tool_call_item":
            tool_name = _tool_name(event.item)
            call_id = _tool_call_id(event.item)
            if call_id and tool_name:
                tool_names_by_call_id[call_id] = tool_name
            arguments = _tool_arguments(event.item)
            tool_args = {"call_id": call_id, "arguments": arguments}
            if call_id:
                tool_args_by_call_id[call_id] = tool_args
            yield AgentStreamEvent(
                kind="tool_calling",
                tool_name=tool_name,
                tool_args=tool_args,
                summary=_tool_calling_summary(tool_name, arguments),
            )
            thinking_emitted = False
            continue

        if event.name == "tool_output" or item_type == "tool_call_output_item":
            call_id = _tool_call_id(event.item)
            tool_name = _tool_name(event.item) or tool_names_by_call_id.get(
                call_id or ""
            )
            output_text = str(getattr(event.item, "output", "") or "")
            yield AgentStreamEvent(
                kind="tool_result",
                tool_name=tool_name,
                tool_args=tool_args_by_call_id.get(call_id or ""),
                tool_result=output_text,
                tool_trace=_latest_tool_trace(deps.bundle.tool_trace, tool_name),
                summary=_tool_result_summary(tool_name, output_text),
            )

    final_output = str(result.final_output or "")
    yield (final_output or _fallback_agent_reply(deps), deps.bundle)


def _build_input_items(question: str, deps: QADeps) -> list[dict[str, str]]:
    input_items: list[dict[str, str]] = []
    if deps.conversation_state is not None:
        rounds = deps.conversation_state.history[-deps.config.max_conversation_rounds :]
        for turn in rounds:
            previous_question = turn.get("question", "")
            previous_answer = turn.get("answer", "")
            if previous_question:
                input_items.append({"role": "user", "content": previous_question})
            if previous_answer:
                compressed = _compress_answer_for_agent(previous_answer)
                input_items.append({"role": "assistant", "content": compressed})
    input_items.append({"role": "user", "content": question})
    return input_items


def _compress_answer_for_agent(answer: str, limit: int = 200) -> str:
    """Strip citation markers and truncate previous answers for agent context."""
    cleaned = _CITATION_RE.sub("", answer).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _fallback_agent_reply(deps: QADeps) -> str:
    if deps.bundle.has_rag_evidence:
        return "已检索到相关规范证据，正在整理回答。"
    return "抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。"


def _raw_item_payload(item: object) -> object:
    raw_item = getattr(item, "raw_item", None)
    if isinstance(raw_item, Mapping):
        return raw_item
    if hasattr(raw_item, "model_dump"):
        return raw_item.model_dump(exclude_unset=True)
    return raw_item


def _payload_value(payload: object, key: str) -> object:
    if isinstance(payload, Mapping):
        return payload.get(key)
    return getattr(payload, key, None)


def _tool_name(item: object) -> str | None:
    tool_name = getattr(item, "tool_name", None)
    if tool_name:
        return str(tool_name)
    payload = _raw_item_payload(item)
    candidate = _payload_value(payload, "name") or _payload_value(payload, "tool_name")
    return str(candidate) if candidate else None


def _tool_call_id(item: object) -> str | None:
    call_id = getattr(item, "call_id", None)
    if call_id:
        return str(call_id)
    payload = _raw_item_payload(item)
    candidate = _payload_value(payload, "call_id") or _payload_value(payload, "id")
    return str(candidate) if candidate else None


def _tool_arguments(item: object) -> str:
    payload = _raw_item_payload(item)
    candidate = (
        _payload_value(payload, "arguments")
        or _payload_value(payload, "params")
        or _payload_value(payload, "input")
    )
    if candidate is None:
        return ""
    if isinstance(candidate, str):
        return candidate
    return json.dumps(candidate, ensure_ascii=False)


def _tool_calling_summary(tool_name: str | None, arguments: str) -> str:
    if tool_name == "retrieve":
        query = _argument_value(arguments, "query")
        if query:
            return f"正在搜索规范知识库：「{query[:50]}」..."
        return "正在搜索规范知识库..."
    if tool_name == "lookup_glossary":
        term = _argument_value(arguments, "term")
        if term:
            return f"正在查询术语：「{term[:50]}」..."
        return "正在查询术语表..."
    if tool_name:
        return f"正在调用 {tool_name}..."
    return "正在调用工具..."


def _tool_result_summary(tool_name: str | None, output: str) -> str:
    first_line = output.splitlines()[0].strip() if output else ""
    if tool_name == "retrieve":
        if first_line:
            return first_line[:120]
        return "规范检索完成。"
    if tool_name == "lookup_glossary":
        if first_line:
            return first_line[:120]
        return "术语查询完成。"
    return "工具执行完成。"


def _argument_value(arguments: str, key: str) -> str:
    if not arguments:
        return ""
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError:
        return ""
    value = payload.get(key) if isinstance(payload, dict) else None
    return str(value) if value else ""


def _latest_tool_trace(
    tool_trace: list[dict],
    tool_name: str | None,
) -> dict[str, object] | None:
    for entry in reversed(tool_trace):
        if tool_name is None or entry.get("tool") == tool_name:
            return dict(entry)
    return None
