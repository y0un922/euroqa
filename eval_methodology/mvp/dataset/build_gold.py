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


def _chunk_entry(chunk: Any, *, score: float | None, strategy: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "content": chunk.content,
        "source": chunk.metadata.source,
        "section_path": list(chunk.metadata.section_path),
        "parent_chunk_id": chunk.metadata.parent_chunk_id or "",
        "object_label": chunk.metadata.object_label or "",
        "score": score,
        "strategy": strategy,
    }


def _merge_entry(
    merged: dict[str, dict[str, Any]],
    entry: dict[str, Any],
) -> None:
    prev = merged.get(entry["chunk_id"])
    if prev is None:
        merged[entry["chunk_id"]] = entry
        return
    # Keep higher score; union strategies.
    if (entry.get("score") or 0) > (prev.get("score") or 0):
        strategies = {prev.get("strategy"), entry.get("strategy")}
        entry = {**entry, "strategy": "+".join(sorted(s for s in strategies if s))}
        merged[entry["chunk_id"]] = entry
    else:
        strategies = {prev.get("strategy"), entry.get("strategy")}
        prev["strategy"] = "+".join(sorted(s for s in strategies if s))


def _question_queries(question: str) -> list[str]:
    queries = [question]
    stripped = question.replace("？", " ").replace("?", " ").strip()
    if stripped and stripped != question:
        queries.append(stripped)
    if len(question) > 40:
        queries.append(question[:40])
    return list(dict.fromkeys(queries))


def _object_labels_from_question(question: str) -> list[str]:
    """Pull Table/Figure/Expression/Clause-like labels for exact object lookup."""
    from shared.reference_graph import extract_reference_labels

    labels = list(extract_reference_labels(question))
    # Lightweight Chinese/number patterns often present in client questions.
    import re

    for m in re.finditer(
        r"(?:Table|表|Figure|图|Expression|公式|Clause|条款)\s*([0-9]+(?:\.[0-9]+)*)",
        question,
        re.I,
    ):
        head = m.group(0)
        labels.append(head)
    return list(dict.fromkeys(labels))


async def _neighbor_chunks(retriever: Any, seed_ids: list[str]) -> list[Any]:
    """Parent + sibling-by-parent expansion around seed hits."""
    out: list[Any] = []
    seen: set[str] = set()
    for cid in seed_ids[:20]:
        try:
            opened = await retriever.open_chunk(cid, neighbors=1)
        except Exception:  # noqa: BLE001
            opened = []
        for ch in opened:
            if ch.chunk_id not in seen:
                seen.add(ch.chunk_id)
                out.append(ch)
        # Sibling expansion: other children of the same parent via ES.
        parent_id = None
        for ch in opened:
            if ch.chunk_id == cid:
                parent_id = ch.metadata.parent_chunk_id
                break
        if not parent_id:
            continue
        try:
            es = await retriever._get_es()
            body = {
                "size": 6,
                "query": {"term": {"parent_chunk_id": parent_id}},
                "_source": False,
            }
            resp = await es.search(index=retriever.config.es_index, body=body)
            sib_ids = [
                h.get("_id")
                for h in resp.get("hits", {}).get("hits", [])
                if h.get("_id") and h.get("_id") not in seen
            ]
            if sib_ids:
                siblings = await retriever._fetch_chunks(sib_ids[:4])
                for ch in siblings:
                    if ch.chunk_id not in seen:
                        seen.add(ch.chunk_id)
                        out.append(ch)
        except Exception:  # noqa: BLE001
            continue
    return out


