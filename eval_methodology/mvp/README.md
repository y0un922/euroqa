# Eval Methodology MVP

Implements the shortest closed loop from `eval_methodology/MVP_PLAN.md`:

**dataset → Faith/CitP/CRec/unresolved_ref_rate → LocateBottleneck → precheck → one A/B → report**

Isolation: only `eval_methodology/` may change; sidecars inject env overrides (never write `.env`).

## Layout

| Path | Role |
|---|---|
| `runner/sidecar.py` | Bypass uvicorn on 18080/18081 + isolation assert |
| `runner/client.py` | `/api/v1/query/stream` SSE client; C from retrievalContext |
| `candidate.py` | Whitelist `CandidateConfig` → ServerConfig → env |
| `dataset/` | Excel labels, gold E⁺, fixed split 16/9/6 |
| `metrics/` | Faith/CitP judges, CRec, bootstrap, `run_eval.py` |
| `loop/decision.py` | LocateBottleneck / precheck / ABDecide |
| `loop/run_mvp.py` | Single-iteration orchestrator |
| `reports/render.py` | Markdown report with 95% CI |
| `tests/` | AB three-state + isolation unit tests |

## Quick commands

```bash
uv run pytest eval_methodology/mvp/tests -q
uv run python eval_methodology/mvp/runner/sidecar.py --isolation-only
uv run python eval_methodology/mvp/runner/sidecar.py --smoke   # needs Milvus collection

uv run python eval_methodology/mvp/dataset/normalize_labels.py
uv run python eval_methodology/mvp/dataset/build_gold.py --limit 3
uv run python eval_methodology/mvp/dataset/split.py --gold eval_methodology/mvp/data/gold.json

uv run python eval_methodology/mvp/loop/run_mvp.py --split dev
```

See `../IMPLEMENTATION_NOTES.md` for blockers (empty local index) and design locks.
