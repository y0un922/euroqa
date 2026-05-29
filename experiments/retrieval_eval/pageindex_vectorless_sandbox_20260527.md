# PageIndex Vectorless RAG Sandbox Comparison

Date: 2026-05-27

## Scope

This sandbox ports the core retrieval idea from `/Users/youngz/webdav/Euro_QA_pageindex` into the current project's `experiments/retrieval_eval/` directory only.

The external PageIndex project is read-only. No production retrieval code in `server/`, `pipeline/`, or `apps/` is modified.

## Imported Retrieval Idea

The PageIndex implementation is vectorless. Its core retrieval flow is:

- Load PageIndex workspace metadata and structure trees.
- Shortlist documents from metadata and document descriptions.
- Rank structure nodes using query terms and explicitly requested clause/object labels.
- Fetch line/page content from the selected structure ranges.
- Convert selected pages into current `Chunk` objects so existing retrieval metrics can be reused.
- Extract basic cross references from selected content and fetch matching structure nodes as `ref_chunks`.

This sandbox includes two modes:

- `deterministic`: local structure ranking without an LLM tool loop.
- `agent`: an Agents SDK tool loop that inspects document metadata, compact structure trees, and selected line ranges before returning evidence pages.

Both modes adapt their output into the current project's `Chunk` shape, so the same retrieval metrics can be reused.

## Commands

```bash
uv run python experiments/retrieval_eval/run_pageindex_sandbox.py \
  --workspace /Users/youngz/webdav/Euro_QA_pageindex/data/pageindex_workspace_md \
  --output experiments/retrieval_eval/results/pageindex-vectorless-sandbox_20260527.json \
  --compare-to experiments/retrieval_eval/results/embedding-compare_20260526_run1.json
```

Full-agent tool-loop mode:

```bash
PAGEINDEX_RETRIEVE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" \
PAGEINDEX_RETRIEVE_MODEL="qwen3.5-flash" \
uv run python experiments/retrieval_eval/run_pageindex_sandbox.py \
  --mode agent \
  --max-turns 8 \
  --workspace /Users/youngz/webdav/Euro_QA_pageindex/data/pageindex_workspace_md \
  --output experiments/retrieval_eval/results/pageindex-agent-sandbox_20260527.json \
  --compare-to experiments/retrieval_eval/results/embedding-compare_20260526_run1.json
```

## Indexed Documents

The tested PageIndex workspace currently contains only two Markdown documents:

| Document | Type | Lines |
|---|---:|---:|
| `EN1992-1-1_2004` | md | 7180 |
| `DG_EN1990` | md | 6157 |

This matters because the 30-question gold set expects `EN1992` for all questions, plus `EN1990` once and `DG_EN1992` twice. Missing `DG_EN1992` limits the maximum achievable score for guide-related questions.

## Overall Comparison

| Metric | BGE 3x mean | Qwen3 en-fill 3x mean | PageIndex deterministic | PageIndex full-agent | Agent vs BGE |
|---|---:|---:|---:|---:|---:|
| `doc_recall@10` | 0.9833 | 0.9778 | 0.9500 | 0.9500 | -0.0333 |
| `section_recall@1` | 0.3093 | 0.2945 | 0.2389 | 0.3278 | +0.0185 |
| `section_recall@3` | 0.4537 | 0.4454 | 0.3167 | 0.4972 | +0.0435 |
| `section_recall@5` | 0.5907 | 0.5870 | 0.4278 | 0.5028 | -0.0879 |
| `section_recall@10` | 0.6926 | 0.7333 | 0.5556 | 0.5028 | -0.1898 |
| `mrr_section` | 0.7186 | 0.6842 | 0.5650 | 0.7444 | +0.0258 |
| `ndcg@10` | 0.5789 | 0.5636 | 0.4432 | 0.5370 | -0.0419 |
| `direct_ref_resolution_rate` | 0.8861 | 0.9139 | 0.6667 | 0.8833 | -0.0028 |
| `keyword_recall@10` | 0.0356 | 0.0337 | 0.0206 | 0.0122 | -0.0234 |
| `concept_recall@10` | 0.0239 | 0.0239 | 0.0089 | 0.0000 | -0.0239 |
| `noise_intrusion_rate` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | +0.0000 |

## Full-Agent Category Summary

| Category | Count | `section_recall@10` | `mrr_section` | `ndcg@10` | Note |
|---|---:|---:|---:|---:|---|
| broad | 12 | 0.3403 | 0.7361 | 0.4019 | Good rank quality, still weak for multi-section coverage. |
| concept | 11 | 0.6970 | 0.8636 | 0.7108 | Strongest category; structure navigation works well. |
| parameter_lookup | 4 | 0.5833 | 0.7500 | 0.6173 | Direct lookups benefit from explicit object/page verification. |
| reasoning | 3 | 0.3333 | 0.3333 | 0.3333 | Small sample; this run underperformed on reasoning questions. |

## Interpretation

The deterministic vectorless PageIndex substrate is promising for concept-style questions where section titles and summaries carry the answer location. It is currently weaker than the existing BGE/Qwen hybrid retrieval on broad and multi-section questions, mainly because deterministic structure ranking does not perform the full agent loop's candidate exploration and verification.

The full-agent mode changes the trade-off rather than simply improving all metrics. It improves early-rank precision (`section_recall@1` rises to `0.3278`, above BGE's `0.3093`; `section_recall@3` reaches `0.4972`, above BGE's `0.4537`) and `mrr_section` exceeds BGE (`0.7444` vs `0.7186`). However, it returns fewer distinct evidence ranges, so `section_recall@10` remains lower (`0.5028` vs BGE's `0.6926`). In other words, the PageIndex agent behaves more like a precise navigator than a high-coverage retriever.

The strongest result is `direct_ref_resolution_rate`: full-agent mode reaches `0.8833`, almost matching BGE (`0.8861`) and much higher than deterministic mode (`0.6667`). This suggests the tool loop is useful for following explicit tables/annexes, but needs a coverage-oriented final selection policy.

Recommended next experiment:

- Rebuild or copy a PageIndex workspace that includes `DG_EN1992` and base `EN1990`.
- Repeat 3 runs because `analyze_query` remains non-deterministic.
- Add a hybrid PageIndex policy: agent selects high-confidence anchors, then deterministic structure expansion fills sibling/parent ranges to improve `section_recall@10`.