async def high_recall_pool(question: str, *, top_k: int = 30) -> list[dict[str, Any]]:
    """Independent multi-strategy high-recall union (read-only).

    Strategies (MVP_PLAN / audit C4):
      1) Independent BM25 per query variant
      2) Independent vector search per query variant
      3) Object exact lookup (table/figure/expression/clause labels)
      4) Parent + neighbor (sibling) expansion around hits
    Does **not** rely solely on HybridRetriever.retrieve() fused path.
    """
    from server.config import ServerConfig
    from server.core.retrieval import HybridRetriever

    config = ServerConfig()
    data = config.model_dump()
    data["vector_top_k"] = top_k
    data["bm25_top_k"] = top_k
    data["rerank_top_n"] = min(top_k, 20)
    config = ServerConfig(**data)

    retriever = HybridRetriever(config)
    await retriever.initialize()
    try:
        merged: dict[str, dict[str, Any]] = {}
        seed_ids: list[str] = []
        filters: dict = {}

        for q in _question_queries(question):
            # 1) BM25 alone
            try:
                bm25 = await retriever._bm25_search(q, top_k=top_k, filters=filters)
            except Exception:  # noqa: BLE001
                bm25 = []
            bm25_ids = [r["chunk_id"] for r in bm25 if r.get("chunk_id")]
            if bm25_ids:
                chunks = await retriever._fetch_chunks(bm25_ids)
                by_id = {c.chunk_id: c for c in chunks}
                for r in bm25:
                    cid = r.get("chunk_id")
                    if cid in by_id:
                        score = r.get("score")
                        _merge_entry(
                            merged,
                            _chunk_entry(
                                by_id[cid],
                                score=float(score) if score is not None else None,
                                strategy="bm25",
                            ),
                        )
                        seed_ids.append(cid)

            # 2) Vector alone
            try:
                vec = await retriever._vector_search(q, top_k, filters)
            except Exception:  # noqa: BLE001
                vec = []
            vec_ids = [r["chunk_id"] for r in vec if r.get("chunk_id")]
            if vec_ids:
                chunks = await retriever._fetch_chunks(vec_ids)
                by_id = {c.chunk_id: c for c in chunks}
                for r in vec:
                    cid = r.get("chunk_id")
                    if cid in by_id:
                        score = r.get("score")
                        _merge_entry(
                            merged,
                            _chunk_entry(
                                by_id[cid],
                                score=float(score) if score is not None else None,
                                strategy="vector",
                            ),
                        )
                        seed_ids.append(cid)

        # 3) Object exact lookup
        for label in _object_labels_from_question(question):
            try:
                objs = await retriever.lookup_object(label, filters=filters, top_k=3)
            except Exception:  # noqa: BLE001
                objs = []
            for ch in objs:
                _merge_entry(
                    merged,
                    _chunk_entry(ch, score=None, strategy="object_lookup"),
                )
                seed_ids.append(ch.chunk_id)

        # 4) Parent + neighbor expansion
        neighbors = await _neighbor_chunks(retriever, list(dict.fromkeys(seed_ids)))
        for ch in neighbors:
            _merge_entry(
                merged,
                _chunk_entry(ch, score=None, strategy="neighbor"),
            )

        ranked = sorted(
            merged.values(),
            key=lambda x: (x.get("score") is not None, x.get("score") or 0.0),
            reverse=True,
        )
        return ranked[:50]
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

    claim_statuses = {c["status"] for c in claims_out}
    if not claims_out:
        gold_claim_status = "none"
    elif claim_statuses == {"supported"}:
        gold_claim_status = "supported"
    elif claim_statuses == {"corpus_gap"}:
        gold_claim_status = "corpus_gap"
    else:
        gold_claim_status = "mixed"

    # All items need human confirmation of min sufficient evidence set (C5).
    status = "needs_human_review"
    if not agree or disputes:
        status = "needs_human_review_disputed"
    if models.get("gold_family") == "stub":
        status = "stub_needs_human_review"

    return {
        "id": qid,
        "question": question,
        "status": status,
        "built_at": _utc_now(),
        "models": models,
        "pool_chunk_ids": [c["chunk_id"] for c in pool],
        "pool_size": len(pool),
        "pool_strategies": sorted(
            {s for c in pool for s in str(c.get("strategy") or "").split("+") if s}
        ),
        "gold": {
            "reference_answer": gold.get("reference_answer", ""),
            "claims": claims_out,
            "E_plus": e_plus,
            "eligible_for_crec": bool(e_plus),
            "gold_claim_status": gold_claim_status,
            # retrieval_gap is evaluated later vs each system's C; placeholder list empty.
            "retrieval_gap_vs_system": [],
        },
        "verify": verify,
        "disputes": disputes,
        "human_review": {
            "required": True,
            "task": "confirm_minimum_sufficient_evidence_set",
            "checklist": [
                "E⁺ 是否为支持参考答案 claims 的最小充分集",
                "是否有应进 E⁺ 却漏掉的 pool chunk",
                "corpus_gap claims 是否确为语料缺口",
            ],
            "confirmed": False,
        },
    }


