"""Build gold evidence E⁺ via high-recall pool + codex generate + claude verify.

State machine (MVP_PLAN §E.2):
  - found supporting evidence → E⁺
  - no evidence in corpus → corpus_gap (excluded from CRec denominator)
  - found but candidate C misses → retrieval_gap (counted by CRec at eval time)

Does not mutate the main project. Writes disputes under eval_methodology/review/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.paths import (  # noqa: E402
    DATA_DIR,
    GOLD_JSON,
    LABELS_JSON,
    REVIEW_DIR,
    SCHEMAS_DIR,
)
from eval_methodology.mvp.metrics.judges.cli_backend import (  # noqa: E402
    run_claude_json,
    run_codex_json,
)

GOLD_SCHEMA_PATH = SCHEMAS_DIR / "gold_output.schema.json"
VERIFY_SCHEMA_PATH = SCHEMAS_DIR / "gold_verify.schema.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def high_recall_pool(question: str, *, top_k: int = 30) -> list[dict[str, Any]]:
    """Multi-strategy high-recall chunk union (read-only against live indices).

    Strategies:
      1) BM25 primary question
      2) vector primary question
      3) keyword-stripped variants
      4) parent-chunk expansion from hits
    """
    from server.config import ServerConfig
    from server.core.retrieval import HybridRetriever

    config = ServerConfig()
    # Inflate retrieval budgets for gold mining only (in-proc, not agent path).
    data = config.model_dump()
    data["vector_top_k"] = top_k
    data["bm25_top_k"] = top_k
    data["rerank_top_n"] = min(top_k, 20)
    config = ServerConfig(**data)

    retriever = HybridRetriever(config)
    await retriever.initialize()
    try:
        queries = [question]
        # Light multi-query: strip punctuation-heavy Chinese question marks.
        stripped = question.replace("？", " ").replace("?", " ").strip()
        if stripped and stripped != question:
            queries.append(stripped)
        # Second pass: first 40 chars (focus head terms).
        if len(question) > 40:
            queries.append(question[:40])

        merged: dict[str, dict[str, Any]] = {}
        for q in queries:
            result = await retriever.retrieve(q)
            for chunk, score in zip(result.chunks, result.scores or [], strict=False):
                entry = {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "source": chunk.metadata.source,
                    "section_path": list(chunk.metadata.section_path),
                    "score": float(score) if score is not None else None,
                    "strategy": "retrieve",
                }
                prev = merged.get(chunk.chunk_id)
                if prev is None or (entry["score"] or 0) > (prev.get("score") or 0):
                    merged[chunk.chunk_id] = entry
            for parent in result.parent_chunks:
                if parent.chunk_id in merged:
                    continue
                merged[parent.chunk_id] = {
                    "chunk_id": parent.chunk_id,
                    "content": parent.content,
                    "source": parent.metadata.source,
                    "section_path": list(parent.metadata.section_path),
                    "score": None,
                    "strategy": "parent",
                }
            for ref in result.ref_chunks:
                if ref.chunk_id in merged:
                    continue
                merged[ref.chunk_id] = {
                    "chunk_id": ref.chunk_id,
                    "content": ref.content,
                    "source": ref.metadata.source,
                    "section_path": list(ref.metadata.section_path),
                    "score": None,
                    "strategy": "ref",
                }
        # Rank by score desc, keep top 40.
        ranked = sorted(
            merged.values(),
            key=lambda x: (x.get("score") is not None, x.get("score") or 0.0),
            reverse=True,
        )
        return ranked[:40]
    finally:
        await retriever.close()


def _pool_prompt(question: str, pool: list[dict[str, Any]]) -> str:
    lines = [
        "你是 Eurocode 规范问答的 gold 标注助手。",
        "给定问题与高召回 chunk 候选池，输出：",
        "1) reference_answer：基于池内证据的参考答案（中文）",
        "2) claims：原子说法列表，每条含 claim_id, text, status, evidence_chunk_ids, negative_chunk_ids",
        "status 只能是 supported | corpus_gap：",
        "  - supported：池内至少 1 个 chunk 充分支持该说法，填 evidence_chunk_ids",
        "  - corpus_gap：池内找不到支持证据",
        "negative_chunk_ids：相关但不足以支持该 claim 的 chunk（可空）",
        "只使用候选池中的 chunk_id，禁止编造 id。",
        "",
        f"问题：{question}",
        "",
        "候选池：",
    ]
    for i, c in enumerate(pool, 1):
        sec = " > ".join(c.get("section_path") or [])
        content = (c.get("content") or "")[:1200]
        lines.append(
            f"[{i}] chunk_id={c['chunk_id']} source={c.get('source')} section={sec}\n{content}"
        )
    return "\n".join(lines)


def _verify_prompt(question: str, gold: dict[str, Any], pool: list[dict[str, Any]]) -> str:
    pool_by_id = {c["chunk_id"]: c for c in pool}
    lines = [
        "你是独立核验员。检查 gold 标注是否成立。",
        "对每条 claim：evidence 是否真支持；reference_answer 是否有事实错误。",
        "输出 per_claim: [{claim_id, agree: bool, note: str}] 与 overall_agree: bool。",
        "",
        f"问题：{question}",
        f"参考答案：{gold.get('reference_answer', '')}",
        "",
        "claims：",
    ]
    for claim in gold.get("claims") or []:
        eids = claim.get("evidence_chunk_ids") or []
        snippets = []
        for eid in eids:
            chunk = pool_by_id.get(eid)
            if chunk:
                snippets.append(f"{eid}: {(chunk.get('content') or '')[:600]}")
        lines.append(
            f"- {claim.get('claim_id')}: status={claim.get('status')} text={claim.get('text')}\n"
            f"  evidence:\n  " + "\n  ".join(snippets or ["(none)"])
        )
    return "\n".join(lines)


def _ensure_schemas() -> None:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    if not GOLD_SCHEMA_PATH.is_file():
        GOLD_SCHEMA_PATH.write_text(
            json.dumps(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["reference_answer", "claims"],
                    "properties": {
                        "reference_answer": {"type": "string"},
                        "claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "claim_id",
                                    "text",
                                    "status",
                                    "evidence_chunk_ids",
                                    "negative_chunk_ids",
                                ],
                                "properties": {
                                    "claim_id": {"type": "string"},
                                    "text": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["supported", "corpus_gap"],
                                    },
                                    "evidence_chunk_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "negative_chunk_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if not VERIFY_SCHEMA_PATH.is_file():
        VERIFY_SCHEMA_PATH.write_text(
            json.dumps(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["overall_agree", "per_claim"],
                    "properties": {
                        "overall_agree": {"type": "boolean"},
                        "per_claim": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["claim_id", "agree", "note"],
                                "properties": {
                                    "claim_id": {"type": "string"},
                                    "agree": {"type": "boolean"},
                                    "note": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )


async def build_one(
    item: dict[str, Any],
    *,
    skip_llm: bool = False,
) -> dict[str, Any]:
    qid = item["id"]
    question = item["question"]
    pool = await high_recall_pool(question)
    pool_ids = {c["chunk_id"] for c in pool}

    if skip_llm:
        # Deterministic stub for offline wiring tests.
        gold = {
            "reference_answer": "",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "(stub — run without --skip-llm for real gold)",
                    "status": "corpus_gap" if not pool else "supported",
                    "evidence_chunk_ids": [pool[0]["chunk_id"]] if pool else [],
                    "negative_chunk_ids": [],
                }
            ],
        }
        verify = {"overall_agree": True, "per_claim": [{"claim_id": "c1", "agree": True, "note": "stub"}]}
        models = {"gold_family": "stub", "verify_family": "stub"}
    else:
        with tempfile.TemporaryDirectory(prefix="mvp_gold_") as tmp:
            gold = run_codex_json(
                _pool_prompt(question, pool),
                schema_path=GOLD_SCHEMA_PATH,
                workdir=Path(tmp),
            )
            verify = run_claude_json(
                _verify_prompt(question, gold, pool),
                schema_path=VERIFY_SCHEMA_PATH,
            )
        models = {
            "gold_family": "codex",
            "verify_family": "claude",
            "gold_model": gold.get("_resolved_model"),
            "verify_model": verify.get("_resolved_model"),
        }

    # Sanitize claim evidence ids to pool.
    e_plus: list[str] = []
    claims_out = []
    for claim in gold.get("claims") or []:
        status = claim.get("status") or "corpus_gap"
        eids = [e for e in (claim.get("evidence_chunk_ids") or []) if e in pool_ids]
        if status == "supported" and not eids:
            status = "corpus_gap"
        if status == "supported":
            e_plus.extend(eids)
        claims_out.append(
            {
                "claim_id": claim.get("claim_id"),
                "text": claim.get("text"),
                "status": status,
                "evidence_chunk_ids": eids,
                "negative_chunk_ids": [
                    e
                    for e in (claim.get("negative_chunk_ids") or [])
                    if e in pool_ids
                ],
            }
        )

    e_plus = sorted(set(e_plus))
    agree = bool(verify.get("overall_agree"))
    disputes = []
    for pc in verify.get("per_claim") or []:
        if not pc.get("agree", True):
            disputes.append(pc)

    status = "ok" if agree and not disputes else "needs_review"
    return {
        "id": qid,
        "question": question,
        "status": status,
        "built_at": _utc_now(),
        "models": models,
        "pool_chunk_ids": [c["chunk_id"] for c in pool],
        "pool_size": len(pool),
        "gold": {
            "reference_answer": gold.get("reference_answer", ""),
            "claims": claims_out,
            "E_plus": e_plus,
            "eligible_for_crec": bool(e_plus),
        },
        "verify": verify,
        "disputes": disputes,
    }


def write_disputes(results: list[dict[str, Any]]) -> Path | None:
    disputed = [r for r in results if r.get("disputes") or r.get("status") != "ok"]
    if not disputed:
        return None
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REVIEW_DIR / f"disputes_{ts}.md"
    lines = [
        f"# Gold disputes ({ts})",
        "",
        "人工复核范围 = 确认最小充分证据集（不止模型分歧）。",
        "",
    ]
    for r in disputed:
        lines.append(f"## {r['id']}: {r['question']}")
        lines.append(f"- status: {r.get('status')}")
        lines.append(f"- E⁺: {', '.join(r.get('gold', {}).get('E_plus') or []) or '(none)'}")
        for d in r.get("disputes") or []:
            lines.append(f"- dispute `{d.get('claim_id')}`: {d.get('note')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def build_all(
    labels_path: Path,
    *,
    limit: int | None = None,
    ids: list[str] | None = None,
    skip_llm: bool = False,
) -> dict[str, Any]:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    items = labels["items"]
    if ids:
        idset = set(ids)
        items = [i for i in items if i["id"] in idset]
    if limit is not None:
        items = items[:limit]

    results = []
    for idx, item in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] gold {item['id']}")
        try:
            results.append(await build_one(item, skip_llm=skip_llm))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "gold": {
                        "reference_answer": "",
                        "claims": [],
                        "E_plus": [],
                        "eligible_for_crec": False,
                    },
                }
            )

    disputes_path = write_disputes(results)
    return {
        "built_at": _utc_now(),
        "n": len(results),
        "disputes_path": str(disputes_path) if disputes_path else None,
        "items": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build gold E⁺ for MVP dataset")
    parser.add_argument("--labels", type=Path, default=LABELS_JSON)
    parser.add_argument("--out", type=Path, default=GOLD_JSON)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", type=str, default=None, help="comma-separated ids")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="offline stub gold (wiring only; not for real metrics)",
    )
    args = parser.parse_args(argv)
    _ensure_schemas()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ids = [x.strip() for x in args.ids.split(",")] if args.ids else None
    payload = asyncio.run(
        build_all(args.labels, limit=args.limit, ids=ids, skip_llm=args.skip_llm)
    )
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} n={payload['n']} disputes={payload.get('disputes_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
