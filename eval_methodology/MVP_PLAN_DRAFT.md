# 评估方法论 MVP 实施方案（草案 v0，待 codex 互审）

> 靶子文档：`eval_methodology/main.tex`。本草案目的：**验证方法论可行**，不是一次铺开全部指标。
> 评审纪律：claude 起草 ↔ codex 对抗审阅，双方公正、不偏袒，逐条给理由。

---

## 0. 目标与切片厚度

- **目的**：跑通 `main.tex` 描述的"数据集构建 → 指标评估 → 迭代优化"一条最短闭环，证明三根支柱都能落地，且**迭代与主程序独立**（调参不改/复原主项目）。
- **切片厚度（claude 决定：薄而完整的一刀）**：
  - 数据集：归一化 31 题人工标签 → 建 **dev 集（约 15 题）+ gold**（test/holdout 划分写入但不在本 MVP 跑）。
  - 指标：实现 **"立即可算"子集**（Faith、CitP、Match、τ）+ **一个诊断指标**（CRec，依赖 gold evidence）；其余指标（Comp/Corr/CPrec/Noise/ECov/RDeg）留接口与签名，不实现。
  - 迭代：跑 **基线 vs 1 个候选**（`vector_top_k` 30→50）一次 A/B，配对 bootstrap 三态判定。
- **成功判据**（可验证）：
  1. 候选配置运行全程未写 `.env`、未改 `server/` 任何文件（`git status` 主项目零脏动）。
  2. 产出一份带 95% CI 的量化对比报告（给甲方看的那种）。
  3. A/B 判定能给出 accept/reject/inconclusive 之一并附 reason。
  4. gold 生成与 judge 全程走 `codex`/`claude` CLI，两族分离可追溯。

---

## 1. 隔离架构（本方案核心）

主项目配置从 `.env` 读、`get_retriever()` 是进程级 `lru_cache`，无法逐请求换配。故两条路径都**旁路**主项目：

### 1.1 端到端指标（Faith/CitP/Match）——旁路后端实例
- 候选配置 `c = {vector_top_k: 50, ...}` 由 eval 侧持有，**不落 `.env`**。
- `runner/sidecar.py`：`subprocess.Popen(["uv","run","uvicorn","server.main:app","--host","127.0.0.1","--port",P], env={**os.environ, "VECTOR_TOP_K":"50",...})`，alt 端口（基线 18080 / 候选 18081）。
- pydantic-settings env 优先级高于 `.env` 文件 → 子进程拿候选配置；主 `.env` 与 `server/` 源码零改动。
- eval 跑完 `terminate()` 子进程。Milvus/ES 共用主项目实例（只读查询，无写入风险）。
- 复用现有 `run_eval_dataset.py` 的 `/api/v1/query/stream` 调用与产物解析逻辑（抽公共函数，不改原技能文件）。

### 1.2 诊断指标（CRec）——进程内 retriever
- `runner/diag_runner.py`：`cfg = get_config().model_copy(update=c)；retriever = HybridRetriever(cfg)`。**直接 new 一个 retriever，绕过 lru_cache 单例**。
- 对每题取检索上下文 `C`（重排后截断结果），与 gold evidence `E⁺` 算 `CRec`。
- 不起 HTTP、不碰 server 进程。

### 1.3 候选配置表示
- 统一 `CandidateConfig` = `dict[str, Any]` override（如 `{"vector_top_k":50,"bm25_top_k":30}`）。
- sidecar 路径：override → env 大写键值字符串。
- in-proc 路径：override → `model_copy(update=...)`。
- **禁用项**：任何 override 写回 `.env`、`config.py`、`server/` 源码。CI 加 `git status --porcelain server/ .env` 断言为空。

---

## 2. 目录结构（全部在 `eval_methodology/`，不动 `tests/eval`）

```
eval_methodology/
  MVP_PLAN_DRAFT.md            # 本文件
  MVP_PLAN.md                  # 互审定稿后产出
  mvp/
    config/
      candidates.yaml          # 基线 + 候选 override 列表（版本化）
    dataset/
      normalize_labels.py      # Excel 4 列自由文本 → 结构化标签（CLI 建议 + 人工复核）
      build_gold.py            # 参考答案/原子说法/gold evidence/负样本（codex 生成 + claude 反验）
      split.py                 # 分层 dev/test/holdout，固定划分绑定代码版本
      dataset.json             # 产物：题目+标签+gold（版本号）
    metrics/
      judges/
        codex_judge.py         # 封装 `codex exec` 出 JSON
        claude_judge.py        # 封装 `claude -p` 出 JSON
      e2e.py                   # Faith/CitP/Match（+Comp/Corr 留接口）
      diagnostics.py           # CRec（+CPrec/Noise/ECov/RDeg/τ 留接口）
      bootstrap.py             # 配对 bootstrap B=1000，95% CI
    runner/
      sidecar.py               # 旁路后端起停
      diag_runner.py           # 进程内 retriever
      run_eval.py              # RunEval(v, D) → 指标字典
    loop/
      bottleneck.py            # LocateBottleneck（表五）
      actions.py               # PickSingleVarAction / ApplyAction
      ab_decide.py             # ABDecide 三态
      loop.py                  # IterativeImprovementLoop（MVP 只跑 1 次迭代）
      failures.py              # F 持久化
    reports/
      render.py                # JSON + Markdown（带 CI，给甲方）
```

复用旧脚手架的数据与口径：`tests/eval/test_questions.json`（题目 schema）、`outputs/评估结果_问题集_202606.xlsx`（甲方标注）、`tests/eval/baselines/`（容差 0.02 口径参考）。**不修改这些文件**。

---

