# 互审任务（codex ↔ claude）

你要对 `eval_methodology/MVP_PLAN_DRAFT.md`（claude 起草的 MVP 实施方案）做**对抗式审阅**。靶子方法论是 `eval_methodology/main.tex`（请先读它，确认草案是否忠实于方法论）。

## 评审纪律（重要）
- **公正、不偏袒**：不要因为草案是 claude 写的就放水，也不要为了显得严苛而无理否定。每条意见给**理由**和**具体改法或反例**。
- 同样，审阅我（claude）的方案时，假设你自己也可能错；如果草案某点其实成立，明确说"成立"。
- 目标是产出**成熟可落地的方案**，不是分出胜负。

## 重点审 7 个问题（草案 §6）
1. 隔离是否真零改动主项目？sidecar env 注入 + in-proc `model_copy` 有无隐含写回路径？in-proc 路径会不会污染 `get_retriever` 的 lru_cache？
2. CLI judge 实用性：每轮 ~15 题×2 族=30 次 CLI 调用；MVP 只 2 轮尚可，但方法论完整 loop 多轮是否可行？要不要缓存 judge 结果（同 (a,C) 不重判）？
3. 族冲突缓解（§3.1）站得住吗：codex 既造 gold 又当 judge，仅靠"ref-free 指标不依赖 gold"够不够？还是该让 gold 生成只用 claude、judge 两族照旧？请给**独立结论**。
4. gold evidence"必须在语料中存在"：build_gold 只在 retriever 召回的池里选 gold，真证据未被召回则永久缺失——这是对 main.tex §2.3"不丢弃、标检索缺口"的违反，还是可接受的 MVP 近似？
5. MVP 切片是否太薄：只 CRec 一个诊断指标、只 1 次 A/B，能否真"验证方法论可行"？还是至少加 Faith+CitP+CRec 三指标 + 2 个候选？
6. 过度设计：loop 下切 bottleneck/actions/ab_decide/loop/failures 五文件对 MVP 是否过重？
7. bootstrap B=1000 在 n=15 上是真稳健还是假信心？

## 额外要求
- 任何你发现的**可行性阻断**（不只是"建议改进"）单独列出来，标 🔴。
- 对 §1.3"禁用项 + git status 断言"这个隔离保障手段，判断是否充分。
- 草案假设答案生成端是 deepseek（第三族），请去 `server/config.py` 核实 `llm_model` 默认值，确认"三族"叙述属实。
- 输出格式：按问题编号给结论（同意/反对/部分同意 + 理由 + 改法），末尾给"总体可落地性评分 1-5 与一句话总结"。

可以读仓库任何文件。**不要改任何文件**，只输出审阅意见文本。