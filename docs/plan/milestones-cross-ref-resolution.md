# 交叉引用解析专项 — 里程碑

## M1: 离线引用图可用

达成标准：

- 已支持 `Table/Figure/Expression/Clause` 内部引用抽取
- 每个关键对象具备稳定 `object_id`
- ES 可按 `object_id/object_label` 精确查询
- 可产出 unresolved refs 报告

## M2: 在线 deterministic resolver 闭环

达成标准：

- exact 问题可输出 `resolved_refs/unresolved_refs`
- 对 `3.1.7 -> Table 3.1` 这类场景可自动补齐被引对象
- groundedness 纳入 `reference_closure`

## M3: 回答层证据闸门生效

达成标准：

- exact evidence pack 强制主条款与被引对象排序
- `sources` 顺序与证据顺序一致
- unresolved refs 能在响应诊断信息中暴露

## M4: 评测门禁建立

达成标准：

- 专项题库 >= 20 题
- 单测覆盖闭环、提权、降级、source 排序
- 评测报告输出：
  - `direct_ref_resolution_rate`
  - `reference_closure_rate`
  - `noise_intrusion_rate`

## M5: 可灰度上线

达成标准：

- 新旧索引并行方案就绪
- 影子日志与回滚预案就绪
- 通过专项评测门槛
- 允许先对 exact 问题小流量灰度
