# main.tex v2 修订说明(与已落地代码对齐)

目标:`eval_methodology/main.tex` 从"完整论文蓝图"收敛为与 `eval_methodology/mvp/` 当前实现**完全一致**的方法论文档。原则:代码没实现的不在正文出现;正文每个数字/阈值必须与代码常量一致。

## 0. 硬约束

- 只修改 `eval_methodology/main.tex`(以及 `MVP_PLAN.md` 顶部加 superseded 标注);不改任何 `.py`。
- 修订后必须编译通过:`cd eval_methodology && latexmk -xelatex -interaction=nonstopmode main.tex`,无 error(warning 可接受)。
- 中文行文风格与现文档保持一致;公式编号、引用键(`\cite{...}`)不悬空——删掉的章节若含 `\label` 被别处 `\ref`,同步清理。

## 1. 与代码对齐的权威口径(正文一切以此为准)

来自当前实现(`mvp/paths.py`、`loop/decision.py`、`loop/run_mvp.py`、`metrics/judges/judge.py`):

- 核心指标 4 个:Faith(主指标,硬门槛)、CitP(非回归门)、unresolved_ref_rate(确定性诊断,L4)、CRec(确定性诊断,L1/L2,gold 为双模型交叉复审产物、未经人工确认、**不进门禁**)。
- 运行指标:单题时延、token 用量(usage)、judge 失败率。
- judge:**单模型族**,CLI 结构化输出,每题一次调用(claims 拆分与判定在同一次输出);与生成端不同族;resolved model id 如实记录;内容寻址缓存(键含 family、model id、prompt/schema 版本、question、answer、context hash),同一答案永不重复 judge。
- judge 失败处理:超时 180s、重试 1 次;失败题 Faith/CitP 为空、计入 judge_fail_rate;**judge_fail_rate > 30% → 该轮降级为趋势参考**(不再有"双 judge 分歧剔除"概念)。
- A/B 判定:配对 bootstrap(B=1000,固定种子),三态:CI 全高于 +ε(0.05)→ accept;CI 全低于 −δ(0.05)→ reject;其余 inconclusive;CI 宽 > 0.1 → 仅探索性;有效配对 n < gate_n(默认 12)→ inconclusive。
- 流程(单管线,两档位):
  - 日常:`baseline`(按 git rev + 配置哈希 + 数据集版本缓存复用)→ 瓶颈定位 → 单变量候选 + L4 前置门(unresolved_ref_rate ≥ 0.15)→ candidate 答案(逐题落盘、断点续跑)→ **context diff 门**(有序 chunk-id 序列变化 < 3 题 → inconclusive,不进 judge)→ judge candidate → 三态判定 → JSON+Markdown 报告(逐题、差值、阶段耗时)。
  - 里程碑:同一命令,`--split full --repeats 2 --fresh`;基线×2 仅用于报告自波动(self-noise)展示,不参与判定。
- 数据集:31 题(dev16/test9/holdout6,划分冻结);历史 Excel 评语仅用于分层参考,不做 Match;gold:15 题 supported(codex 构建 + claude 复审 + 确定性 quote 校验),mixed 9 / corpus_gap 7 不进 CRec 分母。

## 2. 逐节修订指令

- **§引言**:补一段"方法论 v2 收敛原则"(指标少而有用、单 judge、一条管线两档位、一切以可运行为准);删除对双家族/holdout 门禁的前瞻承诺。
- **§数据集构建**:gold 小节改为定稿口径(双模型交叉复审、免人工确认、仅诊断);删除人工确认流程、holdout gate 调度描述;保留分层划分与"历史标签不做 Match"的裁定及理由。
- **§评估指标**:
  - 正文只保留:Faith、CitP、CRec(重写为确定性 quote 覆盖诊断口径)、unresolved_ref_rate(新增小节,给出定义:unresolved/(unresolved+resolved),无引用需求时为 0)、运行指标(时延/token/失败率)。
  - **整段删除**:Hall/NonHall、Match、τ、Comp、Corr、CPrec、Noise、ECov、RDeg 各小节。
  - judge 小节重写:单族 judge 设计 + 失败率降级 + 缓存保证可重复;新增一小段"单 judge 的局限与为何可接受"(不同族缓解自评偏置;缓存保证配对比较两侧同一把尺;方向性结论可信,绝对分数需谨慎解读)。
- **§迭代方法论**:
  - 伪代码/流程按 §1 的单管线重写(baseline 缓存 → 定位 → 前置门 → candidate → diff 门 → judge → 三态);
  - 基线×2 从默认流程改为里程碑选项(self-noise 仅展示);
  - 瓶颈映射表(表 5)收缩为 4 行:Faith↓→L5、CitP↓→L5、unresolved_ref_rate 高→L4、CRec↓→L1/L2;候选动作表(表 6)只保留已验证真实生效的旋钮(`retrieval_auto_cross_ref_closure`),其余注明"待 `_INITIAL_TOP_K` 钳制解除后扩充";
  - 阈值统一:ε=δ=0.05、gate_n=12、CI 宽 0.1、fail_rate 30%、diff 门 3 题。
- **§已有工作的取舍 / §落地约束**:按新口径瘦身,删除与双 judge、Match、gold 人工确认相关的段落;隔离(sidecar env 注入、不改主项目 .env、git 快照断言)保留。
- **§指标可算性汇总**(表):重写为 4 核心 + 运行指标,一列注明"角色(门禁/诊断/随报)"。
- **新增附录:延后指标清单**:一张表,每行 = 指标名 + 一句话定义 + 一句话延后理由(Hall=Faith 镜像;Match 无对应答案的人工标签;Comp/Corr 依赖 gold claims 与族独立性;CPrec/Noise/ECov 依赖 E⁻ 或证据集;RDeg 需改主项目;τ ties 过多)。给老师留取舍痕迹。
- **§交叉审阅摘要**:保留,末尾追加一段:v2 按"可运行优先"原则收敛,收敛决策记录于 `MVP_V2_IMPL_PLAN.md`。
- **§编译命令**:不变。

## 3. MVP_PLAN.md

顶部加一段:

> **[superseded 2026-07-16]** 本文为 v1 双 judge 方案的互审记录,已被 v2 取代;当前实现以 `MVP_V2_IMPL_PLAN.md` 与 `mvp/README.md` 为准。正文保留作决策历史。

其余内容不动。

## 4. 验收

1. `latexmk -xelatex -interaction=nonstopmode main.tex` 编译通过,产出 PDF。
2. `rg -c 'Comp|Corr|CPrec|Noise|ECov|RDeg|Match' main.tex` 的命中只出现在附录"延后指标清单"与交叉审阅摘要历史段落中。
3. 正文不再出现"双家族/两个家族 judge""分歧剔除""人工确认 gold""有效样本数不得低于 15"的表述(附录/历史段除外)。
4. 正文阈值与 `mvp/paths.py`、`decision.py` 常量一一对应(ε、δ、gate_n=12、0.1、30%、3 题、B=1000)。
5. `\ref`/`\label`/`\cite` 无悬空(编译 log 无 undefined reference)。
