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
| `dataset/` | Excel labels; Codex→Claude→Codex gold workflow; fixed split 16/9/6 |
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
uv run python eval_methodology/mvp/dataset/build_gold.py --limit 3 \
  --out /tmp/euroqa_gold_sample.json --review-dir /tmp/euroqa_gold_review
uv run python eval_methodology/mvp/dataset/split.py --gold /tmp/euroqa_gold_sample.json

uv run python eval_methodology/mvp/loop/run_mvp.py --split dev
```

`build_gold.py` requires Markdown standards/guides under `data/parsed`. It first
copies Markdown into a temporary corpus outside the repository. Codex and Claude
start from separate neutral temporary working directories and mount that external
copy, so project `AGENTS.md`/`CLAUDE.md` are not inherited. Codex uses
`gpt-5.6-terra` with low reasoning; gold CLI calls allow up to 900 seconds and kill
their whole process group on timeout. Claude reviews with only Read/Grep/Glob and
keeps the installed CLI's OAuth/keychain authentication.
The artifact records CLI interface separately from the resolved model and inferred
provider family; a Claude CLI configured to use GLM is therefore not mislabeled as
an Anthropic-family verifier.
The gold stage never calls the application retriever or indexes. Failed review is
returned to Codex for at most two repairs. Generated evidence uses exact corpus
locators and remains CRec-ineligible until human minimum-sufficient-set confirmation.

After checking the generated review packet, persist confirmation explicitly:

```bash
uv run python eval_methodology/mvp/dataset/build_gold.py \
  --out /tmp/eval_methodology_gold.json --confirm all --reviewer <name>
```

Any per-question build error is retained in the output for diagnosis and makes the
command exit non-zero.

See `../IMPLEMENTATION_NOTES.md` for blockers (empty local index) and design locks.
