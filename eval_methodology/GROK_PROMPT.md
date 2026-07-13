# Grok 实现任务：Eurocode QA 评估方法论 MVP

## 你的角色
在本仓库（`/Users/youngz/webdav/Euro_QA/.worktrees/agent-refactor`，git 分支 `reproduce-0613-baseline`）实现一个**评估方法论 MVP**，验证"数据集构建 → 指标评估 → 迭代优化"一条最短闭环可行，且迭代与主项目独立（调参不碰主项目）。

## 必读（权威依据，按序读）
1. `eval_methodology/MVP_PLAN.md` —— **实施定稿**，逐节照做。§A/§E 是互审裁定记录（解释了为什么这么定），§B 是落地方案，§C 是已锁定的候选选择。本文件与之冲突时以 `MVP_PLAN.md` 为准。
2. `eval_methodology/main.tex` —— 方法论靶子论文，指标定义、表 5（瓶颈定位）、表 6（环节-候选动作）、迭代主循环与 A/B 判定的形式化来源。

## 技术栈
- Python ≥3.12，包管理 `uv`，一切跑 `uv run`。FastAPI + pydantic v2 + pydantic-settings。
- 后端入口 `server/main:app`，配置 `server/config.py`（`ServerConfig`，`env_prefix=""`，env 优先级高于 `.env`）。
- 评估 sidecar 依赖既有 Milvus + Elasticsearch；**gold 构建不依赖二者**。`codex` CLI 与 `claude` CLI 已安装（gold 生成与 judge 用，见下）。

## 范围（只做这些，别扩张）
- 候选旋钮 = **`retrieval_auto_cross_ref_closure` 从 off→on**（配置级，A 方案）。**不要**用 `vector_top_k/bm25_top_k/rerank_top_n` 当候选——见下方"坑 1"。
- 指标 = **Faith、CitP**（端到端，ref-free）+ **CRec**（诊断，gold-dependent 但确定性、无 judge）+ **`unresolved_ref_rate`**（确定性，定位 L4）。**不实现** Match/Comp/Corr/CPrec/Noise/ECov/RDeg。
- 迭代 = 基线×2 → LocateBottleneck → 候选预检门 → 一次 A/B → 配对 bootstrap 三态判定。
- 代码全放 `eval_methodology/mvp/`。loop 目录合并为 `decision.py`（LocateBottleneck + PickSingleVarAction + ABDecide）+ `run_mvp.py`（编排）。未实现指标只定 schema+todo，不建空函数。

## 隔离纪律（最高优先级，违反即失败）
**主项目零改动**：禁止修改 `server/`、`.env`、`tests/eval/`、`pipeline/`、`shared/`。只允许新增/改 `eval_methodology/` 下文件。
- 端到端指标走**旁路后端**：`subprocess.Popen(["uv","run","uvicorn","server.main:app","--host","127.0.0.1","--port",P], env={**os.environ, ...overrides})`，基线 18080 / 候选 18081。
- 候选配置用**白名单 Pydantic `CandidateConfig`** → 构造完整 `ServerConfig` 做类型校验 → 翻译成 env 注子进程。**不写 `.env`**。
- sidecar 状态全引临时目录：env 设 `KNOWLEDGE_BASE_DB_PATH`、`PARSED_DIR`、日志目录 → 临时路径；`SPOT_CHECK_ENABLED=0`、`REDIS_URL=""`。
- **启动前断言 Milvus collection 已存在**（collection 名从有效 `ServerConfig` 读，**不要硬编码 `eurocode_chunks``）；缺失即报错退出，禁止评测创建索引。
- 隔离验证：跑前快照 `git status --porcelain`、`.env` 哈希；跑后再快照；断言**本次评测新增的脏动**为空、`.env` 哈希不变。注意当前工作树本就有未提交改动（基线就是这个脏状态），所以是"前后对比 diff"而非"要求为空"。
- 进程组启动 + `finally` 超时 kill uv/uvicorn 子进程。

## 必须避开的坑（前一轮互审已确认，别重蹈）
1. **检索旋钮空转**：`server/agents/orchestrator.py:54` 的 `_INITIAL_TOP_K=8` 是硬编码常量，调 retriever 时传入；`server/core/retrieval.py:2035` 的 `_config_for_top_k` 把 `vector_top_k/bm25_top_k/rerank_top_n` 全钳到该值派生值。改这三个全局配置在 agent 主路径**无效**。本方案候选 `retrieval_auto_cross_ref_closure` 在 `retrieval.py:1887` 真接入且不被 `model_copy` 覆盖 → 真生效。`agentic_search_enabled` 是死开关（无消费方），别用。
2. **候选预检门**（跑昂贵 judge 前先过）：① baseline 的 `unresolved_ref_rate` 或逐题引用缺口分析确实指向 L4；② off→on 后至少 3 题的有序 context chunk-ID 集合发生变化。任一不过 → 停候选、不进 judge。
3. **CRec 的 C 不能用 in-proc retriever 算**（不复现 decompose/补检索/父块/截断）。C 取自 e2e 响应里 `EvidenceBundle.citable_chunks()` 保存的真 C（见 `server/core/generation/context.py:13`）。
4. **gold 状态机**：Codex 直接阅读完整 `data/parsed` 找到证据并经 Claude 复审 → `E⁺`；找不到任何证据 → `corpus_gap`；模型复审不收敛 → `review_not_converged`；人工未确认最小充分证据集也不进 CRec。已确认 E⁺ 的 quote 未出现在候选 C → `retrieval_gap`。
5. **两家 judge 必须对齐单元**：不能各自拆 claim 再比（分母/单元不同）。先做**固定 claim/citation 抽取步**产带 ID 的原子 claim + 引用单元 → 两家 judge 只判**同一组单元** → 定义逐单元一致与题级剔除规则。
6. **bootstrap 阈值**：降级线是"有效 n **<15**"（不是 <16）；judge 剔除率 >30% 或有效 n<15 → 整轮降级为趋势参考。固定 bootstrap 随机种子。
7. **基线自然波动**：基线×2（候选预算允许也×2）；基线自波动 = δ/ε 噪声下界，候选改善小于基线自波动判 inconclusive。

## gold 与 judge 的 CLI 用法
- **gold 生成**：先将 `data/parsed/**/*.md` 复制到仓库外临时目录。`codex exec --ephemeral -s read-only --output-schema --add-dir <staged-corpus> -m gpt-5.6-terra -c model_reasoning_effort=\"low\"` 从另一个中立临时 cwd 启动，避免继承项目 `AGENTS.md`；gold CLI 单次超时为 900 秒，超时终止整个进程组。提示词明确使用挂载语料绝对路径，不假设 cwd 有语料，输出参考答案、原子 claims 和 `evidence_id/document_path/section/verbatim quote`，不得经过项目 RAG 或索引。随后 `claude -p --json-schema --output-format json --tools Read,Grep,Glob --no-session-persistence --add-dir <staged-corpus>` 也从中立临时 cwd 独立阅读同一仓库外副本，避免继承项目 `CLAUDE.md`。校验或审查失败则 Codex 完整返修、Claude 复审，最多两轮；仍失败不得进入 CRec。Claude 不使用 `--bare`，以兼容本机 OAuth 登录。
- **judge**：每题每族**一次调用返回全指标**。用原生结构化输出：codex `--output-schema`（JSON Schema 文件），claude `--json-schema`/`--output-format json`。Pydantic 校验；解析失败重试 1 次再失败记缺测。**内容寻址缓存**从 MVP 起做，键 = 族+model id+prompt/schema 版本+question+answer+有序 context chunk 内容哈希+citations。
- 跨族：codex（GPT 系）造 gold、claude（Anthropic 系）反验；judge 两族各打分，一致进硬门槛，分歧剔除计剔除率。报告记录实际 resolved model + 族。

