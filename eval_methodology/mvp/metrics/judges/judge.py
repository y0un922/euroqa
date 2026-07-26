"""Single-family structured judge for Faith and citation precision."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eval_methodology.mvp.metrics.judges.cache import (
    PROMPT_SCHEMA_VERSION,
    JudgeCache,
    make_cache_key,
)
from eval_methodology.mvp.metrics.judges.cli_backend import (
    CLIJudgeError,
    pin_resolved_model,
    resolve_claude_model_id,
    resolve_codex_model_id,
    run_claude_json,
    run_codex_json,
    run_with_retry,
)
from eval_methodology.mvp.paths import SCHEMAS_DIR

JUDGE_SCHEMA = SCHEMAS_DIR / "judge_output.schema.json"

# Total context budget for one judge prompt. Chunks are included in full and in
# order; anything the answer cites must be visible to the judge, otherwise CitP
# and Faith are systematically depressed (measured: the old 30-chunk/800-char
# truncation hid 15% of cited refs and cut 69% of chunks). The budget is ~40%
# above the largest observed question and exists only as an overflow guard;
# omitted refs are declared in the prompt instead of silently judged invalid.
JUDGE_MAX_TOTAL_CONTEXT_CHARS = 240_000


@dataclass(frozen=True)
class JudgeResult:
    faith: float | None
    citp: float | None
    n_claims: int
    n_citations: int
    judge_failed: bool
    fail_reason: str
    resolved_model: str
    family: str
    # LLM-based gold evidence coverage (for CRec). Maps evidence_id -> covered bool.
    # Populated only when gold_evidence was provided to the judge.
    gold_evidence_coverages: dict[str, bool] = field(default_factory=dict)


def _judge_prompt(
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]],
    gold_evidence: list[dict[str, Any]] | None = None,
) -> str:
    context = []
    used = 0
    omitted_from = None
    for index, chunk in enumerate(context_chunks, 1):
        content = str(chunk.get("content") or "")
        if used + len(content) > JUDGE_MAX_TOTAL_CONTEXT_CHARS:
            omitted_from = index
            break
        used += len(content)
        context.append(
            f"[Ref-{index}] chunk_id={chunk.get('chunk_id', '')}\n{content}"
        )
    if omitted_from is not None:
        context.append(
            f"[注意] Ref-{omitted_from} 至 Ref-{len(context_chunks)} 因长度限制未展示；"
            "对指向这些 Ref 的引用输出 valid=false 并在判断 claims 时忽略它们。"
        )

    parts = [
        "你是严格的 Eurocode QA 评判员。只依据给定上下文判断。\n"
        "将答案拆成**关键原子 claims**（聚焦 distinct technical facts，避免过度拆分同一事实）。逐条输出 text 与 supported。\n"
        "supported=true 当且仅当上下文能 entail（蕴含）该说法（允许合理释义，但数值、公式、限定条件必须一致）。\n"
        "找出答案中的 [Ref-N] 引用，并逐条输出 ref_label 与 valid；"
        "只有对应上下文能支持相邻说法时 valid=true。\n"
    ]
    if gold_evidence:
        parts.append(
            "\n另外，对 gold_evidence 中的每个证据项，判断提供的上下文中是否包含能支持该证据核心信息（quote 的实质内容）的 Ref。"
            "若专业读者依据上下文可确认该事实，则 covered=true。输出 gold_evidence_coverages 数组。\n"
        )
        ev_lines = []
        for ev in gold_evidence:
            eid = str(ev.get("evidence_id") or "")
            q = str(ev.get("quote") or "")[:300]
            sec = str(ev.get("section") or "")
            ev_lines.append(f"- evidence_id={eid} section={sec} quote={q}")
        parts.append("gold_evidence:\n" + "\n".join(ev_lines) + "\n")

    parts.append(f"问题：{question}\n答案：{answer}\n上下文：\n" + "\n\n".join(context))
    return "".join(parts)


def _rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _parse_output(
    raw: dict[str, Any], answer: str
) -> tuple[float | None, float | None, int, int, dict[str, bool]]:
    claims = raw.get("claims")
    citations = raw.get("citations")
    if not isinstance(claims, list) or not isinstance(citations, list):
        raise ValueError("judge output must contain claims and citations arrays")
    claim_flags = [item["supported"] for item in claims if isinstance(item, dict) and isinstance(item.get("supported"), bool)]
    citation_flags = [item["valid"] for item in citations if isinstance(item, dict) and isinstance(item.get("valid"), bool)]
    if len(claim_flags) != len(claims) or len(citation_flags) != len(citations):
        raise ValueError("judge output contains invalid verdict entries")
    citp = _rate(citation_flags)
    if not citations and answer.strip():
        citp = 0.0
    # Parse optional LLM gold evidence coverage
    coverages: dict[str, bool] = {}
    gec = raw.get("gold_evidence_coverages")
    if isinstance(gec, list):
        for item in gec:
            if isinstance(item, dict):
                eid = str(item.get("evidence_id") or "")
                cov = item.get("covered")
                if eid and isinstance(cov, bool):
                    coverages[eid] = cov
    return _rate(claim_flags), citp, len(claims), len(citations), coverages


def _model_id(family: str) -> str:
    return resolve_codex_model_id() if family == "codex" else resolve_claude_model_id()


def judge_question(
    *,
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]],
    cache: JudgeCache | None = None,
    gold_evidence: list[dict[str, Any]] | None = None,
) -> JudgeResult:
    """Judge one answer with the configured CLI family (full LLM-as-judge).

    Faith/CitP use atomic claim + citation validity (preserves original judgment approach).
    When gold_evidence is supplied, also computes LLM semantic coverage for CRec
    (replaces brittle string match; fully LLM-based, no human confirmation needed).

    Args:
        question: User question.
        answer: Generated answer.
        context_chunks: Ordered citable context snapshots.
        cache: Optional content-addressed cache.
        gold_evidence: Optional list of gold evidence locators (with evidence_id + quote).
                       When present, the judge will also return coverage verdicts.

    Returns:
        Computed metrics or a failure result with null metrics.
    """
    family = os.environ.get("MVP_JUDGE_FAMILY", "claude").strip().lower()
    explicit_model = os.environ.get("MVP_JUDGE_MODEL", "").strip() or None
    cache = cache or JudgeCache()
    model_id = explicit_model or _model_id(family)

    # Stability for low variance: strongly prefer an explicit pinned model.
    # Different models (or fallback "xxx-unresolved") are the #1 source of run-to-run swings.
    if not explicit_model and ("unresolved" in model_id or model_id.endswith("-failed")):
        # Still proceed (for dev), but results will not be comparable across runs.
        pass  # caller can set MVP_JUDGE_MODEL=claude-xxx or codex-xxx to pin.
    prompt = _judge_prompt(question, answer, context_chunks, gold_evidence=gold_evidence)
    key_args = {
        "family": family,
        "model_id": model_id,
        "question": question,
        "answer": answer,
        "context_chunks": context_chunks,
        "gold_evidence": gold_evidence or [],
        "citations": None,
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
    }
    cached = cache.get(make_cache_key(**key_args))
    if cached:
        try:
            res = dict(cached["result"])
            if "gold_evidence_coverages" not in res:
                res["gold_evidence_coverages"] = {}
            return JudgeResult(**res)
        except (KeyError, TypeError):
            pass

    try:
        if family == "claude":
            raw = run_with_retry(
                lambda: run_claude_json(
                    prompt,
                    schema_path=JUDGE_SCHEMA,
                    model=explicit_model,
                    timeout_s=180.0,
                ),
                retries=1,
            )
        elif family == "codex":
            with tempfile.TemporaryDirectory(prefix="mvp_judge_") as tmp:
                raw = run_with_retry(
                    lambda: run_codex_json(
                        prompt,
                        schema_path=JUDGE_SCHEMA,
                        workdir=Path(tmp),
                        model=explicit_model,
                        timeout_s=180.0,
                    ),
                    retries=1,
                )
        else:
            raise ValueError(f"unsupported MVP_JUDGE_FAMILY={family!r}")
        resolved_model = str(raw.get("_resolved_model") or model_id)
        if explicit_model and explicit_model not in resolved_model:
            raise CLIJudgeError(
                f"judge model pin mismatch: MVP_JUDGE_MODEL={explicit_model!r} "
                f"but CLI resolved {resolved_model!r}"
            )
        pin_resolved_model(family, resolved_model)
        cleaned = {key: value for key, value in raw.items() if not key.startswith("_")}
        faith, citp, n_claims, n_citations, coverages = _parse_output(cleaned, answer)
        result = JudgeResult(
            faith=faith,
            citp=citp,
            n_claims=n_claims,
            n_citations=n_citations,
            judge_failed=False,
            fail_reason="",
            resolved_model=resolved_model,
            family=family,
            gold_evidence_coverages=coverages or {},
        )
        actual_args = {**key_args, "model_id": resolved_model}
        payload = {"result": asdict(result), "output": cleaned}
        cache.set(make_cache_key(**actual_args), payload)
        # Alias-write under the lookup key only when that key cannot collide with a
        # real model id: the unresolved placeholder, or an explicit pin the resolved
        # id was just verified against. Aliasing a stale real id would let lookups
        # under model X return results judged by model Y.
        if resolved_model != model_id and (
            explicit_model or model_id.endswith("-unresolved")
        ):
            cache.set(make_cache_key(**key_args), payload)
        return result
    except Exception as exc:  # noqa: BLE001
        return JudgeResult(
            faith=None,
            citp=None,
            n_claims=0,
            n_citations=0,
            judge_failed=True,
            fail_reason=f"{type(exc).__name__}: {exc}",
            resolved_model=model_id,
            family=family,
            gold_evidence_coverages={},
        )
