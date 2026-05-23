# retrieval_eval — 检索召回评测沙箱

完全隔离的 RAG 检索召回评测模块。**与 `server/` / `pipeline/` / `tests/eval/` / `shared/` 业务模块零代码侵入**，删除整个目录即可彻底回滚。

## Usage

### 1. 数据集转换（一次性）

```bash
uv run python -m experiments.retrieval_eval.dataset.convert \
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

### 2. 跑 baseline 评测

```bash
uv run python experiments/retrieval_eval/run_baseline.py \
  --top-k 10 \
  --questions experiments/retrieval_eval/dataset/test_questions_v2.json \
  --output experiments/retrieval_eval/results/baseline_manual.json
```

不传 `--output` 时默认输出 `experiments/retrieval_eval/results/<exp>_<date>.json`。
可用 `--exp smoke|baseline|high-recall|no-rerank|no-cap|rerank-english|rerank-fill` 切换短反馈实验配置。

- `rerank-english`: 保持候选池和 rerank 开启，但强制 rerank query 使用 `expanded_queries[0]`，用于验证中文 rerank query 对英文 chunks 的跨语言错配假设。
- `rerank-fill`: rerank 只选前 5 个，再按原候选顺序补齐到 top10，用于验证“排序质量 + 覆盖多样性”组合策略。

### 3. 分诊报告

```bash
uv run python experiments/retrieval_eval/triage.py \
  experiments/retrieval_eval/results/baseline_manual.json
```

不传 `--output` 时默认输出 `experiments/retrieval_eval/results/triage_<date>.md`。

### 4. 零侵入验证

```bash
bash experiments/retrieval_eval/verify_isolation.sh
```

如果 task 起点不是当前 `master` merge-base，可显式指定：

```bash
TASK_START_REF=<sha> bash experiments/retrieval_eval/verify_isolation.sh
```

## Prerequisites

- `golden_dataset_reviewed.xlsx`（项目根目录，已有）
- `openpyxl`：仅数据集转换需要；本 task 不修改 `pyproject.toml`，缺失时请在运行环境预装
- Milvus：默认 `localhost:19530`，collection `eurocode_chunks`
- Elasticsearch：默认 `http://localhost:9200`，index `eurocode_chunks`
- BGE-M3 embedding model（可本地或远程，由 `server.config` 决定）
- BGE Reranker v2-m3

如果使用本项目 Docker Compose 栈，先确认服务已启动：

```bash
docker compose ps
```

baseline 需要 Milvus / Elasticsearch / embedding / rerank 均可用；否则 runner 会在每题 `error` 字段记录异常。

## Deletion Impact

```bash
rm -rf experiments/retrieval_eval
```

这之后：
- `server/` 任何业务接口仍可启动（不依赖本目录）
- `tests/eval/eval_retrieval.py` 仍可跑（独立的 v1 评测）
- `pipeline/` 索引、`tests/` 单测均不受影响
- 已生成的 `experiments/retrieval_eval/results/*` 会随目录删除；这些结果默认不进 git

## Internal Dependencies Risks

本沙箱通过 `import` 调用业务代码的**内部方法**：
- `server.core.retrieval.HybridRetriever._vector_search`
- `server.core.retrieval.HybridRetriever._bm25_search`
- `server.core.retrieval.HybridRetriever._rrf_fuse_results`
- `server.core.retrieval.HybridRetriever._cross_doc_aggregate`
- `server.core.retrieval.HybridRetriever._rerank`
- `server.core.retrieval.HybridRetriever._fetch_cross_ref_chunks`
- `server.core.retrieval.HybridRetriever._fetch_object_chunks_by_object_ids`
- `server.core.query_understanding.analyze_query`
- `server.config.ServerConfig`

如果业务 refactor 这些内部方法签名，`trace/wrapper.py` 必须同步更新。`TracingHybridRetriever` 是单线程评测 wrapper，不应复用到 ASGI worker 或线上请求链路。详见 `.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/retrieval-internals.md`。

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
  metrics/                  # 8 个指标 + 三维分桶
  trace/                    # 分阶段 trace wrapper
  results/                  # 评测结果（git-ignored）
  runner.py                 # 通用 runner
  run_baseline.py           # 主入口
  triage.py                 # 分诊报告
  triage_rules.py           # 5 类失败模式规则
  verify_isolation.sh       # 零侵入校验
```

## 设计文档

- PRD：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/prd.md`
- Codex 接力 brief（Step 2-5 实施指南）：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/codex-handoff.md`
- HybridRetriever 内部方法签名（trace wrapper 参照）：`.trellis/tasks/05-22-retrieval-recall-eval-sandbox/research/retrieval-internals.md`

## 不依赖新 PyPI 包

本沙箱不引入新的 `pyproject.toml` 依赖。除转换脚本需要运行环境提供 `openpyxl` 外，其余 import 都使用项目已有的包：`structlog`、`pymilvus`、`elasticsearch`、`FlagEmbedding`、`FlagReranker`。
