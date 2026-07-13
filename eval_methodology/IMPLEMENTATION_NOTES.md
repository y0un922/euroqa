# Implementation Notes (MVP)

## Audit response (codex 2/5 → 4/5 → residuals closed)

Codex must-fix items were verified correct and addressed in code.
HelloAGENTS re-verify of `be90591`: B2/C1/C4/C5/D2/D3/E2/F3/G3 pass; A1 smoke pass
with live index. Residuals D4/E3 closed in follow-up commit:

| ID | Issue | Fix |
|---|---|---|
| B2 | weak L4 (`urr>0`) + set-based context diff | L4 requires `urr ≥ 0.15`; context compare is **ordered sequence** |
| C1 | `retrieval_gap` not wired | per-question `retrieval_gap_ids` in metrics + raw eval |
| C4 | gold only fused retrieve | superseded: Codex directly reads full `data/parsed`; no RAG/index dependency |
| C5 | review only disputes | **all** items written to `review/gold_min_evidence_review_*.md` |
| D2 | citation drop kept Faith | full question drop nulls Faith **and** CitP; aggregate excludes dropped |
| D3 | silent regex JSON salvage | regex fallback `ok=False` → CLIJudgeError; Claude `--no-session-persistence` |
| D4 | cache miss under `codex-unresolved` | pin resolved model (process+disk); lookup uses pin; provisional alias write-once |
| E2 | no per-question Δ | report §4.1 paired delta tables |
| E3 | Faith-only / flat hard-gate blocks | primary `improve` + hard `non_regress` (flat = pass); merge rejects only on reject |
| F3 | trivial accept/reject tests only | CI-crossing + merge + non_regress flat tests |
| G3 | gate bypass paths | closed by B2 + E3 |

## Still blocked for live A1 / G1 (environment)

Local Milvus after `start-search-stack` still has **no collection**. Smoke correctly fails:

```text
Milvus collection '<ServerConfig.milvus_collection>' does not exist ... Refusing to create indexes
```

The sidecar still needs an existing index. Gold generation does not; it only needs
Markdown files under `data/parsed` plus authenticated Codex and Claude CLIs.

The direct-corpus gold path was smoke-tested on one external fixture: Codex generated
a schema-valid locator gold and Claude independently approved it (`n_errors=0`,
`status=needs_human_review`). The run resolved Codex as `gpt-5.6-terra` and the model
behind the Claude CLI as `glm-5.2:cloud[1m]`; artifacts therefore record CLI interface
separately from the actual model family. Smoke outputs were written only under `/tmp`.
Both CLI subprocesses bind stdin to `DEVNULL`, run in a dedicated process group, and
terminate that group on timeout. Gold calls use a 900-second timeout; judge calls keep
their 300-second default.

A full 31-question run completed with `n_errors=0` and wrote
`mvp/data/gold_cli_terra_20260713.json`. Of the 31 questions, 23 reached
`needs_human_review` and 8 exhausted the two repair rounds as
`review_not_converged`; none are CRec-eligible until explicit human confirmation.
The all-question review packet is under `review/gold_cli_terra_20260713/`.

Until indexes are rebuilt **outside** MVP, sidecar commands remain blocked:

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
