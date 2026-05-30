from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()


_CITATION_VARIANTS_RE = re.compile(
    r"[\[【(]"  # 开括号: [ 【 (
    r"[Rr]ef"  # Ref / ref
    r"[\s\-]+"  # 分隔符: 空格或连字符
    r"(\d+)"  # 捕获编号
    r"[\]】)]"  # 闭括号: ] 】 )
)

_CANONICAL_REF_RE = re.compile(r"\[Ref-(\d+)\]")


def postprocess_citations(answer: str, num_sources: int) -> str:
    """归一化 [Ref-N] 格式变体、剔除越界编号、句内去重。

    Args:
        answer: LLM 生成的回答正文
        num_sources: 有效 sources 数量（[Ref-1] 到 [Ref-num_sources]）

    Returns:
        归一化后的回答文本
    """
    if not answer:
        return answer

    # Step 1: 归一化所有变体为 [Ref-N]
    def _normalize_match(m: re.Match) -> str:
        return f"[Ref-{m.group(1)}]"

    answer = _CITATION_VARIANTS_RE.sub(_normalize_match, answer)

    # Step 2: 剔除越界编号 (N < 1 or N > num_sources)
    def _strip_oob(m: re.Match) -> str:
        n = int(m.group(1))
        if n < 1 or n > num_sources:
            logger.warning(
                "citation_out_of_bounds ref=%d num_sources=%d", n, num_sources
            )
            return ""
        return m.group(0)

    answer = _CANONICAL_REF_RE.sub(_strip_oob, answer)

    # Step 3: 句内去重 — 以句号/问号/感叹号/换行为句子分隔
    def _dedup_sentence(sentence: str) -> str:
        seen: set[str] = set()
        parts: list[str] = []
        last_end = 0
        for m in _CANONICAL_REF_RE.finditer(sentence):
            parts.append(sentence[last_end : m.start()])
            ref_tag = m.group(0)
            if ref_tag not in seen:
                seen.add(ref_tag)
                parts.append(ref_tag)
            last_end = m.end()
        parts.append(sentence[last_end:])
        return "".join(parts)

    # 按句子边界拆分后逐句去重，保留分隔符
    segments = re.split(r"([。？！\n])", answer)
    result_parts: list[str] = []
    for i, seg in enumerate(segments):
        if i % 2 == 0:
            result_parts.append(_dedup_sentence(seg))
        else:
            result_parts.append(seg)  # 分隔符原样保留
    return "".join(result_parts)


def _extract_json_text(raw: str) -> str:
    """从可能带 Markdown 代码块的文本中提取 JSON 内容。"""
    cleaned = raw
    if "```json" in cleaned:
        return cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in cleaned:
        return cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return cleaned
