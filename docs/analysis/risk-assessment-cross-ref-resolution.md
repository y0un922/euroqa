# 交叉引用解析专项 — 风险评估

## 风险总览

### R1. 误把相关片段当成交叉引用对象

- 表现：
  - 命中 `3.1.7` 之后，把提到 `Table 3.1` 的其他条款当成真正表格对象
- 后果：
  - exact 问题被“相关片段”污染
- 对策：
  - 强制 object lookup 优先使用 `object_id/object_label/clause_ids`
  - 被引对象必须是结构化对象，不允许只靠正文弱匹配

### R2. 引用对象解析不完整导致误判 grounded

- 表现：
  - 主条款命中，但被引 `Table/Figure/Expression` 未找到
- 后果：
  - 生成阶段给出确定性答案，但证据不闭环
- 对策：
  - 增加 `reference_closure` 判定
  - exact 模式下，若 required refs 未覆盖，则降级 `exact_not_grounded`

### R3. 离线重建索引带来数据兼容风险

- 表现：
  - ES mapping 和 chunk schema 改动后需要重建索引
- 后果：
  - 新旧索引行为不一致
- 对策：
  - 使用新索引版本名或灰度索引
  - 提供 backfill/reindex 脚本和校验脚本

### R4. LLM fallback 反而扩大不稳定性

- 表现：
  - LLM 动态调用工具去追引用，调用路径不稳定
- 后果：
  - 线上不可复现、难调试、成本高
- 对策：
  - fallback 只允许处理 unresolved refs
  - 限制文档域、深度、调用次数、超时
  - 主链仍必须 deterministic

### R5. exact 证据包排序错误

- 表现：
  - 主条款、表格、图、公式都已取回，但 prompt 中顺序不稳定
- 后果：
  - LLM 仍可能抓错主位
- 对策：
  - exact evidence pack 固定为：
    1. primary clause
    2. directly referenced objects
    3. supporting context
  - source 输出顺序与 evidence pack 保持一致

### R6. 评测基线不覆盖生产危险问法

- 表现：
  - 只测简单 “Table 3.1 是什么”
  - 不测 “3.1.7 + Table 3.1 + eps_cu2” 这种真实工程复合问法
- 后果：
  - 线下看起来通过，线上仍出错
- 对策：
  - 专项评测集必须覆盖：
    - 条款 -> 表
    - 条款 -> 图
    - 条款 -> 公式
    - 条款 -> 条款
    - 多跳链
    - 噪音干扰同号场景

## 推荐上线策略

### 阶段 1：离线验证

- 仅在本地/测试环境建立新字段与新索引
- 跑专项评测集
- 人工核查典型问题样本

### 阶段 2：影子流量

- 线上仍用旧回答
- 新链路只记录日志与评测指标
- 比较：
  - direct ref resolution rate
  - exact grounded accuracy
  - noise intrusion rate

### 阶段 3：灰度切换

- 先只对 `answer_mode=exact` 生效
- 再逐步扩大到复杂引用问法

## 方案选择风险对比

```text
┌─────────────────────────────┬────────┬──────────┬──────────┬──────────────┐
│ 方案                        │ 准确性 │ 可审计性 │ 复杂度   │ 是否推荐主用 │
├─────────────────────────────┼────────┼──────────┼──────────┼──────────────┤
│ A 确定性交叉引用图优先      │ 高     │ 高       │ 中高     │ 是           │
│ B 确定性主链 + LLM 受限补查 │ 中高   │ 中       │ 高       │ 可作增强     │
│ C LLM 主导工具追引用        │ 中低   │ 低       │ 表面低/实高 │ 否         │
└─────────────────────────────┴────────┴──────────┴──────────┴──────────────┘
```

## 上线门槛建议

- `Table/Figure/Expression` 专项解析准确率 >= 95%
- exact 问题 `reference_closure_rate` >= 90%
- `noise_intrusion_rate` 低于当前线上基线 50%
- 核心回归题库 0 个 blocker
