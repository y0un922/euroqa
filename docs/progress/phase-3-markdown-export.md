# Phase 3: Markdown 导出器与复制/下载动作封装

## 任务清单

- [x] P3-T1 冻结 Markdown 模板，明确单条复制和整会话导出的章节结构与字段保留规则。（验收：单条复制模板包含回答原文、引用来源、本轮 retrieval context；整会话模板按轮次分节；明确是否包含用户问题、reasoning 与空 section 处理规则；模板可直接落为纯函数输出）
- [x] P3-T2 实现共享的 Markdown 格式化基础能力，例如 section builder、source 列表格式化、retrieval context 分组格式化。（验收：共享 helper 输出稳定、无 UI 依赖；对空 sources、空 retrieval context、空 related refs 有稳定行为；输出不依赖浏览器环境）
- [x] P3-T3 实现单条消息 Markdown builder。（验收：输入单个 `ChatTurn` 输出可直接复制的 Markdown；输出顺序与模板定义一致；只在消息完成态下输出最终版本）
- [x] P3-T4 实现整会话 Markdown builder。（验收：输入消息数组输出整会话 Markdown；每轮问答边界明确；能跳过无效空消息并保留有效完成态消息）
- [x] P3-T5 封装浏览器复制与下载动作，并补齐纯函数/动作层测试。（验收：复制优先使用 Clipboard API 且失败可处理；会话导出支持 `.md` 文件下载；新增导出模块测试覆盖单条与整会话样例）

## Notes

- 本阶段有两个推荐并行 lane：
  - Lane A：P3-T3 单条消息 builder
  - Lane B：P3-T4 整会话 builder
- 在 P3-T1 和 P3-T2 完成前，不要开始 UI 集成，避免模板反复返工。
- 2026-04-08 调整：整会话导出当前产品行为改为精简模式，仅保留每轮 `User Question` 与 `Answer Markdown`；单条回复导出/复制仍保留原有富信息模板边界。
