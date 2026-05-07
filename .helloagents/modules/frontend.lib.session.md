# 模块: frontend.lib.session

## 职责

- 定义前端 Demo 当前会话与历史会话的本地持久化结构
- 提供 `loadPersistedDemoSession()`、`savePersistedDemoSession()` 和 `clearPersistedDemoSession()` 三个会话存储接口

## 行为规范

- 持久化结构必须同时包含 `currentSession` 和 `history`，避免“新建检索会话”后丢失已归档问答。
- 读取本地存储时需要兼容旧版只包含单个会话字段的 payload，并自动归一化为新的 `currentSession` 结构。
- 非法 JSON 或无法识别的数据应直接返回 `null`，不能阻断前端工作台初始化。
- `savePersistedDemoSession()` 必须真实写入浏览器 `localStorage`，不再以删除存储键代替持久化。

## 依赖关系

- 依赖 `frontend/src/lib/types.ts` 中的 `ChatTurn` 与 `LlmSettings` 类型
- 被 `frontend/src/hooks/useEuroQaDemo.ts` 用作当前会话和历史会话的本地存储层
