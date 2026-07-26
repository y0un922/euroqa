# MVP v2 实施说明(定稿,供实现)

目标:把 `eval_methodology/mvp/` 收敛为"答案逐题落盘 → 单 judge → 三态判定"的直线管线。
删双 judge、删 gold 构建管线、删重复答案生成;保留 sidecar 隔离、缓存、bootstrap 三态判定。
本说明只涉及代码(P0–P2),`main.tex` 修订另行处理。

## 0. 硬约束

- 不修改 `server/`、`pipeline/`、`shared/`、主项目 `.env`、`tests/`(主项目测试)——所有改动限于 `eval_methodology/` 内。
- Python 3.12,`uv run` 运行;只用标准库 + 项目已有依赖(httpx、pydantic);不引入新依赖。
- 被删除的能力不留空壳函数/兼容分支;git 历史即存档。
- 每步完成后 `uv run ruff check eval_methodology` 与 `uv run pytest eval_methodology/mvp/tests` 必须通过。

## 1. 删除清单(直接删除文件/代码)

| 目标 | 动作 |
|---|---|
| `mvp/metrics/judges/dual_judge.py` | 删除(由新 `judge.py` 替代) |
| `mvp/metrics/judges/extract.py` | 删除(extract 折进 judge 单次调用) |
| `mvp/schemas/extract_units.schema.json` | 删除 |
| `mvp/dataset/build_gold.py`、`gold_corpus.py`、`normalize_labels.py`、`xlsx_io.py`、`split.py` | 删除(`data/*.json` 为冻结资产,保留) |
| `mvp/tests/test_gold_cli_pipeline.py`、`mvp/tests/test_judge_and_gates.py` | 删除 |
| `run_mvp.py` 中 `_context_diff_scan` | 删除,改为对已存答案做内存 diff(见 §4) |
| `run_eval.py` 中 offline-stub judge(`use_llm_judge=False` 时造 Faith=1.0 假值的分支) | 删除;`--no-judge` 改为只算确定性指标,Faith/CitP 置 None |
| `sidecar.py` 中 `SidecarSession` | 删除(死代码) |
| `cli_backend.py` 中 codex stdout banner 模型嗅探(`re.search(r"model[=:\s]+…")`)与 regex salvage(`allow_regex_fallback`)分支 | 删除;解析失败即抛 `CLIJudgeError` |
| `decision.py` 中 self-noise 默认门(`abs(ci.mean) <= noise` 分支)、`merge_hard_gate_decisions` 的 `regression_metrics` 分支、`ab_decide` 的 `baseline_repeat_*`/`judge_drop_rate`/`degraded_to_trend` 参数 | 删除/简化(见 §5);self_noise_bound 保留在 bootstrap.py,仅 `--repeats 2` 时计算并写入报告,不参与判定 |
| `mvp/metrics/schemas.py` 中 `DEFERRED_METRICS` 及 render 对应章节 | 删除 |

保留不动:`sidecar.py` 其余、`runner/client.py`、`candidate.py`、`isolation.py`、`metrics/diagnostics.py`、`metrics/bootstrap.py`、`metrics/judges/cache.py`。

## 2. 新增 `mvp/runner/answers.py`(~150 行)

```python
def generate_answers(handle, items, run_dir: Path, *, concurrency: int = 2,
                     retries: int = 1, timeout_s: float = 180.0) -> list[dict]
def load_answers(run_dir: Path) -> dict[str, dict]   # qid -> record
```

- ThreadPoolExecutor(concurrency) 并发调 `runner.client.query_stream`。
- 每题完成**立即**写 `run_dir/<qid>.json`:含 question、answer、context_chunk_ids、context_chunks、sources、unresolved_refs、resolved_refs、elapsed_ms、`usage`(从 `raw_done` 里取,若无则 None)、status(`ok`/`error`)、error 信息。
- **断点续跑**:启动时若 `<qid>.json` 已存在且 status=ok 则跳过。
- 单题失败重试 `retries` 次,仍失败记 status=error 后继续下一题,不中断整轮。
- run_dir 布局:`mvp/artifacts/runs/<run_id>/answers/<variant>/<qid>.json`,`run_id` 由调用方给。

