"""Fixed claim/citation extraction step (unit alignment for dual judges).

Both families judge the *same* unit list produced here — they must not
split claims independently (MVP_PLAN §E.2).
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from eval_methodology.mvp.metrics.judges.cache import (
    PROMPT_SCHEMA_VERSION,
    JudgeCache,
    make_cache_key,
)
from eval_methodology.mvp.metrics.judges.cli_backend import (
    run_claude_json,
    run_codex_json,
    run_with_retry,
)
from eval_methodology.mvp.metrics.schemas import (
    CitationUnit,
    ClaimUnit,
    ExtractedUnits,
)
from eval_methodology.mvp.paths import SCHEMAS_DIR

EXTRACT_SCHEMA = SCHEMAS_DIR / "extract_units.schema.json"

_REF_RE = re.compile(r"\[Ref-(\d+)\]|【Ref-(\d+)】|\[(\d+)\]")


def _heuristic_extract(answer: str, sources: list[dict[str, Any]] | None) -> ExtractedUnits:
    """Offline fallback: sentence-level claims + Ref-N citations."""
    text = (answer or "").strip()
    # Split on Chinese / English sentence boundaries.
    parts = [
        p.strip()
        for p in re.split(r"(?<=[。！？.!?；;])\s*", text)
        if p and p.strip()
    ]
    if not parts and text:
        parts = [text]

    claims: list[ClaimUnit] = []
    citations: list[CitationUnit] = []
    cite_index: dict[str, str] = {}

    for i, part in enumerate(parts, 1):
        uid = f"claim_{i}"
        linked: list[str] = []
        for m in _REF_RE.finditer(part):
            num = m.group(1) or m.group(2) or m.group(3)
            label = f"Ref-{num}"
            if label not in cite_index:
                cid = f"cit_{len(cite_index) + 1}"
                cite_index[label] = cid
                hint = ""
                if sources and num.isdigit():
                    idx = int(num) - 1
                    if 0 <= idx < len(sources):
                        s = sources[idx]
                        hint = str(
                            s.get("file")
                            or s.get("fileName")
                            or s.get("clause")
                            or ""
                        )
                citations.append(
                    CitationUnit(
                        citation_id=cid,
                        ref_label=label,
                        linked_claim_ids=[uid],
                        source_hint=hint,
                    )
                )
            else:
                cid = cite_index[label]
                for c in citations:
                    if c.citation_id == cid and uid not in c.linked_claim_ids:
                        c.linked_claim_ids.append(uid)
            linked.append(cite_index[label])
        claims.append(ClaimUnit(unit_id=uid, text=part, citation_ids=linked))

    return ExtractedUnits(claims=claims, citations=citations)


def _extract_prompt(question: str, answer: str, sources: list[dict[str, Any]] | None) -> str:
    return (
        "将答案拆成原子说法(claims)与引用单元(citations)。\n"
        "规则：\n"
        "1) 每个 claim 一条可独立判定的事实/数值/条件说法，赋 unit_id=claim_N\n"
        "2) 引用单元对应 [Ref-N] 或脚注，赋 citation_id=cit_N，ref_label=Ref-N\n"
        "3) 记录 claim↔citation 链接；不要评判真假，只做切分\n"
        f"问题：{question}\n"
        f"答案：{answer}\n"
        f"sources: {json.dumps(sources or [], ensure_ascii=False)[:3000]}\n"
    )


def extract_units(
    *,
    question: str,
    answer: str,
    sources: list[dict[str, Any]] | None = None,
    context_chunks: list[dict[str, Any]] | None = None,
    use_llm: bool = True,
    family: str = "codex",
    cache: JudgeCache | None = None,
) -> ExtractedUnits:
    """Produce fixed units. Prefer LLM extract; fall back to heuristic."""
    cache = cache or JudgeCache()
    model_id = f"{family}-extract"
    key = make_cache_key(
        family=family,
        model_id=model_id,
        question=question,
        answer=answer,
        context_chunks=context_chunks or [],
        citations=sources or [],
        prompt_schema_version=PROMPT_SCHEMA_VERSION + "-extract",
        kind="extract",
    )
    cached = cache.get(key)
    if cached:
        return ExtractedUnits.model_validate(cached)

    if not use_llm:
        units = _heuristic_extract(answer, sources)
        cache.set(key, units.model_dump())
        return units

    prompt = _extract_prompt(question, answer, sources)
    try:
        if family == "claude":
            raw = run_with_retry(
                lambda: run_claude_json(prompt, schema_path=EXTRACT_SCHEMA)
            )
        else:
            with tempfile.TemporaryDirectory(prefix="mvp_extract_") as tmp:
                raw = run_with_retry(
                    lambda: run_codex_json(
                        prompt,
                        schema_path=EXTRACT_SCHEMA,
                        workdir=Path(tmp),
                    )
                )
        units = ExtractedUnits.model_validate(
            {k: v for k, v in raw.items() if not k.startswith("_")}
        )
    except Exception:
        units = _heuristic_extract(answer, sources)

    if not units.claims:
        units = _heuristic_extract(answer, sources)

    cache.set(key, units.model_dump())
    return units
