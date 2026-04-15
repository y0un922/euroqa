# LLM 回复复制与会话导出 Task Breakdown

## 任务目标

目标 feature：

- 为单条 LLM 回复增加复制按钮
- 支持导出/复制整个会话
- 输出格式为 Markdown
- 内容包含回答原文与该轮检索召回的全部上下文
- 以数据准确性优先

## 规划假设

- “全部检索上下文”在本次实现中指生成层实际消费的最终检索快照：
  - 主检索结果 `chunks`
  - 扩展上下文 `parent_chunks`
  - 与主检索结果对应的 rerank 分数
- 不把完整 LLM prompt 原样导出；不导出 embedding、内部 client 参数、完整历史 prompt 拼接结果。
- 整会话导出基于前端当前会话快照生成，不依赖后端 `ConversationManager` 重建。
- 为保证数据准确性，流式回答未完成前，不允许导出该条消息的最终 Markdown 包。

## 阶段总览

- Phase 1: 后端导出契约与检索快照标准化
- Phase 2: 前端数据接入与会话持久化
- Phase 3: Markdown 导出器与复制/下载动作封装
- Phase 4: UI 集成与交互反馈
- Phase 5: 回归验证与交付收口

## Phase 1: 后端导出契约与检索快照标准化

目标：
让 `/api/v1/query` 与 `/api/v1/query/stream` 的完成态都返回同一份、可持久化、可导出的 retrieval context 快照。

并行策略：
本阶段以单 lane 顺序执行，不建议并行。

Merge Risk：
低。核心变更集中在后端 schema、generation 和 query 编排文件，但存在协议耦合，拆并行收益不高。

### Lane A

#### P1-T1

- 描述：在 `server/models/schemas.py` 中定义 export-ready 的 retrieval context DTO，并把它纳入非流式响应与流式完成态元数据。
- 优先级：P0
- 预估工作量：M
- 依赖：无
- 验收标准：
  - 新结构能区分主检索上下文与父级扩展上下文
  - 主检索项支持携带 rerank score
  - 字段仅包含导出与前端持久化需要的内容，不直接暴露完整内部 `Chunk` 结构
  - `/query` 与 `/query/stream` 的完成态使用同一数据形状

#### P1-T2

- 描述：在 `server/core/generation.py` 中新增共享的 retrieval context snapshot builder，统一从 `chunks / parent_chunks / scores` 生成导出快照。
- 优先级：P0
- 预估工作量：M
- 依赖：P1-T1
- 验收标准：
  - 流式与非流式都复用同一个快照构造逻辑
  - 主检索结果与父级扩展结果分组清晰
  - 输出字段覆盖文件名、标题、章节、页码、条款、正文文本以及导出所需的补充元数据
  - builder 对空检索结果返回稳定空结构

#### P1-T3

- 描述：更新 `server/api/v1/query.py` 的 `/query` 与 `/query/stream` 完成态返回，并同步补齐后端契约测试。
- 优先级：P0
- 预估工作量：M
- 依赖：P1-T2
- 验收标准：
  - 非流式 `QueryResponse` 含 retrieval context
  - 流式 `done` payload 含相同 retrieval context
  - fallback 非流式路径与 stream 完成态在字段存在性上保持一致
  - `tests/server/test_api.py` 与 `tests/server/test_generation.py` 覆盖新增字段

## Phase 2: 前端数据接入与会话持久化

目标：
让前端能够稳定接收、保存、恢复 retrieval context，并把它绑定到每条 `ChatTurn`。

并行策略：
本阶段建议单 lane 顺序执行。`types`、`hook`、`session` 三处高度耦合，强行并行会提高回归风险。

Merge Risk：
中高。`frontend/src/lib/types.ts`、`frontend/src/hooks/useEuroQaDemo.ts`、`frontend/src/lib/session.ts` 都是状态核心路径。

### Lane A

#### P2-T1

