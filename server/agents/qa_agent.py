from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from agents import Agent, ModelSettings, RawResponsesStreamEvent, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.stream_events import RunItemStreamEvent
import httpx
from openai import AsyncOpenAI

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tools.search import lookup_object, search
from server.config import ServerConfig
from shared.spot_check import merge_spot_check_usage

logger = structlog.get_logger(__name__)

_QA_AGENT_INSTRUCTIONS = """你是 Eurocode（EN 199x 系列）结构设计规范的中文问答专家。

系统通常已经为你预检索了相关证据，证据会以【预检索证据】给出，并由后端分配稳定的 [Ref-N] 编号。
如果同时提供【回答大纲】，它是基于同一批证据生成的结构规划。

## 工作方式
- 先阅读【预检索证据】与【回答大纲】，再组织最终回答。
- 用中文回答，按大纲 sections 顺序展开；每段先给结论，再展开依据、公式或推导。
- 面向甲方汇报/技术说明场景，回答不要过短；在已有 [Ref-N] 证据覆盖的范围内，适当展开条款含义、适用条件、计算路径、工程注意点和边界例外，让答案更完整、更可交付。
- 扩充只能围绕已经出现的引用证据展开；证据中出现相关条款、表格、公式、限制或例外时，即使大纲没有逐项列出，也可以纳入对应段落说明，但必须贴近这些 [Ref-N]。
- 只能引用已出现的 [Ref-N] 证据编号；不要自造引用编号。
- 公式用 LaTeX。
- 计算类问题必须给出计算步骤，并对照大纲中的 calculation_steps 展开。
- 收尾前对照大纲 self_check 自检；不要输出自检过程，只输出最终答案。
- 如果证据不足以完整回答，明确说明缺失部分，不要编造规范内容，也不要把片段算例包装成通用完整流程；若缺口具体且可定位，优先用工具补证后再回答。
- 直接输出最终答案；不要输出分析过程、思考步骤、草稿、回答结构规划或“我需要...”这类内部说明。

## 按问题类型组织回答
- 定义类问题：给出参数-符号-含义-关系表格，再补必要说明。
- 关系类问题：覆盖参数之间的协同变化，尤其是本构关系（应力-应变 σ-ε）以及设计参数随强度的折减；具体折减系数与取值规则必须来自检索到的 [Ref-N] 证据，不要凭记忆给出数值；证据没有时明确说明该关系缺少证据。
- 计算类问题：必须给出可复现的数值算例，结构为给定输入 → 分步代入公式 → 数值结果；不要只给泛泛的计算步骤。

## 工具（仅用于纠正性补证）
- search(query, top_k=8): 仅当预检索证据与大纲暴露出具体缺口时使用。
- lookup_object(label, top_k=3): 精确查找 Table/Figure/Expression/Annex/Clause。

## 限制
- 证据充足时直接回答，不调工具。
- 不做泛化检索；常规补检索已经由前置小模型闭环完成。
- 不要输出 JSON、action 字段或路由指令；只输出最终自然语言答案。
"""

_CITATION_RE = re.compile(r"\[Ref-\d+\]")


