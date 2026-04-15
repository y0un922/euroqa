# 模块: frontend.components.TopBar

## 职责

- 展示 API 状态、文档数、术语数等顶部摘要
- 提供 LLM 设置入口并承载设置面板开关

## 行为规范

- 顶部栏中的 `LLM 设置` 按钮只负责打开/关闭面板，不承担设置持久化逻辑。
- 设置面板关闭前的“保存”与“恢复默认”动作，必须回调到 `useEuroQaDemo` 完成状态更新。
- 保持现有顶部摘要信息不变，不因设置功能引入额外主布局变动。

## 依赖关系

- 依赖 `frontend/src/components/LlmSettingsPanel.tsx` 渲染设置面板
- 依赖 `frontend/src/hooks/useEuroQaDemo.ts` 提供默认值、覆盖值和保存动作
