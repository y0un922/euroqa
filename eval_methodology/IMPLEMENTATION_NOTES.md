# Implementation Notes (MVP)

## Audit response (codex 2/5 → fixes)

Codex must-fix items were verified correct and addressed in code:

| ID | Issue | Fix |
|---|---|---|
| B2 | weak L4 (`urr>0`) + set-based context diff | L4 requires `urr ≥ 0.15`; context compare is **ordered sequence** |
| C1 | `retrieval_gap` not wired | per-question `retrieval_gap_ids` in metrics + raw eval |
| C4 | gold only fused retrieve | independent BM25 + vector + `lookup_object` + parent/sibling neighbors |
| C5 | review only disputes | **all** items written to `review/gold_min_evidence_review_*.md` |
| D2 | citation drop kept Faith | full question drop nulls Faith **and** CitP; aggregate excludes dropped |
| D3 | silent regex JSON salvage | regex fallback `ok=False` → CLIJudgeError; Claude `--no-session-persistence` |
| D4 | cache model placeholder | cache key uses resolved model id (env + CLI banner/envelope) |
| E2 | no per-question Δ | report §4.1 paired delta tables |
| E3 | Faith-only final decision | `merge_hard_gate_decisions(Faith, CitP)` + CRec regression reject |
| F3 | trivial accept/reject tests only | added CI-crossing inconclusive + merge tests |
| G3 | gate bypass paths | closed by B2 + E3 |

## Still blocked for live A1 / G1 (environment)

Local Milvus after `start-search-stack` still has **no collection**. Smoke correctly fails:

```text
Milvus collection '<ServerConfig.milvus_collection>' does not exist ... Refusing to create indexes
```

Until indexes are rebuilt **outside** MVP:

```bash
./scripts/rebuild-indexes.sh   # or pipeline
uv run python eval_methodology/mvp/runner/sidecar.py --smoke
uv run python eval_methodology/mvp/dataset/build_gold.py --limit 3   # then full
uv run python eval_methodology/mvp/loop/run_mvp.py --split dev
```

## How to run offline checks

```bash
uv run pytest eval_methodology/mvp/tests -q
uv run python eval_methodology/mvp/runner/sidecar.py --isolation-only
```

## Design locks (unchanged)

- Candidate: `retrieval_auto_cross_ref_closure` off→on only
- Ports 18080 / 18081; never write `.env`
- Main project untouched; only `eval_methodology/`
