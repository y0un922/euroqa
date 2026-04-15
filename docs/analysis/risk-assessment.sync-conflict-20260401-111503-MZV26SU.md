# Euro_QA Feature Risk Assessment

## 任务定义

目标是实现：

- 单条 LLM 回复复制
- 整个会话导出/复制
- 导出格式为 Markdown
- 内容包含回答原文与该轮检索召回的全部上下文
- 以数据准确性优先

## 主要结论

这是一个“跨前后端协议 + 前端导出能力”的 feature，不是纯 UI 按钮任务。

最关键的事实：

- 前端当前只拿得到 `answer` 和 `sources`
- 后端内部真正参与回答生成的 `chunks / parent_chunks` 没有返回给前端

因此，如果严格按需求实现，就必须扩展 API 契约。

## 风险清单

### P0. 检索上下文当前未透传到前端

严重度：高

现状：

- `server/core/retrieval.py` 内部存在 `RetrievalResult.chunks` 和 `parent_chunks`
- `server/api/v1/query.py` 调用生成后并未把这些字段带回前端
- 前端 `ChatTurn` 也没有相应字段

影响：

- 无法准确导出“本轮检索召回的全部上下文”
- 只能退化成“回答 + sources”，无法满足你确认的范围 B

建议：

- 在后端完成态响应中增加一个显式的“retrieval context”结构
- 前端把它存入 `ChatTurn`

### P0. 流式与非流式响应结构需要同时保持一致

严重度：高

现状：

- `/query` 返回 `QueryResponse`
- `/query/stream` 通过 SSE `done` 返回 `sources / related_refs / confidence`
- 两条链路共享同一数据域，但结构并不完全一致

影响：

- 如果只改非流式或只改 stream done，前端状态会出现分叉
- fallback 路径会丢字段，导致同一问题在不同网络条件下导出结果不一致

建议：

- 统一设计“完成态元数据”结构
- 非流式与流式 done 都返回同一组新增字段

### P1. localStorage 体积与会话膨胀风险

严重度：中高

现状：

- `frontend/src/lib/session.ts` 会把整个 `messages` 放进 localStorage
- 若每轮保存完整 `chunks + parent_chunks`，体积会明显增大

影响：

- 长会话可能接近浏览器存储上限
- 页面刷新恢复可能变慢

建议：

- 明确 retrieval context 的保存粒度
- 优先保存“导出所需字段”，而不是把整个后端内部 `Chunk` 原样塞到前端
- 控制每轮上下文的保留上限和字段裁剪规则

### P1. 既有 session 数据迁移风险

严重度：中高

现状：

- `frontend/src/lib/session.ts` 已经存在兼容旧消息结构的迁移逻辑

影响：

- 新增字段后，如果迁移策略不稳，会导致旧会话无法恢复或消息被丢弃

建议：

- 新增字段必须是可选字段
- `normalizeChatTurn()` 与相关测试同步扩展

### P1. 导出内容定义不清会导致“准确但不好用”或“好用但不准确”

严重度：中

现状：

- 需求明确要“全部上下文”，但“全部上下文”的导出格式尚未定稿

潜在分歧点：

- 是否保留 `scores`
- 是否区分 `chunks` 与 `parent_chunks`
- 是否带上 source 元数据、标题、页码、条款号
- 是否导出 reasoning

建议：

- 在规划阶段先定义稳定的 Markdown 模板
- 明确单条复制与整会话导出的排版一致性

### P2. UI 入口放置不当会让消息区变得拥挤

严重度：中

现状：

- `MainWorkspace.tsx` 的回答头部已经承载状态、引用、思考折叠等信息
- `Sidebar.tsx` 当前只有新建会话与导航内容

建议：

- 单条复制按钮放在回答头部或回答卡片右上角
- 整会话导出按钮放在会话级入口，例如 `Sidebar` 或 `TopBar`

### P2. 工作区脏状态提高误改风险

严重度：中

现状：

- 仓库存在大量未提交改动
- 有 sync-conflict 遗留文件

影响：

- 实现阶段可能误碰无关文件
- 回归验证时需要特别区分本次改动与历史未提交改动

建议：

- 只在明确目标文件内增量修改
- 测试与 diff 审核时以文件范围为边界

## 复杂度热点

### 1. `frontend/src/hooks/useEuroQaDemo.ts`

- 单一 hook 承担网络、状态、持久化、UI 联动
- 新增消息字段时需要同时处理：
  - stream 过程中的占位消息
  - done 完成态
  - fallback 非流式
  - session save/load

### 2. `server/core/generation.py`

- 既负责 prompt 组装，又负责 source 构造和流式元数据
- 新增导出用的 retrieval context 时，最可能从这里扩展

### 3. `frontend/src/components/MainWorkspace.tsx`

- 回答卡片 UI 已较复杂
- 复制按钮、成功反馈、整会话导出入口都要避免破坏现有阅读节奏

## 推荐实现方向

推荐采用“后端先标准化导出上下文，前端只做展示和拼装”的模式。

理由：

- 你的优先级是数据准确，不是最小 UI 改动
- 后端最清楚本轮真实使用了哪些检索结果
- 前端只负责持久化与 Markdown 导出，数据口径更稳定

建议的总体方向：

1. 后端定义可导出的 retrieval context DTO
2. `/query` 和 `/query/stream` 一起返回该 DTO
3. 前端扩展 `ChatTurn`
4. 前端新增 Markdown 导出拼装器
5. 最后再挂单条复制与整会话导出按钮

## 需要在后续规划阶段明确的问题

- 单条复制是否包含 `reasoning`
- 整会话导出中每一轮的 Markdown 分节格式
- retrieval context 是否保留 rerank score
- parent context 与 main chunks 的分组展示格式
- 复制成功反馈是 toast、按钮文案切换，还是轻量状态提示

## 对实施成本的判断

粗略判断：中等偏上复杂度。

原因：

- 涉及前后端契约调整
- 涉及 localStorage 模型迁移
- 涉及流式与非流式双路径一致性
- 涉及 UI 与导出格式双层设计

但它仍然是一个边界清晰的 feature，不属于架构重写。