def write_human_review_packet(results: list[dict[str, Any]]) -> Path:
    """Write review file for **all** items (not only model disputes). Audit C5."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REVIEW_DIR / f"gold_min_evidence_review_{ts}.md"
    lines = [
        f"# Gold 最小充分证据集人工复核 ({ts})",
        "",
        "范围：**全部题目**。任务 = 确认每题 E⁺ 是否为支持 claims 的最小充分集。",
        "模型分歧题额外标 `[DISPUTED]`。",
        "",
        f"题数：{len(results)}",
        "",
    ]
    for r in results:
        tag = ""
        if r.get("disputes") or "disputed" in str(r.get("status")):
            tag = " `[DISPUTED]`"
        if r.get("status") == "error":
            tag = " `[ERROR]`"
        lines.append(f"## {r['id']}{tag}: {r.get('question', '')}")
        lines.append(f"- status: {r.get('status')}")
        gold = r.get("gold") or {}
        lines.append(f"- gold_claim_status: {gold.get('gold_claim_status')}")
        lines.append(f"- E⁺ ({len(gold.get('E_plus') or [])}): "
                     f"{', '.join(gold.get('E_plus') or []) or '(none)'}")
        lines.append(f"- pool_size: {r.get('pool_size')} strategies={r.get('pool_strategies')}")
        lines.append(f"- reference_answer: {(gold.get('reference_answer') or '')[:300]}")
        for claim in gold.get("claims") or []:
            lines.append(
                f"  - claim `{claim.get('claim_id')}` [{claim.get('status')}]: "
                f"{claim.get('text')}"
            )
            lines.append(
                f"    evidence: {', '.join(claim.get('evidence_chunk_ids') or []) or '—'}"
            )
        for d in r.get("disputes") or []:
            lines.append(f"  - **dispute** `{d.get('claim_id')}`: {d.get('note')}")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        lines.append("- [ ] 人工确认最小充分证据集")
        lines.append("")
    # Also emit a disputes-only companion for quick triage.
    disputed = [
        r for r in results if r.get("disputes") or "disputed" in str(r.get("status"))
    ]
    if disputed:
        dpath = REVIEW_DIR / f"disputes_{ts}.md"
        dlines = [
            f"# Gold model disputes only ({ts})",
            "",
            f"n_disputed={len(disputed)} / total={len(results)}",
            "",
        ]
        for r in disputed:
            dlines.append(f"## {r['id']}: {r.get('question')}")
            for d in r.get("disputes") or []:
                dlines.append(f"- `{d.get('claim_id')}`: {d.get('note')}")
            dlines.append("")
        dpath.write_text("\n".join(dlines), encoding="utf-8")
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

    review_path = write_human_review_packet(results)
    return {
        "built_at": _utc_now(),
        "n": len(results),
        "review_path": str(review_path),
        "disputes_path": str(review_path),  # backward-compatible key
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
    print(
        f"wrote {args.out} n={payload['n']} "
        f"review={payload.get('review_path')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
