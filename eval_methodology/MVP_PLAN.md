# 评估方法论 MVP 实施方案（v1，codex 一审已裁定并入）

> 草案 v0 → codex 对抗审阅（2/5，4 个 🔴）→ claude 公正裁定（事实全部核实成立，全部接受）→ 本 v1。
> 下一节"codex 一审裁定记录"逐条写明接受/反驳与理由；其后是修订后的落地方案。

---

## A. codex 一审裁定记录（claude 公正裁定）

| # | codex 意见 | 核实 | 裁定 | 处理 |
|---|---|---|---|---|
| 🔴1 | `vector_top_k` 30→50 被 prefetch 钳制无效 | 属实。`_config_for_top_k`(retrieval.py:2035) 把 vector/bm25/rerank_top_n 全钳到 `_INITIAL_TOP_K=8` 派生值 | **接受** | 换候选为 `retrieval_auto_cross_ref_closure` off→on（已核实 retrieval.py:1887 真接入，且 model_copy 不覆盖它→真生效） |
| 🔴2 | CRec 的 gold（仅召回池）与 C（in-proc retriever 不复现 decompose/补检索/父块/截断）都不合格 | 属实 | **接受** | gold 最终改为 Codex CLI 直接阅读完整 `data/parsed`，不依赖任何 RAG 候选池；CRec 的 C 取 e2e `retrievalContext` |
| 🔴3 | "零改动主项目"不成立：sidecar 起 lifespan 会 init SQLite/WAL、恢复任务、可能建 Milvus collection；`.env` 被 gitignore 检测不到；工作树本就脏 | 属实（main.py:25-45 lifespan；.gitignore:18） | **接受** | sidecar 状态全引向临时目录；断言 Milvus collection 已存在；`git status` 改前后快照对比+`.env` 哈希单独比；进程组+finally+kill |
| 🔴4 | Match 无有效人类标签：Excel 无对应答案快照，旧 y 用到新答案上无意义 | 属实（`outputs/dataset_answers/` 均旧版本） | **接受** | MVP A/B 删除 Match；y 仅用于分层划分与未来 holdout；历史答案可作 judge 校准参考（非 A/B 指标） |
| P1 | model_copy 不校验（留 str "50"、收未知字段）；dict[str,Any] 使 sidecar/in-proc 对坏配置发散 | 属实（codex 实测） | **接受** | 改白名单 Pydantic CandidateConfig，经完整 ServerConfig 构造做类型校验 |
| P2 | CLI judge 完整 loop 不可扩展；应缓存；用原生结构化输出 | 属实（claude `--json-schema`/codex `--output-schema` 均核实存在） | **接受** | 每题每族一次调用返回全指标；内容寻址缓存从 MVP 起做；Pydantic 校验；codex `--ephemeral -s read-only` 临时目录，claude 禁工具/会话持久化 |
| P3 | 族冲突：codex 既造 gold 又 judge；"gold 只 claude"同样违独立性 | 部分属实 | **接受+收窄** | MVP 指标限定 ref-free（Faith/CitP/CRec），不依赖 gold→冲突结构性回避；Comp/Corr 延后（需第三族或人工裁定 gold）；报告记录实际 resolved model+族 |
| P4 | gold 仅召回池是循环定义，非可接受近似 | 属实 | **接受** | 同 🔴2 处理；若坚持池内则改名 pool-relative CRec 且不得声称验证检索召回 |
| P5 | 候选应由基线诊断定位、非预指定，否则只验 A/B 机制不验迭代 | 成立 | **接受** | 加 LocateBottleneck 薄步骤：基线指标→表 5→选环→选候选；3 态单测 |
| P6 | 5 文件 loop 过重 | 成立 | **接受** | 合并为 `decision.py`+`run_mvp.py`；未实现指标不建空函数，只定 schema+todo |
| P7 | B=1000 在 n=15 是假信心；dev 恰 15 一题分歧即跌破；未刻画生成随机性 | 成立 | **接受** | dev 16 题；固定 bootstrap 种子；基线重复 1 次估自然波动；报告逐题配对差、有效 n、CI 宽度、judge 剔除率；宽 CI 标探索性 |