## 3. CLI 作为两个模型族（gold 生成与 judge）

`main.tex` 硬约束：gold 生成族 ≠ judge 族；每题两家 judge。手上凭据 = `codex` CLI（GPT 系）+ `claude` CLI（Anthropic 系），天然两族。

- **gold 生成**（`build_gold.py`）：
  1. 每题先用基线 retriever 取候选 chunk 池（大 top_k）。
  2. `codex exec --skip-git-repo-check "<prompt + 池>"` → 参考答案 + 原子说法 + 各说法的 gold evidence chunk_id + 负样本 chunk_id（严格 JSON）。
  3. `claude -p "<反向核验 prompt>"` → 逐条核验 gold evidence 是否支持对应说法、参考答案有无事实错误，标不一致。
  4. 不一致处写 `review/disputes_*.md`，人工复核（MVP checkpoint，不自动合并）。
- **judge**（`metrics/judges/`）：
  - 每题对 (a, C) 两家各打分：`codex_judge.py`、`claude_judge.py`，返回 JSON（faithfulness 逐说法、citation 有效性、match 类别）。
  - 两家一致 → 进硬门槛分母；不一致 → 剔除并存疑，按 §3.3 规则（有效样本<15 或剔除率>30% 整轮降级为趋势参考）。

### 3.1 已识别的族冲突风险（请 codex 重点审）
答案生成端是 `LLM_*`（deepseek，第三族）。但：
- gold 由 codex 生成 → **codex 当 judge 时与 gold 同族**，违反 §2.3"gold gen 族 ≠ judge 族"。
- 缓解：ref-free 指标（Faith/CitP/Match）不依赖 gold，无此冲突；依赖 gold 的 Comp/Corr（MVP 未实现）将以 **claude judge 为权威、codex judge 仅作交叉核验**，并记录残余偏差。
- 这是对方法论的**部分偏离**，需在 `MVP_PLAN.md` 显式声明，并问用户是否接受。**codex 请独立判断此缓解是否站得住脚，不要因为是我提的就放过。**

---

## 4. CLI 结构化输出可靠性（请 codex 重点审）

- `codex exec` / `claude -p` 返回自由文本。要求严格 JSON 时易解析失败。
- 方案：prompt 末尾强约束"只输出一个 JSON 对象，无 markdown 围栏"；解析层 `json.loads` 失败则用正则取首个 `{...}`；再失败重试 1 次（温度/换族）；仍失败记为该题该指标缺测、不致命。
- MVP 不引重型 schema 校验（保持简单），但 `judges/*` 出错要计入剔除率。

---

## 5. 实施步骤（每步带验证）

1. **骨架与隔离验证** → `python mvp/runner/sidecar.py --smoke`：起旁路后端、用 override 配置打 `/healthz` 与 1 题 `/query/stream`、关进程；断言 `git status --porcelain server/ .env` 为空。
2. **数据集** → `python mvp/dataset/normalize_labels.py` + `build_gold.py` + `split.py` → `dataset.json`（15 dev 题，每题含 gold）；人工 spot-check 3 题。
3. **judge 适配器** → `codex_judge.py`/`claude_judge.py` 对 1 题出 JSON，解析通过。
4. **指标** → `run_eval.py` 在 dev 上跑基线（sidecar 18080）→ 指标字典 + bootstrap CI。
5. **迭代** → `loop.py`：基线 vs 候选（`vector_top_k` 30→50），`ab_decide.py` 给三态判定 + reason。
6. **报告** → `reports/render.py` 出 `reports/baseline_vs_candidate_<ts>.md`（带 CI 表，甲方可读）。

每步可独立跑、独立验证；任一步失败不阻塞前置产物。

---

## 6. 待 codex 对抗审阅的关键点

1. **隔离是否真的零改动**：sidecar env 注入 + in-proc `model_copy` 是否有任何隐含写回主项目的路径？`get_retriever` 的 lru_cache 在 in-proc 路径会不会被污染？
2. **CLI judge 的实用性**：每轮 ~15 题 × 2 族 = 30 次 CLI 调用，每次数十秒；MVP 只 2 轮配置尚可，但方法论完整 loop 多轮是否可行？是否需要缓存 judge 结果（同 (a,C) 不重判）？
3. **族冲突缓解（§3.1）是否站得住脚**：codex 既造 gold 又当 judge，仅靠"ref-free 指标不依赖 gold"是否够？还是该让 gold 生成只用 claude、judge 两族照旧？请给独立结论。
4. **gold evidence "必须在语料中存在"**：build_gold 只在 retriever 召回的池里选 gold，若真证据未被召回则永久缺失——这是对 §2.3"不丢弃、标检索缺口"的违反还是可接受的 MVP 近似？
5. **MVP 切片是否太薄**：只实现 CRec 一个诊断指标、只跑 1 次 A/B，能否真正"验证方法论可行"？还是该至少加 Faith+CitP+CRec 三指标 + 2 个候选？
6. **过度设计风险**：目录切这么细（loop/bottleneck/actions/ab_decide/loop/failures 五文件）对 MVP 是否过重？能否合并？
7. **bootstrap B=1000 在 n=15 上是否真比点估计稳健**，还是给假信心？

---

## 7. 不在本 MVP 做（留接口）

- Comp/Corr/CPrec/Noise/ECov/RDeg 完整实现（RDeg 需主项目加退化标志——属"小改"，本 MVP 不动主项目故跳过）。
- test/holdout 调度、check k 轮、holdout gate、失败回流 F 跨迭代累积。
- 多轮迭代主循环（MVP 只 1 次迭代证明闭环）。
- prompt/代码级与专项工程旋钮（只动配置级 `vector_top_k`）。