- 描述：扩展前端类型与 API payload，纳入 retrieval context。
- 优先级：P0
- 预估工作量：S
- 依赖：P1-T3
- 验收标准：
  - `frontend/src/lib/types.ts` 增加 retrieval context 相关类型
  - `QueryResponse` 与 `StreamDonePayload` 同步扩展
  - `ChatTurn` 拥有可选且可持久化的 retrieval context 字段

#### P2-T2

- 描述：在 `frontend/src/hooks/useEuroQaDemo.ts` 中接入 retrieval context，覆盖流式完成、非流式 fallback 和错误分支。
- 优先级：P0
- 预估工作量：M
- 依赖：P2-T1
- 验收标准：
  - 流式完成时将 retrieval context 写入对应 `ChatTurn`
  - 非流式 fallback 时也写入同样结构
  - 错误分支保持稳定空值，不污染旧消息
  - 刷新页面后消息对象结构不丢失

#### P2-T3

- 描述：扩展 `frontend/src/lib/session.ts` 的 localStorage 序列化、恢复与迁移逻辑。
- 优先级：P0
- 预估工作量：M
- 依赖：P2-T2
- 验收标准：
  - 旧 session 仍可恢复
  - 新 session 可完整恢复 retrieval context
  - `frontend/src/lib/session.test.ts` 覆盖新旧数据结构
  - 恢复后的 streaming 消息仍按现有规则降级为 error，不影响新字段

## Phase 3: Markdown 导出器与复制/下载动作封装

目标：
定义稳定的 Markdown 输出模板，并实现单条复制与整会话导出的纯函数生成器。

并行策略：
先顺序冻结模板与共享格式化基础，再在单条导出与整会话导出之间并行。

Merge Risk：
中。若把两个 builder 放进同一文件，会出现中等冲突概率；建议先明确共享 helper，再并行分工。

#### P3-T1

- 描述：冻结 Markdown 模板，明确单条复制和整会话导出的章节结构与字段保留规则。
- 优先级：P0
- 预估工作量：S
- 依赖：P2-T3
- 验收标准：
  - 单条复制模板至少包含回答原文、引用来源、本轮 retrieval context
  - 整会话模板按轮次分节，结构稳定
  - 明确是否包含用户问题、reasoning、空 section 的处理规则
  - 模板规则能直接落为可测试的纯函数输出

#### P3-T2

- 描述：实现共享的 Markdown 格式化基础能力，例如 section builder、source 列表格式化、retrieval context 分组格式化。
- 优先级：P0
- 预估工作量：M
- 依赖：P3-T1
- 验收标准：
  - 共享 helper 输出稳定、无 UI 依赖
  - 对空 sources、空 retrieval context、空 related refs 有稳定行为
  - 输出不依赖浏览器环境，便于纯单元测试

### Lane A

#### P3-T3

- 描述：实现单条消息 Markdown builder。
- 优先级：P0
- 预估工作量：S
- 依赖：P3-T2
- 验收标准：
  - 输入单个 `ChatTurn`，输出可直接复制的 Markdown
  - 输出顺序与模板定义一致
  - 只在消息完成态下输出最终版本

### Lane B

#### P3-T4

- 描述：实现整会话 Markdown builder。
- 优先级：P0
- 预估工作量：M
- 依赖：P3-T2
- 验收标准：
  - 输入消息数组，输出整会话 Markdown
  - 每轮问答边界明确
  - 能跳过无效空消息，保留有效完成态消息

#### P3-T5

- 描述：封装浏览器复制与下载动作，并补齐纯函数/动作层测试。
- 优先级：P1
- 预估工作量：M
- 依赖：P3-T3, P3-T4
- 验收标准：
  - 复制动作优先用 Clipboard API，失败时返回可处理错误
  - 会话导出支持生成 `.md` 文件下载
  - `frontend/src/lib/` 下新增导出模块测试，覆盖单条与整会话样例

## Phase 4: UI 集成与交互反馈