## 3. 新增 `mvp/metrics/judges/judge.py`(~120 行,替代 dual_judge+extract)

- 单族单次调用:默认 `run_claude_json`(`claude -p --json-schema --no-session-persistence`,禁工具);环境变量 `MVP_JUDGE_FAMILY=codex` 可切到 `run_codex_json`(临时目录、`--ephemeral -s read-only`)。
- `schemas/judge_output.schema.json` 改为合并 schema:
  ```json
  {"claims": [{"text": "...", "supported": true}],
   "citations": [{"ref_label": "Ref-1", "valid": true}]}
  ```
- Prompt:问题 + 答案 + 有序 context(前 30 chunk × 800 字符,沿用原 `_judge_prompt` 截断);要求模型自行把答案拆成原子 claims 并逐条判 supported;引用单元按 `[Ref-N]` 判 valid。
- 计算:Faith = supported 均值(claims 空 → None);无 citations 且答案非空 → CitP=0.0,否则 CitP = valid 均值。
- 超时 180s,重试 1 次(复用 `run_with_retry`);最终失败 → 返回 `judge_failed=True`,Faith/CitP=None。
- 缓存:沿用 `cache.py` 内容寻址(键含 family、resolved model id、prompt/schema 版本、question、answer、context hash);`PROMPT_SCHEMA_VERSION` 递增。
- 返回 dataclass `JudgeResult(faith, citp, n_claims, n_citations, judge_failed, fail_reason, resolved_model, family)`。

## 4. 改 `loop/run_mvp.py`:子命令 + 新流程

```
run_mvp.py baseline --split dev [--limit N] [--no-judge] [--fresh] [--repeats 1]
run_mvp.py compare  --split dev [--limit N] [--no-judge] [--fresh] [--gate-n 12]
```

- **baseline**:缓存键 = `git rev-parse HEAD` + baseline CandidateConfig 哈希 + `MVP_DATASET_VERSION`;`mvp/artifacts/runs/` 下有同键完成品且非 `--fresh` → 直接复用。否则起 sidecar 跑 answers → judge → 确定性指标 → 聚合 → 落盘。
- **compare** 流程(顺序关键):
  1. 取/跑 baseline(judge 结果走缓存);
  2. `locate_bottleneck`(保留现逻辑)+ `pick_single_var_action` + `candidate_precheck` 的 L4 门(unresolved_ref_rate ≥ 0.15);
  3. 起 candidate sidecar 跑 **candidate answers**(逐题落盘);
  4. **内存 diff 门**:新纯函数 `context_diff_from_answers(base_answers, cand_answers) -> (diff_ids, details)`,比较有序 chunk-id 序列;变化题数 < `CONTEXT_DIFF_MIN_QUESTIONS`(3)→ 判 inconclusive("候选未改变检索路径"),**不进 judge**,直接出报告;
  5. judge candidate(只 judge candidate 一侧;baseline 已缓存);
  6. `ab_decide`(faith 主指标 improve 模式 + citp non_regress 门)→ `merge` → 报告。
- 每阶段(answers/judge/decide/report)计时,print 且写入 payload `stage_timings`;每题完成后 payload checkpoint 增量落盘(覆盖写同一 json)。
- 基线×2 不再默认:`--repeats 2` 时对 baseline 跑两遍,`self_noise_bound` 结果仅写入报告展示。

## 5. 改 `loop/decision.py`

- `ab_decide(baseline_values, candidate_values, *, primary_metric, epsilon=0.05, delta=0.05, gate_n=12, mode)`:
  - n < gate_n → inconclusive;
  - CI 全低于 −δ → reject;
  - improve 模式:CI 全高于 +ε → accept;CI 宽 > 0.1 → inconclusive(exploratory);其余 inconclusive;
  - non_regress 模式:未证显著回归 → accept;CI 宽 > 0.1 → inconclusive。