## 复用（不重造）
- 题目 schema：`tests/eval/test_questions.json`。甲方标注：`outputs/评估结果_问题集_202606.xlsx`（31 题，4 列自由文本：正确性/完整性/多余·编造/总体判定）——Excel 解析逻辑可参考 `.claude/skills/euro-qa-run-eval/scripts/run_eval_dataset.py`（抽公共函数，**不改原文件**）。基线容差口径参考 `tests/eval/baselines/`（tolerance 0.02）。**不改 `tests/eval`**。

## 实施顺序（每步独立可验证，逐步提交）
1. **骨架 + 隔离验证** → `mvp/runner/sidecar.py --smoke`：起旁路后端、用 override 打 1 题 `/api/v1/query/stream`、关进程；断言主项目零新增脏动 + `.env` 哈希不变。**这步过了再继续。**
2. **数据集** → `normalize_labels.py` + `build_gold.py`（Codex 直读语料生成 → Claude 独立审查 → Codex 有界返修）+ `split.py`；人工确认全部题目的最小充分证据集。
3. **judge 适配器** → `codex_judge.py`/`claude_judge.py` 对 1 题出 JSON，固定 claim 单元对齐，缓存就位。
4. **指标** → `run_eval.py` 在 dev 上跑基线（sidecar 18080，×2）→ Faith/CitP/CRec/unresolved_ref_rate + 配对 bootstrap CI。
5. **迭代** → `decision.py`：基线→LocateBottleneck（表 5）→候选预检门→ABDecide 三态。`tests/` 覆盖 accept/reject/inconclusive 三态单测（mock 指标字典）。
6. **报告** → `reports/render.py` 出 `reports/baseline_vs_candidate_<ts>.md`（带 95% CI 表、有效 n、剔除率、基线自波动、resolved model+族），甲方可读。

## 成功判据
1. 全程 `git status` 证明主项目零新增脏动、`.env` 哈希不变。
2. 产出带 95% CI 的量化对比报告。
3. A/B 给出 accept/reject/inconclusive 之一并附 reason。
4. gold/judge 全程 CLI 两族可追溯，报告含 resolved model+族。
5. 三态单测全绿。

## 纪律
- 每步先写验证再写实现（goal-driven）。
- 简单优先：MVP 只跑 1 次迭代，别建多轮 loop/失败回流的空壳。
- 只动 `eval_methodology/`。任何"顺手优化 server/"的冲动都停下。
- 有歧义先读 `MVP_PLAN.md` 对应章节，仍不清楚就在 `eval_methodology/IMPLEMENTATION_NOTES.md` 记录问题并暂停问我，别擅自改主项目绕过。
