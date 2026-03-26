"""Generation layer: prompt assembly + LLM call + structured output parsing."""
from __future__ import annotations

import json

import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.models.schemas import Chunk, Confidence, QueryResponse, Source

logger = structlog.get_logger()

# 系统提示词：指导 LLM 以 Eurocode 专家身份回答问题
_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，帮助中国工程师理解和查询规范内容。

规则：
1. 所有回答必须基于提供的规范原文，不要编造规范中不存在的内容。
2. 回答用中文，但保留原文中的关键术语（如条款编号、表格编号、公式编号）。
3. 必须标注出处（文件名、章节、页码、条款号）。
4. 对原文关键段落提供中文翻译。
5. 如果需要推理，说明推理过程。

输出格式：严格 JSON，结构如下：
{
  "answer": "中文回答",
  "sources": [{"file": "EN 1990:2002", "title": "...", "section": "...", "page": 28, "clause": "...", "original_text": "...", "translation": "..."}],
  "related_refs": ["相关的其他规范引用"],
  "confidence": "high|medium|low"
}"""


def build_prompt(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
) -> str:
    """将检索结果组装为发送给 LLM 的用户提示词。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段（已排序）
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录（多轮会话场景）

    Returns:
        组装完成的提示词字符串
    """
    parts: list[str] = []

    # 术语对照（帮助 LLM 理解中英对应关系）
    if glossary_terms:
        terms = ", ".join(f"{zh}={en}" for zh, en in glossary_terms.items())
        parts.append(f"相关术语对照：{terms}\n")

    # 主要检索片段
    parts.append("检索到的规范内容：\n")
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        page_str = ",".join(map(str, meta.page_numbers))
        section_str = " > ".join(meta.section_path)
        source_info = f"{meta.source}, Page {page_str}, {section_str}"
        parts.append(f"[{i}] {source_info}\n{chunk.content}\n")

    # 扩展上下文（截取前2000字符，避免过长）
    if parent_chunks:
        parts.append("\n扩展上下文（章节级）：\n")
        for pc in parent_chunks[:2]:
            section_str = " > ".join(pc.metadata.section_path)
            parts.append(f"[Parent] {section_str}\n{pc.content[:2000]}\n")

    # 历史对话（仅保留最近两轮，避免上下文膨胀）
    if conversation_history:
        parts.append("\n之前的对话：\n")
        for h in conversation_history[-2:]:
            parts.append(f"Q: {h['question']}\nA: {h['answer'][:500]}\n")

    parts.append(f"\n用户问题：{question}")
    return "\n".join(parts)


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
    cleaned = raw
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(cleaned)
        sources = [Source(**s) for s in data.get("sources", [])[:5]]
        return QueryResponse(
            answer=data.get("answer", ""),
            sources=sources,
            related_refs=data.get("related_refs", []),
            confidence=Confidence(data.get("confidence", "low")),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("llm_response_parse_failed", raw=raw[:200])
        return QueryResponse(
            answer=raw,
            sources=[],
            related_refs=[],
            confidence=Confidence.LOW,
        )


async def generate_answer(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
) -> QueryResponse:
    """调用 LLM 生成基于检索内容的回答。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录
        config: 服务器配置（为空时使用默认配置）

    Returns:
        结构化的 QueryResponse；LLM 调用失败时返回降级响应
    """
    cfg = config or ServerConfig()
    prompt = build_prompt(
        question, chunks, parent_chunks, glossary_terms, conversation_history
    )

    client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    try:
        resp = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        return parse_llm_response(raw)
    except Exception:
        logger.exception("llm_call_failed")
        return QueryResponse(
            answer="LLM 服务暂时不可用，以下是检索到的相关规范片段。",
            sources=[],
            confidence=Confidence.LOW,
            degraded=True,
        )
