# LLM 回复复制与会话导出 Milestones

## M1: 后端导出契约冻结

对应阶段：

- Phase 1

目标：

- 后端能稳定返回可导出的 retrieval context 快照

达成标准：

- `/api/v1/query` 响应包含 retrieval context
- `/api/v1/query/stream` 的 `done` payload 包含相同结构
- 非流式与流式完成态字段保持一致
- 后端契约测试通过

## M2: 前端会话模型可持久化完整导出数据

对应阶段：

- Phase 2

目标：

- 每条 `ChatTurn` 都能保存回答原文、sources 与 retrieval context

达成标准：

- 前端类型与 API 接口已接入 retrieval context
- 流式与 fallback 非流式都能写入该字段
- 页面刷新后，新会话数据可恢复
- 历史 localStorage 数据迁移不报错、不丢消息

## M3: Markdown 导出引擎可独立工作

对应阶段：

- Phase 3

目标：

- 单条复制和整会话导出都能基于纯函数生成稳定 Markdown

达成标准：

- 模板规则冻结
- 单条消息 builder 与整会话 builder 均已实现
- 复制与下载动作层已封装
- 导出器测试覆盖核心样例与空值场景

## M4: 用户可见的复制与导出入口上线

对应阶段：

- Phase 4

目标：

- 用户可以在界面上直接完成单条复制与整会话导出

达成标准：

- 每条 assistant 回复出现复制入口
- 顶部栏出现整会话导出入口
- streaming 中的消息不会误导出不完整内容
- 成功、失败、禁用态反馈明确

## M5: 功能达到可验证交付状态

对应阶段：

- Phase 5

目标：

- 功能在 stream、fallback、刷新恢复三条关键路径下都可靠

达成标准：

- 后端回归测试通过
- 前端回归测试通过
- 人工验证覆盖以下场景：
  - 流式正常完成
  - 流式失败后自动 fallback
  - 刷新后恢复会话
  - 单条复制内容正确
  - 整会话导出内容正确

## 里程碑建议验收顺序

- 先验收 M1，再进入前端开发
- M2 完成后，再冻结 Markdown 模板
- M3 完成后，再接 UI
- M4 完成后，再进行 M5 的全面验证