**新增（codex 未点透，claude 补充）**：`_INITIAL_TOP_K=8` 不仅钳 vector/bm25，连 `rerank_top_n` 也钳成 8。即方法论表 5/6 列为"配置级日常旋钮"的 `k_vec/k_bm25/k_rr` 在当前 agent 主路径**大部分空转**。这对"迭代方法论可行性"是关键发现——日常迭代可能被迫落到代码级旋钮（`_INITIAL_TOP_K`、decompose prompt、max_turns），而代码级改动恰好与"不反复改/复原主项目"的隔离要求最紧张。**这点需用户拍板 MVP 候选用配置级（`auto_cross_ref_closure`，已验生效）还是代码级（如 `_INITIAL_TOP_K` 8→12，验更难的隔离）。** 见 §C 决策点。

---

## B. 修订后落地方案（v1）

### B.0 目标与切片（修订）
- 目的：验证方法论三支柱可行 + 迭代与主项目独立。
- 指标集（收窄）：**Faith、CitP（端到端，ref-free）+ CRec（诊断，gold-dependent 但确定性、无 judge）+ `unresolved_ref_rate`（确定性，定位 L4）**。Match/Comp/Corr 不进 MVP（Match 无新标签；Comp/Corr 依赖 gold 且有族冲突）。详见 §E.2 措辞修正。
- 迭代：**基线 → LocateBottleneck → 1 个候选 → 配对 bootstrap 三态判定**；基线额外重复 1 次估自然波动。
- 成功判据：①主项目零脏动可证（快照对比，见 B.3）；②带 95% CI 的甲方可读报告；③A/B 给三态+reason；④gold/judge 全程 CLI 两族可追溯。

### B.1 隔离架构（修订）
- **端到端 Faith/CitP**：旁路后端（`runner/sidecar.py`），候选配置注入子进程 env，alt 端口。**CRec 的 C 也取自该响应的 retrievalContext**（不再有 in-proc 诊断路径）。
- **候选配置**：白名单 `CandidateConfig`（Pydantic，只含 `retrieval_auto_cross_ref_closure / *_timeout_seconds` 等已验证流入字段）→ 构造完整 `ServerConfig` 做类型校验 → sidecar 走 env、（若选代码级候选则走 patch overlay，见 §C）。
- **隔离保障**（修订，覆盖 🔴3/P1）：
  - sidecar env：`KNOWLEDGE_BASE_DB_PATH / PARSED_DIR / 日志目录` → 临时目录；`SPOT_CHECK_ENABLED=0`、`REDIS_URL=""`。
  - 启动前断言 Milvus `eurocode_chunks` collection 已存在，缺失即报错退出（禁止评测创建索引）。
  - `git status` 前后快照对比，只断言**本次评测新增的脏动**为空；`.env` 单独前后哈希对比。
  - 进程组启动 + `finally` 超时 kill uv/uvicorn 子进程。

### B.2 数据集（修订，覆盖 🔴2/P4）
- `dataset/normalize_labels.py`：Excel 4 列自由文本 → 结构化标签（codex 或 claude 建议 + 人工复核），输出可信度高/低。
- `dataset/build_gold.py`：
  1. 先把 Markdown 语料复制到仓库外临时目录；Codex CLI 从中立临时 cwd 以 read-only/ephemeral 模式启动，通过 `--add-dir <staged-corpus>` 搜索完整语料，固定使用 `gpt-5.6-terra` 并显式设置 `model_reasoning_effort=low`；gold CLI 单次超时为 900 秒，超时须终止整个进程组。提示词使用挂载语料绝对路径，不假设 cwd 内有文件；该隔离防止继承项目 `AGENTS.md`，且禁止调用 `HybridRetriever`、Milvus、Elasticsearch 或预计算候选池；
  2. 定位符固定为 `evidence_id + document_path + section + verbatim quote`，代码确定性校验路径未逃逸且规范化后的 quote 确实存在；
  3. Claude CLI 同样从仓库外中立临时 cwd 启动，仅启用 `Read/Grep/Glob` 并挂载同一个仓库外语料副本，避免 `--add-dir` 回溯项目 `CLAUDE.md`；不使用会禁用本机 OAuth/keychain 的 `--bare`，核验答案、claim、证据支持关系与最小充分性。报告分别记录 CLI interface、resolved model 与由 model id 判定的实际 family，不把 `claude` 命令名误记为 Anthropic 家族；
  4. Claude 或确定性校验不通过时，把问题交回 Codex 输出完整返修版，再交 Claude 复审；最多返修两轮，仍不通过标 `review_not_converged`；
  5. 通过模型复审后仍须人工确认最小充分证据集，并用 `build_gold.py --confirm <ids|all> --reviewer <name>` 持久化；未确认题不进入正式 CRec。CRec 用 evidence quote 对 e2e citable context 正文做确定性覆盖匹配。
