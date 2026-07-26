# 验收任务：对抗审阅 Grok 的评估方法论 MVP 实现

## 你的角色
Grok 已按 `eval_methodology/GROK_PROMPT.md` 实现了评估方法论 MVP（代码在 `eval_methodology/mvp/`）。你要做**对抗式验收**：不是橡皮图章，也不是为严苛而严苛——逐条用**可复现的证据**（`file:line` + 命令 + 实跑输出）判定 pass/fail/partial。发现 Grok 偷懒、绕过、或文档写得好但代码没做到的，必须指出。

## 必读
1. `eval_methodology/MVP_PLAN.md` —— 实施定稿。**§E 是互审两轮挖出的坑与裁定，是验收清单的来源**。
2. `eval_methodology/main.tex` —— 方法论靶子（指标定义、表 5/6、A/B 判定）。
3. `eval_methodology/GROK_PROMPT.md` —— Grok 被要求做的事（验收即核对它是否做到）。
4. `eval_methodology/mvp/` —— Grok 的实现。

## 验收清单（逐条给 verdict + 证据 + 复现命令）

### A. 隔离是否真零改动（最高权重，🔴3 衍生）
- A1. 跑 `uv run python eval_methodology/mvp/runner/sidecar.py --smoke`（或等价入口），实跑前后对比 `git status --porcelain`：断言**除 `eval_methodology/` 外主项目无新增脏动**。
- A2. 实跑前后 `.env` 哈希对比（`shasum -a 256 .env`）应不变。
- A3. sidecar 是否把 `KNOWLEDGE_BASE_DB_PATH`/`PARSED_DIR`/日志引到临时目录、设 `SPOT_CHECK_ENABLED=0`、`REDIS_URL=""`？给 `file:line`。
- A4. 启动前是否**断言 Milvus collection 已存在**且**从配置读 collection 名**？grep `mvp/` 看有无硬编码 `eurocode_chunks`（应无）。
- A5. 子进程是否用进程组 + `finally` 超时 kill？模拟超时路径验证不残留 uvicorn。
- A6. `CandidateConfig` 是否白名单 pydantic、经完整 `ServerConfig` 做类型校验后转 env？有无 `dict[str,Any]` 直传导致的 sidecar/in-proc 分歧漏洞？

### B. 候选是否真有效（🔴1 + E.1 预检门）
- B1. 候选是否 = `retrieval_auto_cross_ref_closure` off→on？**没用** `vector_top_k/bm25_top_k/rerank_top_n` 当候选（核实：`orchestrator.py:54` `_INITIAL_TOP_K=8` 经 `retrieval.py:2035` 钳制它们）。
- B2. 是否实现**候选预检门**：① baseline `unresolved_ref_rate` 指向 L4；② off→on 在 ≥3 题产生有序 context chunk-ID 集合变化。任一不过则停候选、不进 judge？给 `file:line` + 实跑预检输出。

### C. gold 与 CRec 正确性（🔴2 + E.1/E.2）
- C1. gold 状态机三态是否实现：找到→`E⁺`；找不到→`corpus_gap`（**核实不进 CRec 分母**）；找到但候选未召回→`retrieval_gap`（计入）。
- C2. CRec 的 `eligible n` 是否在报告中给出？
- C3. **CRec 的 C 是否取自 e2e 响应 `EvidenceBundle.citable_chunks()`**（`server/core/generation/context.py:13`）？**核实没有用 in-proc retriever 算 C**（grep `mvp/` 是否有 `HybridRetriever(...)` 用于 CRec）。
- C4. gold 生成是否走高召回多策略并集（多查询 BM25+向量+对象查找+父块/邻块），而非仅基线 retriever 池？
- C5. 人工复核范围是否 = 确认最小充分证据集（不止模型分歧）？`disputes_*.md` 是否产出？

### D. judge 对齐与 CLI（E.2/N5 + P2）
- D1. 是否有**固定 claim/citation 抽取步**产带 ID 单元，两家 judge 判**同一组单元**？（不是各自拆 claim 再比）
- D2. 逐单元一致 + 题级剔除规则是否定义并实现？
- D3. 是否用原生结构化输出：codex `--output-schema`、claude `--json-schema`/`--output-format json`？**有无退回"正则截 {...}"**（应只在原生失败重试时兜底，且计入剔除率）。
- D4. 是否实现**内容寻址缓存**？键是否含 族+model id+prompt/schema 版本+question+answer+有序 context chunk 哈希+citations？抽查缓存命中是否正确（同输入不重判）。
- D5. 跨族：codex 造 gold、claude 反验；judge 两族各打分、一致进硬门槛、分歧剔除。报告是否记 resolved model+族？

### E. bootstrap 与统计（E.2/N1/N6 + P7）
- E1. 降级线是"有效 n **<15**"（**核实不是 <16**）；剔除率 >30% 或 n<15 整轮降级趋势参考。
- E2. bootstrap 固定随机种子？B=1000？逐题配对差、有效 n、CI 宽度、剔除率是否都进报告？
- E3. 基线是否×2（候选预算允许也×2）？**基线自波动是否作为 δ/ε 噪声下界**——候选改善小于基线自波动判 inconclusive？核实决策代码真用了这条。

### F. 迭代与测试（P5/P6）
- F1. `decision.py` 是否含 LocateBottleneck（表 5）→ 预检门 → ABDecide？候选是否由 baseline 诊断驱动（非预写死）？
- F2. loop 是否合并为 `decision.py`+`run_mvp.py`（无 5 文件过度拆分、无空壳函数）？
- F3. **实跑** `uv run pytest eval_methodology/mvp/tests/`：三态单测（accept/reject/inconclusive）是否全绿？审查单测是否用**真实区间的 mock 指标**（非平凡通过），尤其 inconclusive 的区间跨越判定。

### G. 报告诚实度
- G1. 报告是否真算了 CI（抽查一题的 bootstrap 区间与点估计是否自洽，非编造）？
- G2. 是否披露：有效 n、judge 剔除率、基线自波动、resolved model+族、降级为趋势参考的项？
- G3. 有无"形式完整但结论不可信"的迹象（如候选预检门没过却仍出 A/B 结论、剔除率>30% 却不降级、CI 宽度>0.1 仍当硬门槛）？

### H. 范围纪律
- H1. 未实现 Match/Comp/Corr/CPrec/Noise/ECov/RDeg（只定 schema+todo，不建空函数）。
- H2. 只动 `eval_methodology/`；`server/`、`.env`、`tests/eval/`、`pipeline/`、`shared/` 零改动（`git status` 佐证）。

## 输出格式
- 按 A1–H2 逐条：`verdict`（pass/fail/partial）+ `证据`（file:line 或命令输出）+ `复现命令`。
- 单独列 🔴 must-fix（阻断接受的问题）。
- 末尾：可接受性评分 1–5 + 一句话总评 + "接受前必须修的项"清单。
- 纪律：能实跑就实跑，别只读代码下结论。对 Grok 不偏袒也不找茬——每条以代码与实跑为准。

## 不要做的事
- 不要改任何文件（只读 + 跑只读命令；pytest 与 smoke 命令可跑）。
- 不要因为 Grok 实现了某个功能就默认它正确——验证它避开了已知的坑。
- 不要复述方案；只报偏差与证据。