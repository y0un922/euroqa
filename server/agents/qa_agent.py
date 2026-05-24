from __future__ import annotations

from typing import Literal

from agents import Agent, ModelSettings, Runner, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from pydantic import BaseModel

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tools.lookup_glossary import lookup_glossary
from server.agents.tools.retrieve import retrieve
from server.config import ServerConfig

_QA_AGENT_INSTRUCTIONS = """你是欧洲结构设计规范（Eurocode, EN 199x 系列）的专家问答助手。

根据用户问题决定响应策略：

## 工具
- retrieve(query): 搜索规范知识库。传入检索查询，系统自动进行查询扩展和混合检索。返回匹配的规范片段摘要。
- lookup_glossary(term): 查询术语表。传入术语，返回翻译和定义。

## 决策规则

### action = "chat"
适用于闲聊、寒暄、与规范无关的问题、或上下文追问且历史中已有足够信息。
不调用工具，在 direct_reply 中直接回复。

### action = "clarify"
适用于问题过于模糊（缺规范号、缺参数、缺构件类型）。
不调用工具，在 direct_reply 中礼貌反问。

### action = "compose_rag"
适用于明确的规范相关问题。先调用 retrieve 收集证据，确认检索到相关内容后设置此 action。
direct_reply 留空（系统会用检索证据生成详细回答）。
检索不理想可换角度重试（最多 2-3 次）。

## 重要原则
- 不要编造规范内容
- 检索不到就坦率告知
- 优先检索，不确定时宁可多查一次
"""


class AgentDecision(BaseModel):
    action: Literal["compose_rag", "chat", "clarify"]
    direct_reply: str | None = None


def build_qa_agent(config: ServerConfig) -> Agent[QADeps]:
    set_tracing_disabled(disabled=True)
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
        output_type=AgentDecision,
        tools=[retrieve, lookup_glossary],
        model_settings=ModelSettings(temperature=0.1),
        instructions=_QA_AGENT_INSTRUCTIONS,
    )


async def run_qa_agent(
    agent: Agent[QADeps],
    question: str,
    deps: QADeps,
    max_turns: int = 5,
) -> tuple[AgentDecision, EvidenceBundle]:
    input_items = _build_input_items(question, deps)

    def on_max_turns(_handler_input: object) -> AgentDecision:
        if not deps.bundle.is_empty:
            return AgentDecision(action="compose_rag")
        return AgentDecision(
            action="chat",
            direct_reply="抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。",
        )

    result = await Runner.run(
        agent,
        input_items,
        context=deps,
        max_turns=max_turns,
        error_handlers={"max_turns": on_max_turns},
    )
    return result.final_output, deps.bundle


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
                input_items.append({"role": "assistant", "content": previous_answer})
    input_items.append({"role": "user", "content": question})
    return input_items
