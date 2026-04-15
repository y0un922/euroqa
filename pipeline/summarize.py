"""Stage 3.5: Generate natural language summaries for special element chunks.

Uses LLM to create embedding-friendly text for tables, formulas, and images.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

import structlog
from openai import AsyncOpenAI

from pipeline.config import PipelineConfig
from server.models.schemas import Chunk, ElementType

_client: AsyncOpenAI | None = None
logger = structlog.get_logger()
_SUMMARY_MAX_ATTEMPTS = 2


def _get_client(config: PipelineConfig | None = None) -> AsyncOpenAI:
    global _client
    if _client is None:
        cfg = config or PipelineConfig()
        _client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    return _client


async def _call_llm(
    prompt: str,
    config: PipelineConfig | None = None,
    max_tokens: int = 300,
) -> str:
    client = _get_client(config)
    cfg = config or PipelineConfig()
    resp = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _extract_table_headers(html: str) -> list[str]:
    """从 HTML 表格中提取表头文本（<th> 或第一行 <td>）。"""
    # 尝试提取 <th> 标签
    th_matches = re.findall(r"<th[^>]*>(.*?)</th>", html, re.DOTALL | re.IGNORECASE)
    if th_matches:
        return [re.sub(r"<[^>]+>", "", h).strip() for h in th_matches if h.strip()]

    # 如果没有 <th>，取第一行 <tr> 中的 <td>
    first_row = re.search(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    if first_row:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", first_row.group(1), re.DOTALL | re.IGNORECASE)
        return [re.sub(r"<[^>]+>", "", td).strip() for td in tds if td.strip()]
    return []


def _extract_first_column(html: str) -> list[str]:
    """从 HTML 表格中提取每行第一列的文本（行标签）。"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    labels: list[str] = []
    for row in rows[1:]:  # 跳过表头行
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
        if cells:
            text = re.sub(r"<[^>]+>", "", cells[0]).strip()
            if text:
                labels.append(text)
    return labels


def build_table_embedding_text(chunk: Chunk) -> str:
    """纯结构化提取生成表格 embedding 文本，不调用 LLM。

    比 LLM 摘要更精确：保留原始术语（如 εcu2、fck），
    零成本、零延迟、确定性可复现。
    """
    section_context = " > ".join(chunk.metadata.section_path)
    caption = chunk.metadata.object_label or ""
    headers = _extract_table_headers(chunk.content)
    row_labels = _extract_first_column(chunk.content)

    parts: list[str] = []
    if caption:
        parts.append(caption)
    if chunk.metadata.source:
        parts.append(f"Source: {chunk.metadata.source}")
    if headers:
        parts.append(f"Columns: {', '.join(headers[:20])}")
    if row_labels:
        parts.append(f"Rows: {', '.join(row_labels[:20])}")
    parts.append(f"Section: {section_context}")

    return "\n".join(parts)


async def generate_formula_description(chunk: Chunk, config: PipelineConfig | None = None) -> str:
    section_context = " > ".join(chunk.metadata.section_path)
    prompt = (
        f"以下是欧洲建筑规范 {chunk.metadata.source} 中 {section_context} 的一个公式。\n"
        f"请用简洁的中文描述公式的含义和用途（100字以内）。\n\n"
        f"公式内容：\n{chunk.content}"
    )
    return await _call_llm(prompt, config)


async def _generate_non_empty_summary(
    chunk: Chunk,
    generator: Callable[[Chunk, PipelineConfig | None], Awaitable[str]],
    config: PipelineConfig,
) -> str:
    """Generate a non-empty summary with one retry on failure or blank output."""
    last_error: Exception | None = None

    for attempt in range(1, _SUMMARY_MAX_ATTEMPTS + 1):
        try:
            summary = (await generator(chunk, config)).strip()
            if summary:
                return summary
            raise ValueError("LLM returned empty summary")
        except Exception as exc:
            last_error = exc
            logger.warning(
                "chunk_summary_attempt_failed",
                chunk_id=chunk.chunk_id,
                element_type=chunk.metadata.element_type.value,
                section_path=chunk.metadata.section_path,
                attempt=attempt,
                max_attempts=_SUMMARY_MAX_ATTEMPTS,
                error=str(exc),
            )

    assert last_error is not None
    raise last_error


async def enrich_chunk_summaries(
    chunks: list[Chunk],
    config: PipelineConfig | None = None,
    progress_callback: Callable[[dict], Awaitable[None] | None] | None = None,
) -> list[Chunk]:
    """Fill embedding_text for all special element chunks.

    使用受控并发调用 LLM，并发数由 config.llm_concurrency 控制。
    单个 chunk 失败不影响其他 chunk。
    """
    cfg = config or PipelineConfig()
    special_chunks = [
        chunk for chunk in chunks
        if chunk.metadata.element_type != ElementType.TEXT
    ]
    total = len(special_chunks)
    if total == 0:
        return chunks

    semaphore = asyncio.Semaphore(max(1, cfg.llm_concurrency))

    # 进度报告：用队列保证按完成顺序回调，不阻塞主流程
    progress_queue: asyncio.Queue[Chunk | None] | None = None
    reporter_task: asyncio.Task[None] | None = None

    async def _report_progress(queue: asyncio.Queue[Chunk | None]) -> None:
        """从队列消费已完成 chunk，按完成顺序触发进度回调。"""
        completed = 0
        while True:
            done_chunk = await queue.get()
            if done_chunk is None:
                return
            completed += 1
            if progress_callback is None:
                continue
            payload = {
                "completed": completed,
                "total": total,
                "chunk_id": done_chunk.chunk_id,
                "element_type": done_chunk.metadata.element_type.value,
                "section_path": done_chunk.metadata.section_path,
            }
            result = progress_callback(payload)
            if isinstance(result, Awaitable):
                await result

    async def _enrich_one(chunk: Chunk) -> None:
        """处理单个特殊元素 chunk（受信号量控制）。"""
        try:
            if chunk.metadata.element_type == ElementType.TABLE:
                # 表格：纯结构化提取，不调用 LLM
                chunk.embedding_text = build_table_embedding_text(chunk)
            elif chunk.metadata.element_type == ElementType.FORMULA:
                async with semaphore:
                    desc = await _generate_non_empty_summary(
                        chunk,
                        generate_formula_description,
                        cfg,
                    )
                chunk.embedding_text = (
                    f"{desc} Section: {' > '.join(chunk.metadata.section_path)}"
                )
            elif chunk.metadata.element_type == ElementType.IMAGE:
                # 图片暂不调用 LLM，后续接入 VLM
                chunk.embedding_text = (
                    f"{chunk.content} Section: {' > '.join(chunk.metadata.section_path)}"
                )
            else:
                return
        except Exception:
            logger.exception(
                "chunk_summary_failed",
                chunk_id=chunk.chunk_id,
                element_type=chunk.metadata.element_type.value,
                section_path=chunk.metadata.section_path,
            )
            return

        if progress_queue is not None:
            await progress_queue.put(chunk)

    # 启动进度报告协程
    if progress_callback is not None:
        progress_queue = asyncio.Queue()
        reporter_task = asyncio.create_task(_report_progress(progress_queue))

    # 并发处理所有特殊元素
    await asyncio.gather(*(_enrich_one(chunk) for chunk in special_chunks))

    # 关闭进度报告
    if progress_queue is not None and reporter_task is not None:
        await progress_queue.put(None)
        await reporter_task

    return chunks