- `dataset/split.py`：分层 dev16/test9/holdout6，固定划分绑定代码版本。

### B.3 指标（修订）
- `metrics/judges/`：`codex exec --ephemeral -s read-only --output-schema <schema.json>`（临时目录跑）；`claude -p --json-schema <schema> --output-format json`（禁工具/会话持久化）。每题每族**一次调用返回全指标**。
- `metrics/e2e.py`：Faith（逐说法支持率）、CitP（引用内容级有效性）；两家一致进硬门槛，分歧剔除并计剔除率（有效 n<15 或剔除>30% 降级趋势参考）。
- `metrics/diagnostics.py`：CRec = 被 C 覆盖的已确认 E⁺ quote 数 / 已确认 E⁺ quote 总数，**C 取自 e2e 响应 retrievalContext 正文**。
- `metrics/bootstrap.py`：配对 bootstrap B=1000，**固定种子**；报告逐题配对差、有效 n、CI 宽度、剔除率；宽 CI 标探索性。
- **内容寻址缓存**（从 MVP 起，覆盖 P2）：键 = 族+model id+prompt/schema 版本+question+answer+有序 context chunk 内容哈希+citations。

### B.4 迭代（修订，合并文件，覆盖 P5/P6）
- `loop/decision.py`：`LocateBottleneck`（表 5 映射，如 Faith↓→L5、CRec↓→L1/L2）+ `PickSingleVarAction`（表 6，只选配置或代码级、优先配置、一次一个）+ `ABDecide`（三态，bootstrap 区间判定）。
- `loop/run_mvp.py`：跑基线（×2 估波动）→ LocateBottleneck → 候选 → ABDecide → 报告。
- `tests/`：accept/reject/inconclusive 三态单测（mock 指标字典）。

### B.5 报告
- `reports/render.py`：JSON + Markdown，含 CI 表、有效 n、剔除率、基线自波动、resolved model+族。甲方可读。

---

## C. MVP 候选（已定：A）

> ✅ 用户已拍板：**A**（配置级候选 `retrieval_auto_cross_ref_closure` off→on）。B（代码级 overlay）不进本轮 MVP，留作后续隔离能力验证。

**MVP 候选用配置级还是代码级？**

- **选项 A（配置级，推荐做 MVP 第一刀）**：候选 = `retrieval_auto_cross_ref_closure` off→on。
  - 已核实 retrieval.py:1887 真接入、不被 prefetch 钳制 → 真改变 C → Faith/CitP/CRec 真变。
  - 验证 env 覆盖式隔离（主项目零改动）。
  - 但**不**验证代码级隔离——而钳制 gap 表明真实日常迭代多半落在代码级旋钮。
- **选项 B（代码级，验更难的隔离）**：候选 = `_INITIAL_TOP_K` 8→12 或 decompose prompt 微调，通过 **patch overlay 应用到 server/ 的临时副本**（git worktree 或 copy-on-write），sidecar 跑副本、主 worktree 永不改动。
  - 直接验证用户最担心的"调代码级参数不反复改/复原主项目"。
  - 隔离机制更重（需 server/ 副本 + patch 应用/清理）。
  - 更贴合方法论里"prompt/代码级"旋钮的真实迭代场景。

claude 倾向 **A 先跑通闭环、B 紧接做第二轮验证**（两候选正好也满足 codex P5"若宣称迭代闭环已验证再跑第二个顺序候选"）。但这是用户的核心关切，请你定。

---

## E. codex 二审裁定 + v2 定稿修订（claude 全部接受）

二审结果：🔴4 resolved；🔴1/🔴2/🔴3 partial；0 unresolved；3/5（修完约 4.5/5）。逐条裁定如下，均为**接受**（事实成立、改进落地），无反驳。

