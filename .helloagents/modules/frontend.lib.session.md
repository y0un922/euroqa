# 模块: frontend.lib.session

## 职责

- 定义前端 Demo 当前会话轻量指针的本地持久化结构
- 提供 `loadPersistedDemoSession()`、`savePersistedDemoSession()` 和 `clearPersistedDemoSession()` 三个会话存储接口

## 行为规范

- 持久化结构必须包含 `currentSession` 指针、草稿、引用定位状态和设置，但不保存完整 `messages` 或历史会话列表。
- 历史会话列表由后端 Redis `GET /api/v1/sessions?userId=...` 恢复，避免浏览器本地存储承担完整会话历史。
- 读取本地存储时需要兼容旧版只包含单个会话字段的 payload，并自动归一化为新的 `currentSession` 结构。
- 非法 JSON 或无法识别的数据应直接返回 `null`，不能阻断前端工作台初始化。
- `savePersistedDemoSession()` 必须真实写入浏览器 `localStorage`，但只写轻量 payload；写入失败时返回 `false`，不能阻断前端工作台。

## 依赖关系

- 依赖 `frontend/src/lib/types.ts` 中的 `ChatTurn` 与 `LlmSettings` 类型
- 被 `frontend/src/hooks/useEuroQaDemo.ts` 用作当前会话轻量指针的本地存储层