class EuroQAChatCompletionsModel(OpenAIChatCompletionsModel):
    """Chat Completions model with provider-specific compatibility fixes."""

    def __init__(
        self,
        *args: Any,
        drop_empty_tool_call_messages: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._drop_empty_tool_call_messages = drop_empty_tool_call_messages

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        if not self._drop_empty_tool_call_messages:
            return await super()._fetch_response(*args, **kwargs)

        args_list = list(args)
        if len(args_list) >= 2:
            args_list[1] = _drop_empty_messages_between_tool_call_and_output(
                args_list[1]
            )
            args = tuple(args_list)
        elif "input" in kwargs:
            kwargs["input"] = _drop_empty_messages_between_tool_call_and_output(
                kwargs["input"]
            )
        return await super()._fetch_response(*args, **kwargs)


@dataclass(frozen=True)
class AgentStreamEvent:
    """User-facing summary of one internal agent streaming event."""

    kind: Literal[
        "thinking",
        "tool_calling",
        "tool_result",
        "commentary",
        "answer_delta",
    ]
    tool_name: str | None = None
    tool_args: dict[str, object] | None = None
    tool_result: str | None = None
    tool_trace: dict[str, object] | None = None
    summary: str = ""


def _aggregate_streamed_usage(result: object) -> dict[str, int] | None:
    """Sum usage across all raw_responses from a streamed run."""
    raw_responses = getattr(result, "raw_responses", None)
    if not raw_responses:
        return None
    totals: dict[str, int] = {}
    for resp in raw_responses:
        usage = getattr(resp, "usage", None)
        if usage is None:
            continue
        for key in (
            "requests",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            val = getattr(usage, key, 0) or 0
            if val:
                totals[key] = totals.get(key, 0) + int(val)
        cached = getattr(
            getattr(usage, "input_tokens_details", None), "cached_tokens", 0
        ) or 0
        if cached:
            totals["cached_tokens"] = totals.get("cached_tokens", 0) + int(cached)
        reasoning = getattr(
            getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0
        ) or 0
        if reasoning:
            totals["reasoning_tokens"] = totals.get("reasoning_tokens", 0) + int(reasoning)
    return totals or None


def _uses_deepseek_agent_endpoint(config: ServerConfig) -> bool:
    model = config.resolved_agent_llm_model.lower()
    base_url = config.resolved_agent_llm_base_url.lower()
    return "deepseek" in model or "api.deepseek.com" in base_url


def _agent_model_extra_body(config: ServerConfig) -> dict[str, object]:
    if _uses_deepseek_agent_endpoint(config):
        return {"thinking": {"type": "disabled"}}
    return {"enable_thinking": config.llm_enable_thinking}


def _drop_empty_messages_between_tool_call_and_output(input_items: object) -> object:
    if not isinstance(input_items, list):
        return input_items

    filtered: list[object] = []
    for index, item in enumerate(input_items):
        if (
            _is_empty_assistant_message(item)
            and filtered
            and _item_type(filtered[-1]) == "function_call"
            and _next_item_type(input_items, index) == "function_call_output"
        ):
            continue
        filtered.append(item)
    return filtered


def _next_item_type(items: list[object], index: int) -> str:
    if index + 1 >= len(items):
        return ""
    return _item_type(items[index + 1])


def _item_type(item: object) -> str:
    item_type = _item_value(item, "type")
    return str(item_type) if item_type else ""


def _item_value(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _is_empty_assistant_message(item: object) -> bool:
    if _item_type(item) != "message" or _item_value(item, "role") != "assistant":
        return False
    content = _item_value(item, "content")
    if isinstance(content, str):
        return content == ""
    if isinstance(content, list):
        return all(_content_part_is_empty_text(part) for part in content)
    return content is None


def _content_part_is_empty_text(part: object) -> bool:
    part_type = _item_value(part, "type")
    if part_type not in {"output_text", "refusal"}:
        return False
    key = "refusal" if part_type == "refusal" else "text"
    value = _item_value(part, key)
    return isinstance(value, str) and value == ""


def build_qa_agent(config: ServerConfig) -> Agent[QADeps]:
    client = AsyncOpenAI(
        api_key=config.resolved_agent_llm_api_key,
        base_url=config.resolved_agent_llm_base_url,
        timeout=httpx.Timeout(config.agent_llm_timeout_seconds, connect=10.0),
    )
    model = EuroQAChatCompletionsModel(
        model=config.resolved_agent_llm_model,
        openai_client=client,
        drop_empty_tool_call_messages=_uses_deepseek_agent_endpoint(config),
    )
    return Agent[QADeps](
        name="eurocode-qa",
        model=model,
        tools=[
            search,
            lookup_object,
        ],
        model_settings=ModelSettings(
            temperature=0.1,
            extra_body=_agent_model_extra_body(config),
        ),
        instructions=_QA_AGENT_INSTRUCTIONS,
    )


async def run_qa_agent(
    agent: Agent[QADeps],
    question: str,
    deps: QADeps,
    max_turns: int = 5,
) -> tuple[str, EvidenceBundle, dict[str, int] | None]:
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
    usage = _aggregate_streamed_usage(result)
    if usage is not None:
        merge_spot_check_usage(usage)
    return str(result.final_output or ""), deps.bundle, usage


async def run_qa_agent_streamed(
    agent: Agent[QADeps],
    question: str,
    deps: QADeps,
    max_turns: int = 5,
) -> AsyncIterator[
    AgentStreamEvent | tuple[str, EvidenceBundle, dict[str, int] | None]
]:
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
            delta = _raw_response_text_delta(event)
            if delta:
                yield AgentStreamEvent(
                    kind="answer_delta",
                    summary=delta,
                )
                continue
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
    usage = _aggregate_streamed_usage(result)
    if usage is not None:
        merge_spot_check_usage(usage)
    yield (final_output or _fallback_agent_reply(deps), deps.bundle, usage)


def _build_input_items(question: str, deps: QADeps) -> list[dict[str, str]]:
    input_items: list[dict[str, str]] = []
    if deps.conversation_state is not None:
        for turn in deps.conversation_state.history:
            previous_question = turn.get("question", "")
            previous_answer = turn.get("answer", "")
            if previous_question:
                input_items.append({"role": "user", "content": previous_question})
            if previous_answer:
                cleaned = _CITATION_RE.sub("", previous_answer).strip()
                input_items.append({"role": "assistant", "content": cleaned})
    input_items.append({"role": "user", "content": question})
    if deps.bundle.has_rag_evidence:
        evidence_text = _format_evidence_context(
            deps.bundle,
            max_chars=deps.config.agent_evidence_max_chars,
        )
        input_items.append(
            {
                "role": "user",
                "content": f"【预检索证据】\n{evidence_text}",
            }
        )
    if deps.bundle.outline:
        input_items.append(
            {
                "role": "user",
                "content": (
                    "【回答大纲】\n"
                    f"{json.dumps(deps.bundle.outline, ensure_ascii=False)}"
                ),
            }
        )
    return input_items



def _fallback_agent_reply(deps: QADeps) -> str:
    if deps.bundle.has_rag_evidence:
        return "已检索到相关规范证据，正在整理回答。"
    return "抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。"


def _raw_response_text_delta(event: RawResponsesStreamEvent) -> str:
    data = getattr(event, "data", None)
    if isinstance(data, Mapping):
        event_type = str(data.get("type") or "")
    else:
        event_type = str(getattr(data, "type", "") or "")
    if event_type != "response.output_text.delta":
        return ""
    for attr in ("delta", "text"):
        value = getattr(data, attr, None)
        if isinstance(value, str) and value:
            return value
    if isinstance(data, Mapping):
        value = data.get("delta") or data.get("text")
        if isinstance(value, str):
            return value
    return ""


def _format_evidence_context(
    bundle: EvidenceBundle,
    max_chars: int | None = None,
) -> str:
    chunks = bundle.citable_chunks()
    bundle.ensure_ref_ids(chunks)
    if not chunks:
        return "（当前没有可引用证据）"
    blocks: list[str] = []
    total_chars = 0
    for chunk in chunks:
        ref = bundle.ref_label_for(chunk)
        meta = chunk.metadata
        section = " > ".join(meta.section_path) if meta.section_path else "unknown"
        page = ", ".join(map(str, meta.page_numbers)) if meta.page_numbers else "unknown"
        object_label = f" | {meta.object_label}" if meta.object_label else ""
        block = (
            f"[{ref}] {meta.source} | {section} | p.{page}{object_label}"
            f"\n\n{chunk.content}"
        )
        if max_chars is not None and blocks and total_chars + len(block) > max_chars:
            break
        blocks.append(block)
        total_chars += len(block)
    return "\n\n".join(blocks)


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
    if tool_name == "search":
        query = _argument_value(arguments, "query")
        if query:
            return f"正在搜索规范知识库：「{query[:50]}」..."
        return "正在搜索规范知识库..."
    if tool_name == "lookup_object":
        label = _argument_value(arguments, "label")
        if label:
            return f"正在精确查找规范对象：「{label[:50]}」..."
        return "正在精确查找规范对象..."
    if tool_name:
        return f"正在调用 {tool_name}..."
    return "正在调用工具..."


def _tool_result_summary(tool_name: str | None, output: str) -> str:
    first_line = output.splitlines()[0].strip() if output else ""
    if tool_name == "search":
        if first_line:
            return first_line[:120]
        return "规范检索完成。"
    if tool_name == "lookup_object":
        if first_line:
            return first_line[:120]
        return "规范对象查找完成。"
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
