# Eval Methodology MVP

Implements the shortest closed loop from `eval_methodology/MVP_PLAN.md`:

**stored answers → Faith/CitP/CRec/unresolved_ref_rate → one A/B → report**

Isolation: only `eval_methodology/` may change; sidecars inject env overrides (never write `.env`).

## Layout

| Path | Role |
|---|---|
| `runner/sidecar.py` | Bypass uvicorn on 18080/18081 + isolation assert |
| `runner/client.py` | `/api/v1/query/stream` SSE client; C from retrievalContext |
| `runner/answers.py` | Concurrent per-question answer checkpoints + resume |
| `candidate.py` | Whitelist `CandidateConfig` → ServerConfig → env |
| `data/` | Frozen dataset, split, labels, and reviewed gold assets |
| `metrics/` | Single-family Faith/CitP judge, CRec, bootstrap, `run_eval.py` |
| `loop/decision.py` | LocateBottleneck / precheck / ABDecide |
| `loop/run_mvp.py` | Single-iteration orchestrator |
| `reports/render.py` | Markdown report with 95% CI |
| `tests/` | AB three-state + isolation unit tests |

## Quick commands

```bash
uv run pytest eval_methodology/mvp/tests -q
uv run python eval_methodology/mvp/runner/sidecar.py --isolation-only
uv run python eval_methodology/mvp/runner/sidecar.py --smoke   # needs Milvus collection

uv run python -m eval_methodology.mvp.loop.run_mvp baseline --split dev --no-judge
uv run python -m eval_methodology.mvp.loop.run_mvp compare --split dev
```

See `../IMPLEMENTATION_NOTES.md` for blockers (empty local index) and design locks.