### E.1 阻断 partial 闭合
- **🔴1 候选预检门（新）**：`auto_cross_ref_closure` 只在有未覆盖内部引用时补 `fallback_ref_chunks`，OFF 时确定性引用补齐仍执行 → "必然改 C"过强。**加门**：off→on 后至少 N 题（建议 ≥3）的有序 context chunk-ID 集合发生变化，否则候选判无效、不进 judge。此门用 sidecar 响应的 retrievalContext 直接比，零 LLM 成本。
- **🔴2 gold 状态机修正**：三态明确——
  - Codex 直接阅读完整语料并经 Claude 复审后**找到**支持证据 → 进 `E⁺`（精确语料定位符）；
  - **找不到**任何支持证据 → 标 `corpus_gap`/`unverified_claim`，**不进 CRec 分母**；
  - 找到但候选版本 C 未召回 → `retrieval_gap`（计入，正是 CRec 该暴露的）。
  - 报告须给 `CRec eligible n`（分母实际题数）。人工复核范围 = 最小充分证据集确认（不止模型分歧）。
- **🔴3 代码级 overlay 修正**：B 路径的副本**快照当前工作树**（含未提交/未跟踪改动，因为基线就是脏状态），不从 HEAD 起 worktree；副本需处理 `.env`/依赖/cwd/PYTHONPATH/相对数据路径。`milvus_collection` 名从有效配置读，不硬编码 `eurocode_chunks`。

### E.2 修订引入的新问题（修正）
- **阈值**：降级线是"有效 n **<15**"（main.tex:204），不是 `<16`。dev=16 时一题分歧剩 15 仍可门禁；两题分歧才降级。
- **CRec 措辞**：CRec **不是 ref-free**，是 gold-dependent **确定性**诊断（依赖 E⁺，但无 judge→无自评循环）。族冲突只在 judge 自评时咬，CRec 无 judge 故不受影响。§B.0 的"ref-free"只适用 Faith/CitP。
- **LocateBottleneck 选 L4 的依据**：现有三指标（CRec→L1/L2、Faith/CitP→L5）无法指向 L4（auto_cross_ref 所在层）。**加确定性诊断 `unresolved_ref_rate`**（从 baseline 工具轨迹/引用缺口算，零 judge 成本）：基线该率高才进 L4 选 auto_cross_ref。
- **judge 单元对齐（关键）**：两家不能各自拆 claim 再比（分母/单元不同）。流程改为：**先做固定 claim/citation 抽取**（一个独立抽取步，产带 ID 的原子 claim 列表 + 引用单元）→ 两家 judge **只判同一组单元**的 support/valid → 定义逐单元一致与题级剔除规则。
- **基线重复进决策**：基线×2、候选×2（预算紧则候选×1）；基线自波动 = `δ/ε` 噪声下界，候选改善小于基线自波动判 inconclusive。
- **`_INITIAL_TOP_K` 定性**：若走 B，它同时改向量/BM25 候选、rerank 截断、最终 evidence 数——定义为**"prefetch budget"单一实现旋钮**，不解释为单阶段参数。

### E.3 §C 定稿（采纳 codex 独立结论，用户已定 A）
**本轮 MVP 只做 A。B 不进本轮，留作后续隔离能力验证。**

- **A（第一刀）**：候选 = `retrieval_auto_cross_ref_closure` off→on。两道**前置门**：
  1. baseline 的 `unresolved_ref_rate` 或逐题引用缺口分析确实指向 L4；
  2. off→on 在 ≥3 题产生 context diff（E.1 预检门）。
  - 两门任一不过：停止，不进昂贵 judge；改由 baseline 实际指向的层选候选（很可能 L5 代码级 prompt）。
- **B（紧随，隔离能力验证）**：仅做 overlay smoke——快照当前脏工作树副本、应用单一 patch、sidecar 跑副本与主 worktree 一致性校验。**不**做完整科研 A/B（除非 baseline 定位到 B 能解的瓶颈）。
- 若用户本轮必须同时证明代码级隔离：A 闭环 → B overlay smoke/一致性 → 后续按瓶颈决定是否完整 B。

> claude 与 codex 在 §C 收敛，无分歧。互审两轮结束（2/5 → 3/5 → 修完约 4.5/5），剩余项均为"按上表修完即实现"，无开放争议。

---

## D. 仍延后的部分（非 MVP）
- Comp/Corr/CPrec/Noise/ECov/RDeg 完整实现；RDeg 需主项目加退化标志（属小改，MVP 不动主项目故跳过）。
- test/holdout 调度、check k 轮、holdout gate、失败回流 F 跨迭代累积。
- 多轮主循环、第三族 judge、人工裁定 gold（Comp/Corr 正式门禁的前提）。
