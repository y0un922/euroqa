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
    resolve_claude_model_id,
    resolve_codex_model_id,
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
    model_id: str,
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]],
    units: ExtractedUnits,
) -> tuple[JudgeRawOutput | None, str, str | None]:
    """Run one judge family. Cache key includes the real resolved model id."""
    cache_key = make_cache_key(
        family=family,
        model_id=model_id,
        question=question,
        answer=answer,
        context_chunks=context_chunks,
        citations=units.model_dump(),
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        kind="judge",
    )
    cached = cache.get(cache_key)
    if cached:
        try:
            return (
                JudgeRawOutput.model_validate(cached["output"]),
                str(cached.get("model_id") or model_id),
                None,
            )
        except Exception as exc:  # noqa: BLE001
            # Fall through to re-run on corrupt cache.
            _ = f"cache corrupt: {exc}"

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
        actual_model = str(raw.get("_resolved_model") or model_id)
        # If CLI resolved a more specific model than env placeholder, re-key cache.
        if actual_model != model_id:
            cache_key = make_cache_key(
                family=family,
                model_id=actual_model,
                question=question,
                answer=answer,
                context_chunks=context_chunks,
                citations=units.model_dump(),
                prompt_schema_version=PROMPT_SCHEMA_VERSION,
                kind="judge",
            )
        cleaned = {k: v for k, v in raw.items() if not k.startswith("_")}
        out = JudgeRawOutput.model_validate(cleaned)
        cache.set(
            cache_key,
            {
                "output": out.model_dump(),
                "model_id": actual_model,
                "family": family,
                "parse_source": raw.get("_parse_source"),
            },
        )
        return out, actual_model, None
    except Exception as exc:  # noqa: BLE001
        return None, model_id, f"{type(exc).__name__}: {exc}"


def _rate(supported_flags: list[bool]) -> float | None:
    if not supported_flags:
        return None
    return sum(1 for x in supported_flags if x) / len(supported_flags)


def _drop(
    *,
    units: ExtractedUnits,
    codex: JudgeRawOutput | None,
    claude: JudgeRawOutput | None,
    reason: str,
    resolved: dict[str, str],
    claim_agree: dict[str, bool] | None = None,
    cit_agree: dict[str, bool] | None = None,
) -> DualJudgeResult:
    """Question-level drop: both Faith and CitP null; counts toward drop rate."""
    return DualJudgeResult(
        units=units,
        codex=codex,
        claude=claude,
        faith=None,
        citp=None,
        agreed=False,
        dropped=True,
        drop_reason=reason,
        resolved_models=resolved,
        per_claim_agreement=claim_agree or {},
        per_citation_agreement=cit_agree or {},
    )


def judge_question(
    *,
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
    use_llm_extract: bool = True,
    cache: JudgeCache | None = None,
    codex_model: str | None = None,
    claude_model: str | None = None,
) -> DualJudgeResult:
    """Extract units once, dual-judge, gate on unit-level agreement.

    Any unit-level disagreement or missing family → full question drop
    (Faith and CitP both null; audit D2).
    """
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

    codex_model_id = resolve_codex_model_id(codex_model)
    claude_model_id = resolve_claude_model_id(claude_model)

    codex_out, codex_model_id, codex_err = _run_family(
        "codex",
        prompt,
        cache=cache,
        model_id=codex_model_id,
        question=question,
        answer=answer,
        context_chunks=context_chunks,
        units=units,
    )
    claude_out, claude_model_id, claude_err = _run_family(
        "claude",
        prompt,
        cache=cache,
        model_id=claude_model_id,
        question=question,
        answer=answer,
        context_chunks=context_chunks,
        units=units,
    )

    resolved = {
        "codex": codex_model_id,
        "claude": claude_model_id,
        "codex_family": "codex",
        "claude_family": "claude",
    }

    if codex_out is None or claude_out is None:
        return _drop(
            units=units,
            codex=codex_out,
            claude=claude_out,
            reason=f"missing judge: codex={codex_err} claude={claude_err}",
            resolved=resolved,
        )

    if not units.claims:
        return _drop(
            units=units,
            codex=codex_out,
            claude=claude_out,
            reason="no claims extracted",
            resolved=resolved,
        )

    codex_claim = {v.unit_id: v.supported for v in codex_out.claim_verdicts}
    claude_claim = {v.unit_id: v.supported for v in claude_out.claim_verdicts}
    claim_agree: dict[str, bool] = {}
    for u in units.claims:
        a = codex_claim.get(u.unit_id)
        b = claude_claim.get(u.unit_id)
        claim_agree[u.unit_id] = a is not None and b is not None and a == b

    if not all(claim_agree.values()):
        return _drop(
            units=units,
            codex=codex_out,
            claude=claude_out,
            reason="claim-level judge disagreement",
            resolved=resolved,
            claim_agree=claim_agree,
        )

    codex_cit = {v.citation_id: v.valid for v in codex_out.citation_verdicts}
    claude_cit = {v.citation_id: v.valid for v in claude_out.citation_verdicts}
    cit_agree: dict[str, bool] = {}
    for c in units.citations:
        a = codex_cit.get(c.citation_id)
        b = claude_cit.get(c.citation_id)
        cit_agree[c.citation_id] = a is not None and b is not None and a == b

    # Citation disagreement → full question drop (do not keep Faith alone).
    if units.citations and not all(cit_agree.values()):
        return _drop(
            units=units,
            codex=codex_out,
            claude=claude_out,
            reason="citation-level judge disagreement",
            resolved=resolved,
            claim_agree=claim_agree,
            cit_agree=cit_agree,
        )

    faith_flags = [
        bool(codex_claim[u.unit_id] and claude_claim[u.unit_id]) for u in units.claims
    ]
    faith = _rate(faith_flags)

    if not units.citations:
        citp = 0.0 if (answer or "").strip() else None
    else:
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
