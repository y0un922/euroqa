"""Dual-family judge: same fixed units → Faith/CitP verdicts + agreement gate."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
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
from eval_methodology.mvp.metrics.judges.extract import extract_units
from eval_methodology.mvp.metrics.schemas import (
    ExtractedUnits,
    JudgeRawOutput,
)
from eval_methodology.mvp.paths import SCHEMAS_DIR

JUDGE_SCHEMA = SCHEMAS_DIR / "judge_output.schema.json"


@dataclass
class DualJudgeResult:
    units: ExtractedUnits
    codex: JudgeRawOutput | None
    claude: JudgeRawOutput | None
    faith: float | None
    citp: float | None
    agreed: bool
    dropped: bool
    drop_reason: str
    resolved_models: dict[str, str]
    per_claim_agreement: dict[str, bool]
    per_citation_agreement: dict[str, bool]


def _judge_prompt(
    question: str,
    answer: str,
    units: ExtractedUnits,
    context_chunks: list[dict[str, Any]],
) -> str:
    ctx_lines = []
    for c in context_chunks[:30]:
        ctx_lines.append(
            f"- {c.get('chunk_id')}: {(c.get('content') or '')[:800]}"
        )
    return (
        "你是严格的 Eurocode QA 评判员。\n"
        "对**给定**的 claim/citation 单元逐条判定，禁止增删或重拆单元。\n"
        "- claim supported=true 当且仅当上下文充分支持该说法（不可外部知识补全）\n"
        "- citation valid=true 当且仅当引用内容级支持其链接说法，且源在上下文内\n"
        f"问题：{question}\n"
        f"答案：{answer}\n"
        f"单元：{json.dumps(units.model_dump(), ensure_ascii=False)}\n"
        "上下文 C：\n" + "\n".join(ctx_lines)
    )


def _run_family(
    family: str,
    prompt: str,
    *,
    cache: JudgeCache,
    cache_key: str,
) -> tuple[JudgeRawOutput | None, str, str | None]:
    cached = cache.get(cache_key)
    if cached:
        try:
            return (
                JudgeRawOutput.model_validate(cached["output"]),
                cached.get("model_id", f"{family}-cached"),
                None,
            )
        except Exception as exc:  # noqa: BLE001
            err = f"cache corrupt: {exc}"
        else:
            err = None
    else:
        err = None

    try:
        if family == "codex":
            with tempfile.TemporaryDirectory(prefix="mvp_judge_") as tmp:
                raw = run_with_retry(
                    lambda: run_codex_json(
                        prompt,
                        schema_path=JUDGE_SCHEMA,
                        workdir=Path(tmp),
                    )
                )
        else:
            raw = run_with_retry(
                lambda: run_claude_json(prompt, schema_path=JUDGE_SCHEMA)
            )
        model_id = str(raw.get("_resolved_model") or f"{family}-default")
        cleaned = {k: v for k, v in raw.items() if not k.startswith("_")}
        out = JudgeRawOutput.model_validate(cleaned)
        cache.set(
            cache_key,
            {"output": out.model_dump(), "model_id": model_id, "family": family},
        )
        return out, model_id, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{family}-failed", f"{type(exc).__name__}: {exc}"


def _rate(supported_flags: list[bool]) -> float | None:
    if not supported_flags:
        return None
    return sum(1 for x in supported_flags if x) / len(supported_flags)


def judge_question(
    *,
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
    use_llm_extract: bool = True,
    cache: JudgeCache | None = None,
) -> DualJudgeResult:
    """Extract units once, dual-judge, gate on unit-level agreement."""
    cache = cache or JudgeCache()
    units = extract_units(
        question=question,
        answer=answer,
        sources=sources,
        context_chunks=context_chunks,
        use_llm=use_llm_extract,
        family="codex",
        cache=cache,
    )
    prompt = _judge_prompt(question, answer, units, context_chunks)

    codex_key = make_cache_key(
        family="codex",
        model_id="codex-judge",
        question=question,
        answer=answer,
        context_chunks=context_chunks,
        citations=units.model_dump(),
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        kind="judge",
    )
    claude_key = make_cache_key(
        family="claude",
        model_id="claude-judge",
        question=question,
        answer=answer,
        context_chunks=context_chunks,
        citations=units.model_dump(),
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        kind="judge",
    )

    codex_out, codex_model, codex_err = _run_family(
        "codex", prompt, cache=cache, cache_key=codex_key
    )
    claude_out, claude_model, claude_err = _run_family(
        "claude", prompt, cache=cache, cache_key=claude_key
    )

    resolved = {
        "codex": codex_model,
        "claude": claude_model,
        "codex_family": "codex",
        "claude_family": "claude",
    }

    if codex_out is None or claude_out is None:
        return DualJudgeResult(
            units=units,
            codex=codex_out,
            claude=claude_out,
            faith=None,
            citp=None,
            agreed=False,
            dropped=True,
            drop_reason=f"missing judge: codex={codex_err} claude={claude_err}",
            resolved_models=resolved,
            per_claim_agreement={},
            per_citation_agreement={},
        )

    claim_agree: dict[str, bool] = {}
    codex_claim = {v.unit_id: v.supported for v in codex_out.claim_verdicts}
    claude_claim = {v.unit_id: v.supported for v in claude_out.claim_verdicts}
    for u in units.claims:
        a = codex_claim.get(u.unit_id)
        b = claude_claim.get(u.unit_id)
        claim_agree[u.unit_id] = a is not None and b is not None and a == b

    cit_agree: dict[str, bool] = {}
    codex_cit = {v.citation_id: v.valid for v in codex_out.citation_verdicts}
    claude_cit = {v.citation_id: v.valid for v in claude_out.citation_verdicts}
    for c in units.citations:
        a = codex_cit.get(c.citation_id)
        b = claude_cit.get(c.citation_id)
        cit_agree[c.citation_id] = a is not None and b is not None and a == b

    # Question-level drop rule: any claim unit disagrees → drop Faith/CitP for item.
    claims_all_agree = all(claim_agree.values()) if claim_agree else False
    # If no claims extracted, drop.
    if not units.claims:
        return DualJudgeResult(
            units=units,
            codex=codex_out,
            claude=claude_out,
            faith=None,
            citp=None,
            agreed=False,
            dropped=True,
            drop_reason="no claims extracted",
            resolved_models=resolved,
            per_claim_agreement=claim_agree,
            per_citation_agreement=cit_agree,
        )

    if not claims_all_agree:
        return DualJudgeResult(
            units=units,
            codex=codex_out,
            claude=claude_out,
            faith=None,
            citp=None,
            agreed=False,
            dropped=True,
            drop_reason="claim-level judge disagreement",
            resolved_models=resolved,
            per_claim_agreement=claim_agree,
            per_citation_agreement=cit_agree,
        )

    # Agreed path: use conservative AND of both families for scores.
    faith_flags = []
    for u in units.claims:
        faith_flags.append(bool(codex_claim[u.unit_id] and claude_claim[u.unit_id]))
    faith = _rate(faith_flags)

    citp: float | None
    if not units.citations:
        # No citations in answer: if system requires citations, CitP=0 when answer non-empty.
        citp = 0.0 if (answer or "").strip() else None
    else:
        # Citation agreement required for those present; disagreeing citation → drop CitP only.
        if units.citations and not all(cit_agree.get(c.citation_id, False) for c in units.citations):
            return DualJudgeResult(
                units=units,
                codex=codex_out,
                claude=claude_out,
                faith=faith,
                citp=None,
                agreed=False,
                dropped=True,
                drop_reason="citation-level judge disagreement",
                resolved_models=resolved,
                per_claim_agreement=claim_agree,
                per_citation_agreement=cit_agree,
            )
        cit_flags = [
            bool(codex_cit[c.citation_id] and claude_cit[c.citation_id])
            for c in units.citations
        ]
        citp = _rate(cit_flags)

    return DualJudgeResult(
        units=units,
        codex=codex_out,
        claude=claude_out,
        faith=faith,
        citp=citp,
        agreed=True,
        dropped=False,
        drop_reason="",
        resolved_models=resolved,
        per_claim_agreement=claim_agree,
        per_citation_agreement=cit_agree,
    )