- `merge_hard_gate_decisions(per_metric, primary_metric="faith", non_regress_metrics=("citp",))`:任一 reject → reject;primary accept 且 citp 非回归 → accept;否则 inconclusive。
- `MetricSnapshot`/`locate_bottleneck`/`candidate_precheck` 保留;`judge_drop_rate` 语义改为 `judge_fail_rate`(judge 调用失败率),>30% → 聚合标 `degraded_to_trend`(只影响报告措辞,不再作为 ab_decide 参数)。

## 6. 改 `metrics/run_eval.py` 与 `metrics/e2e.py`

- `eval_on_sidecar` 拆分:答案获取委托 `answers.generate_answers`;指标计算改为独立函数 `metrics_from_answers(answers, items, *, use_llm_judge)`(对每题:judge.judge_question 或跳过 + diagnostics CRec/urr)。
- CRec 资格判断 `_evidence_for_crec` 改为:`item["gold"]["gold_claim_status"] == "supported"` 且 evidence 非空即 eligible,**删除 `gold_human_review.confirmed` 门**。
- `aggregate` 保留,`judge_drop_rate` 改名 `judge_fail_rate`,`crec_eligible_n` 保留。

## 7. 一次性数据合并(先执行,脚本不入库)

写临时脚本把 `mvp/data/gold.json` 中 `status=="supported"` 的 15 题的 `gold`(含 evidence quotes)合并进 `mvp/data/dataset.json` 对应 item 的 `gold` 字段,并设 `item["gold"]["gold_claim_status"]="supported"`;mixed/corpus_gap 不合并。合并后验证:dataset.json 中 eligible 题数 == 15。脚本跑完删除,dataset.json 的 diff 入库。

## 8. 改 `reports/render.py`

- 指标表:Faith / CitP / unresolved_ref_rate / CRec(标注"模型交叉复审 gold,未人工确认,仅诊断")。
- 新增:阶段耗时表;逐题状态表(qid、faith、citp、urr、crec、elapsed_ms、status ok/judge_failed/error);ops 行(平均时延、token 合计、judge_fail_rate)。
- 删除 DEFERRED_METRICS 章节;resolved model 如实展示(不称"双家族")。

## 9. 测试(`mvp/tests/`)

保留并适配:`test_ab_decide.py`(删 self-noise/drop-rate 用例,补 gate_n 参数化用例)、`test_candidate_and_isolation.py`(删 `SidecarSession` 相关如有)。
新增:
- `test_answers_resume.py`:mock `query_stream`,断言逐题落盘、二次运行跳过 status=ok 的题、单题失败不中断。
- `test_judge_parse_and_fail.py`:mock `run_claude_json`,断言 Faith/CitP 计算、无引用→CitP=0、失败→judge_failed 且指标 None、缓存命中不再调用。
- `test_context_diff_from_runs.py`:纯函数 diff 门(顺序变化也算 diff;<3 题 → 门不过)。
全部 mock,不打网络、不起 sidecar。

## 10. 验收标准

1. `uv run python -m eval_methodology.mvp.loop.run_mvp baseline --split dev --limit 2 --no-judge` 在无外部 LLM 依赖下完成(需本地 Milvus/ES 与后端可用),逐题 json 落盘,中断重跑跳过已完成题。
2. `run_mvp.py compare --split dev` 全流程可运行,diff 门不过时不调用任何 judge。
3. `uv run pytest eval_methodology/mvp/tests` 全绿;`uv run ruff check eval_methodology` 无错。
4. 报告(md+json)含:逐题结果、核心指标、版本差值、阶段耗时、三态判定与理由。
5. `rg -l "dual_judge|extract_units|build_gold|SidecarSession" eval_methodology/mvp` 无残留引用。
