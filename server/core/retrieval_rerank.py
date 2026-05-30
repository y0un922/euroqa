"""Reranking helpers for hybrid retrieval."""

from __future__ import annotations

from typing import Any

from server.config import ServerConfig
from server.models.schemas import Chunk
from shared.spot_check import record_spot_check
from shared.tokenizers import count_for_rerank


def _current_count_for_rerank():
    """Resolve package-level tokenizer so legacy monkeypatch paths still work."""
    from server.core import retrieval as retrieval_module

    return getattr(retrieval_module, "count_for_rerank", count_for_rerank)


def _rerank_text(chunk: Chunk) -> str:
    """选择用于 reranker 的文本：table/formula 用 content 以保留完整数据。"""
    if chunk.metadata.element_type in ("table", "formula"):
        # 对于表格和公式，embedding_text 是压缩后的摘要，
        # 用原始 content 做重排序能保留具体数值，提高匹配精度。
        # 截断到 2000 字符避免超出 reranker 输入限制。
        text = chunk.content or ""
        if chunk.metadata.object_label:
            text = f"{chunk.metadata.object_label}\n{text}"
        return text[:2000]
    return chunk.embedding_text or chunk.content


async def _rerank(
    rerank_client: object,
    config: ServerConfig,
    query: str,
    chunks: list[Chunk],
    top_n: int,
) -> list[tuple[Chunk, float]]:
    """使用 FlagReranker 对候选 chunk 进行重排序，返回 top_n 结果。"""
    if not chunks:
        return []

    documents = [_rerank_text(c) for c in chunks]
    token_records: list[dict[str, Any]] = []
    truncation_records: list[dict[str, Any]] = []
    rerank_max_length = max(int(config.rerank_max_length), 1)
    count_tokens = _current_count_for_rerank()
    for chunk, document in zip(chunks, documents, strict=False):
        token_count, is_estimate = count_tokens(
            document,
            config.rerank_model,
        )
        truncated = token_count > rerank_max_length
        element_type = getattr(
            chunk.metadata.element_type,
            "value",
            chunk.metadata.element_type,
        )
        token_records.append(
            {
                "chunk_id": chunk.chunk_id,
                "tokens": token_count,
                "is_estimate": is_estimate,
                "source": chunk.metadata.source,
                "element_type": element_type,
            }
        )
        truncation_records.append(
            {
                "chunk_id": chunk.chunk_id,
                "tokens": token_count,
                "max_tokens": rerank_max_length,
                "truncated": truncated,
                "truncation_ratio": (
                    token_count / rerank_max_length if token_count else 0.0
                ),
                "source": chunk.metadata.source,
                "element_type": element_type,
            }
        )
    record_spot_check("rerank_input_tokens", token_records)
    record_spot_check("rerank_truncated", truncation_records)

    ranked = await rerank_client.rerank(
        query=query,
        documents=documents,
        top_n=top_n,
    )
    return [(chunks[index], score) for index, score in ranked]
