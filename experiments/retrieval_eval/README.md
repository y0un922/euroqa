# retrieval_eval — 检索召回评测沙箱

完全隔离的 RAG 检索召回评测模块。**与 `server/` / `pipeline/` / `tests/eval/` / `shared/` 业务模块零代码侵入**，删除整个目录即可彻底回滚。

## 用法

### 1. 数据集转换（一次性）

```bash
python3 -m experiments.retrieval_eval.dataset.convert \
  --input golden_dataset_reviewed.xlsx \
  --output experiments/retrieval_eval/dataset/test_questions_v2.json
```

将「修订版基线建议」+「逐题审查」+ 原始问题文本合并为 v2 schema（30 题）。每题含：
- `expected_documents:[{doc, sections, objects}]` — 跨文档金标
- `expected_sections` — 所有文档章节的 flat 兼容字段
- `expected_keywords` / `expected_concepts` / `expected_answer_points` / `expected_formulas`
- `review_bucket` — 通过 / 小幅修改 / 中等修改 / 重大修改
- `category` — broad / exact_ref / parameter_lookup / reasoning / concept
- `notes` — 原始未审查字段做溯源参考

### 2. 跑 baseline 评测（待实施）

```bash
uv run python experiments/retrieval_eval/run_baseline.py --top-k 10
# 输出 results/baseline_<date>.json
```

需要本地 Milvus + Elasticsearch 启动。

### 3. 分诊报告（待实施）

```bash
python3 experiments/retrieval_eval/triage.py results/baseline_<date>.json
# 输出 results/triage_<date>.md
```

### 4. 零侵入验证

```bash
bash experiments/retrieval_eval/verify_isolation.sh
```

## 前置条件

- `golden_dataset_reviewed.xlsx`（项目根目录，已有）
- Milvus（默认 `localhost:19530`，collection `eurocode_chunks`）
- Elasticsearch（默认 `http://localhost:9200`，index `eurocode_chunks`）
- BGE-M3 embedding model（可本地或远程，由 `server.config` 决定）
- BGE Reranker v2-m3

## 删除影响

```bash
rm -rf experiments/retrieval_eval
```

这之后：
- ✅ `server/` 任何业务接口仍可启动（不依赖本目录）
- ✅ `tests/eval/eval_retrieval.py` 仍可跑（独立的 v1 评测）
- ✅ `pipeline/` 索引、`tests/` 单测均不受影响

## 内部依赖风险

本沙箱通过 `import` 调用业务代码的**内部方法**：
- `server.core.retrieval.HybridRetriever._vector_search` / `_bm25_search` / `_rrf_fuse_results` / `_rerank`
- `server.core.query_understanding.analyze_query`
- `server.config.ServerConfig`

如果业务 refactor 这些内部方法签名，`trace/wrapper.py` 必须同步更新。详见 `.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/retrieval-internals.md`。

## 目录布局

```
experiments/retrieval_eval/
  __init__.py
  .gitignore                # results/ 被 ignore
  README.md
  dataset/
    schema.py               # QuestionV2 dataclass
    convert.py              # xlsx → v2 json
    test_questions_v2.json  # 30 题金标
  metrics/                  # 8 个指标 + 三维分桶（Step 2，待实施）
  trace/                    # 分阶段 trace wrapper（Step 3，待实施）
  results/                  # 评测结果（git-ignored）
  runner.py                 # 通用 runner（Step 3）
  run_baseline.py           # 主入口（Step 3）
  triage.py                 # 分诊报告（Step 4）
  verify_isolation.sh       # 零侵入校验（Step 5）
```

## 设计文档

- PRD：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/prd.md`
- Codex 接力 brief（Step 2-5 实施指南）：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/codex-handoff.md`
- HybridRetriever 内部方法签名（trace wrapper 参照）：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/retrieval-internals.md`

## 不依赖新 PyPI 包

本沙箱不引入新的 `pyproject.toml` 依赖。所有 import 都使用项目已有的包：
`openpyxl`（system python 已装）、`structlog`、`pymilvus`、`elasticsearch`、`FlagEmbedding`、`FlagReranker`。
