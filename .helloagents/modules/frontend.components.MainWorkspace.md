# 模块: frontend.components.MainWorkspace

## 职责

- 展示用户问题与流式回答内容
- 展示引用来源入口和关联引用
- 在 reasoning 可用时展示“深度思考”折叠面板

## 行为规范

- 空会话欢迎区、推荐问题区和输入框 placeholder 必须与当前主文档语境一致；文档切换后不应继续保留旧规范示例。
- 正式回答继续按 Markdown 渲染，保持现有 GFM 表格能力。
- 正文 Markdown 渲染会显式保留 `reference://` 与 `citation://` 两类内部引用协议，避免被 `react-markdown` 默认 URL 清洗后退化成普通文本。
- 正文中的内部规范引用统一渲染为紧凑编号锚点，命中来源时点击后联动右侧证据与溯源面板。
- 当同一 section 被拆成多条 `sources` 时，正文引用会优先关联最接近的来源片段，而不是因为“命中不唯一”直接退化为 `?`。
- 未命中当前 `sources` 的规范引用渲染为中性条款缩写胶囊（如 `A1.2.1`、`3.3`），保留 tooltip，但不允许误触发跳转。
- “引用来源”列表与正文共享同一套编号顺序，便于在正文锚点、来源列表和证据面板之间快速对应。
- `message.reasoning` 非空时，展示默认折叠的“深度思考”区域；为空时不渲染该区域。
- 流式生成中如果已收到 reasoning 且正文尚未到达，“深度思考”区域会自动展开；用户点击折叠/展开后，以手动偏好优先，不再被自动展开条件覆盖。
- reasoning 与 answer 分开累计，避免把思考内容混入最终回答正文。
- 已完成回答始终直接展示完整 LLM 正文，不再提供“现场 / 设计 / 审图”分层切换。
- 回答头部不再显示 `questionType` 小标签（如 `rule`），避免把内部分类暴露给最终用户。

## 依赖关系

- 依赖 `frontend/src/hooks/useEuroQaDemo.ts` 提供 `messages` 与流式状态
- 依赖 `frontend/src/lib/citations.ts` 识别并改写正文中的规范引用
- 依赖 `frontend/src/lib/inlineReferences.ts` 生成正文引用编号与可访问性提示
- 依赖 `frontend/src/lib/markdown.ts` 提供 Markdown 插件与内部引用 URL transform
- 依赖 `frontend/src/lib/types.ts` 中的 `ChatTurn.reasoning`
- 依赖 `frontend/src/lib/api.ts` 处理 `reasoning` / `chunk` / `done` 三类 SSE 事件
- 依赖后端 `/api/v1/suggest` 提供热门问题列表，供空状态推荐和底部推荐追问复用
