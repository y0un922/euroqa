# Eval 体系说明

本目录包含三类评测：

- 检索侧 eval：`eval_retrieval.py` 调用本地检索链路，评估 section、keyword、grounded mode、cross-ref closure 等指标。需要 Milvus 和 Elasticsearch 在线。
- 生成侧特征化快照：`test_characterization_generation.py` 对 generation 纯 helper 做离线 snapshot，记录当前行为，适合作为 CI/本地门禁。
- 生成侧活跑：`eval_generation.py` 调用在线 `POST /api/v1/query/stream`，收集完整回答并评估引用、groundedness 和关键词命中。需要 Milvus、Elasticsearch、LLM 和后端服务在线，不作为 CI 门禁。

## 如何运行

一键离线门禁：

```bash
uv run python scripts/eval_gate.py
```

只跑检索基线比较：

```bash
uv run python tests/eval/compare_baseline.py
```

重新生成检索结果：

```bash
uv run python tests/eval/eval_retrieval.py
```

只跑生成侧特征化快照：

```bash
uv run python -m pytest tests/eval/test_characterization_generation.py
```

跳过快照，只比较检索基线：

```bash
uv run python scripts/eval_gate.py --skip-snapshots
```

手动活跑生成侧评测：

```bash
uv run python tests/eval/eval_generation.py --api-url http://127.0.0.1:18080
```

## 如何更新基线

检索侧基线：

- 确认 Milvus 和 Elasticsearch 中的数据版本正确。
- 运行 `uv run python tests/eval/eval_retrieval.py` 生成 `tests/eval/eval_results.json`。
- 人工检查结果后，将 `eval_results.json` 的 `metadata`、`config`、`metrics` 复制到 `tests/eval/baselines/retrieval_baseline.json`。

生成侧特征化快照：

- 当 generation helper 行为变更是预期结果时，删除对应的 `tests/eval/snapshots/*.json`。
- 重新运行 `uv run python -m pytest tests/eval/test_characterization_generation.py`，测试会生成新的 snapshot。
- 人工 review JSON diff 后提交。

生成侧活跑基线：

- 启动后端服务，并确保 Milvus、Elasticsearch、LLM 可用。
- 运行 `uv run python tests/eval/eval_generation.py`。
- 输出写入 `tests/eval/baselines/generation_baseline.json`，该文件用于周期性人工检查，不进入一键门禁。

## 容差含义

`compare_baseline.py` 默认使用 `metadata.tolerance = 0.02`。对越高越好的指标，`-0.02` 表示当前结果允许比基线略低 0.02；例如基线 0.90 时，当前 0.88 仍可通过。对越低越好的指标，例如 `noise_intrusion_rate`，当前值允许比基线略高 0.02。

## 在线依赖

- 不需要在线服务：`scripts/eval_gate.py` 中的快照测试；`compare_baseline.py` 只比较已有 JSON 文件。
- 需要 Milvus + Elasticsearch：`eval_retrieval.py`。
- 需要 Milvus + Elasticsearch + LLM + 后端服务：`eval_generation.py`。