目标：
把单条复制和整会话导出能力接入现有界面，且不破坏当前回答阅读流。

并行策略：
先顺序暴露 hook 级 action，再在单条消息入口与整会话入口之间并行。

Merge Risk：
中。`useEuroQaDemo.ts` 是共享热点，但 `MainWorkspace.tsx` 与 `TopBar.tsx` 可在 action 暴露后低冲突并行。

#### P4-T1

- 描述：在前端状态层暴露复制/导出动作与反馈状态。
- 优先级：P0
- 预估工作量：M
- 依赖：P3-T5
- 验收标准：
  - `useEuroQaDemo` 或等价 action 层向 UI 提供单条复制与整会话导出能力
  - UI 可感知成功、失败、禁用状态
  - streaming/空会话等边界条件有统一策略

### Lane A

#### P4-T2

- 描述：在 `frontend/src/components/MainWorkspace.tsx` 中为每条 assistant 回复增加复制按钮与反馈。
- 优先级：P0
- 预估工作量：M
- 依赖：P4-T1
- 验收标准：
  - 仅 assistant 回复展示复制入口
  - streaming 中的回复不可复制，避免导出不完整内容
  - 成功与失败反馈轻量、明确，不打断阅读

### Lane B

#### P4-T3

- 描述：在全局会话级入口增加整会话导出按钮，优先放在 `TopBar`。
- 优先级：P0
- 预估工作量：S
- 依赖：P4-T1
- 验收标准：
  - 空会话时禁用
  - 导出文件命名稳定且可读
  - 不与现有 LLM 设置入口冲突

#### P4-T4

- 描述：统一交互细节，包括 tooltip、aria label、禁用态文案与布局微调。
- 优先级：P1
- 预估工作量：S
- 依赖：P4-T2, P4-T3
- 验收标准：
  - 操作文案清晰，符合当前 UI 风格
  - 键盘与屏幕阅读器语义完整
  - 不引入明显布局抖动或消息区拥挤问题

## Phase 5: 回归验证与交付收口

目标：
验证协议、持久化、导出内容和 UI 动作在流式与非流式两条路径下都一致可靠。

并行策略：
后端测试与前端测试可并行，人工验证在两者完成后执行。

Merge Risk：
低。测试文件分散，冲突概率小。

### Lane A

#### P5-T1

- 描述：补齐后端回归测试。
- 优先级：P0
- 预估工作量：S
- 依赖：P4-T4
- 验收标准：
  - `tests/server/test_api.py` 覆盖 `/query` 与 `/query/stream` 新字段
  - `tests/server/test_generation.py` 覆盖 retrieval context builder 和空值行为

### Lane B

#### P5-T2

- 描述：补齐前端回归测试。
- 优先级：P0
- 预估工作量：M
- 依赖：P4-T4
- 验收标准：
  - `frontend/src/lib/api.test.ts` 覆盖 stream done 新字段
  - `frontend/src/lib/session.test.ts` 覆盖新旧 session 迁移
  - 新增导出器测试覆盖单条与整会话 Markdown 输出

#### P5-T3

- 描述：执行人工验证清单并记录边界行为。
- 优先级：P0
- 预估工作量：S
- 依赖：P5-T1, P5-T2
- 验收标准：
  - 验证流式成功路径
  - 验证流式失败后 fallback 非流式路径
  - 验证刷新页面后会话恢复
  - 验证单条复制与整会话导出的 Markdown 内容准确

## 并行执行建议

- 推荐并行的阶段：
  - Phase 3 的单条导出与整会话导出 builder
  - Phase 4 的单条复制 UI 与整会话导出 UI
  - Phase 5 的后端测试与前端测试
- 不推荐并行的阶段：
  - Phase 1
  - Phase 2

## 实施顺序建议

- 先打通后端协议，再打通前端状态
- 先完成纯函数导出器，再接入 UI
- 最后统一做 stream/fallback/session 恢复三条路径的验证
