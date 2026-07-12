# Implementation Notes (MVP)

## Status

Skeleton + full MVP code paths implemented under `eval_methodology/mvp/`.

## Blockers / environment

1. **Milvus collection missing** (2026-07-12 local): after `./scripts/start-search-stack.sh`,
   `utility.list_collections()` was `[]`. Per MVP_PLAN, the runner **refuses to create**
   indexes and exits with a clear error. Full `--smoke` / `run_mvp` e2e needs a prebuilt
   `ServerConfig.milvus_collection` (default name from config, not hard-coded in logic).
2. **ES index also empty** in the same session. Gold high-recall and sidecar answers need both.
3. Rebuild indexes **outside** the MVP runner (`./scripts/rebuild-indexes.sh` or pipeline),
   then re-run smoke.

## Design choices locked to MVP_PLAN

| Topic | Choice |
|---|---|
| Candidate | `retrieval_auto_cross_ref_closure` off→on only |
| Ports | baseline 18080 / candidate 18081 |
| Metrics | Faith, CitP, CRec, unresolved_ref_rate |
| Bootstrap degrade | effective n **<15** or judge drop **>30%** |
| Judge units | fixed extract → dual judge same units |
| CRec C | e2e `retrievalContext` chunk ids (citable merge order) |
| Isolation | git dirty-set diff + `.env` sha256; allow new dirty only under `eval_methodology/` |

## How to run

```bash
# Unit tests (no Milvus required)
uv run pytest eval_methodology/mvp/tests -q

# Isolation snapshot only
uv run python eval_methodology/mvp/runner/sidecar.py --isolation-only

# Smoke (needs live collection + embedding/LLM)
uv run python eval_methodology/mvp/runner/sidecar.py --smoke

# Dataset
uv run python eval_methodology/mvp/dataset/normalize_labels.py
uv run python eval_methodology/mvp/dataset/split.py
# Gold (needs indices + codex/claude); spot-check 3:
uv run python eval_methodology/mvp/dataset/build_gold.py --limit 3
# Re-assemble dataset with gold:
uv run python eval_methodology/mvp/dataset/split.py --gold eval_methodology/mvp/data/gold.json

# Full MVP loop (expensive)
uv run python eval_methodology/mvp/loop/run_mvp.py --split dev
```

## Open questions (do not bypass by editing main project)

None blocking code structure. Operational: confirm where the production index lives if
not localhost docker (config already reads `.env` into `ServerConfig`).
