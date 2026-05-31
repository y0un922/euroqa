from __future__ import annotations

from agents import Agent, ModelSettings, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tools.lookup_glossary import lookup_glossary
from server.agents.tools.retrieve import retrieve
from server.config import ServerConfig

_QA_AGENT_INSTRUCTIONS = """你是欧洲结构设计规范（Eurocode, EN 199x 系列）的专家问答助手。

## 工具
- retrieve(query): 搜索规范知识库。传入检索查询，系统自动进行查询扩展和混合检索。返回匹配的规范片段摘要。
- lookup_glossary(term): 查询术语表。传入术语，返回翻译和定义。

## 行为准则
- 用户问 Eurocode、EN 199x、结构设计规范、承载力、荷载组合、材料分项系数、构造限值等规范相关问题时，必须调用 retrieve 搜索证据。
- 用户寒暄、闲聊、或问与规范无关的问题时，直接自然语言回复，不调用工具。
- 用户追问且当前对话历史已经足够回答时，可以直接回复。
- 用户追问但需要新的规范证据、其他条文、表格、公式或参数时，再次调用 retrieve。
- 问题过于模糊且无法形成有效检索查询时，直接礼貌反问，请用户补充规范号、构件类型、参数名称或设计场景。
- retrieve 返回 0 条结果时，可以换查询角度重试 1-2 次；仍为 0 则直接告知暂未找到相关条文，并请用户补充信息。

## 重要原则
- 不要编造规范内容
- 优先检索，不确定时宁可多查一次
- 如果调用 retrieve 且找到了相关证据，简要说明找到了什么即可；系统会基于证据生成详细回答。
- 如果没有调用 retrieve，你的回复就是最终回答，请直接、清晰地回复用户。
- 不要输出 JSON、action 字段或路由指令；只用自然语言回复。

## 常见错误（禁止）
- ❌ 用户问"EN 1992-1-1 表 2.1N 的材料分项系数是什么？" → 不调用 retrieve 直接回答。
- ❌ retrieve 返回 0 条 → 编造条文编号或参数值。
- ❌ 输出 {"action": "retrieve"} 或 {"action": "compose_rag"}。
"""


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
        if deps.bundle.has_rag_evidence:
            return "已检索到相关规范证据，正在整理回答。"
        return "抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。"

    result = await Runner.run(
        agent,
        input_items,
        context=deps,
        max_turns=max_turns,
        error_handlers={"max_turns": on_max_turns},
    )
    return str(result.final_output or ""), deps.bundle


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
